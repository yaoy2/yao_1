"""Read-only previews and explicit, verified local moves for M20."""

from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Callable, Iterable
import uuid

from .models import Decision, ExecutionResult, Plan, PlanItem, ProgressEvent, selected_rules
from .dispatch import DISPATCH_ARCHIVE, DISPATCH_KIND, classify_dispatch, dispatch_number, is_dispatch_named
from .dingtalk_dispatch import DingTalkError, DingTalkRegister, REGISTER_YEAR
from .file_dates import creation_date_bounds, creation_time_ns, validate_start_date
from .invoices import INVOICE_HINT, classify_invoice
from .monthly import MONTHLY_HINT, classify_monthly
from .news import NEWS_DIRECTORY, classify_news_file, classify_news_folder, is_news_directory_name, is_news_word
from .readers import read_document_text
from .rules import RELEASE_DATE, VERSION
from .school_calendar import CALENDAR_PERIOD
from .weekly import classify_weekly, with_monthly_summary


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_link(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _normal_path(path: Path, *, root: Path | None = None) -> Path:
    path = Path(os.path.abspath(path))
    if root is not None and not path.is_relative_to(root):
        raise ValueError("路径超出当前Ding2026目录")
    for part in [path, *path.parents]:
        if part.exists() or part.is_symlink():
            if _is_link(part):
                raise ValueError("路径含链接、联接或未落地文件，请先确认本地同步目录")
    return path


def _root(path: str | Path) -> Path:
    root = _normal_path(Path(path))
    if not root.is_dir():
        raise ValueError("请选择已同步到本机的 Ding2026 文件夹")
    return root


@contextmanager
def _read_locked(path: Path, *, for_move: bool = False):
    """Windows denies writes while reading/moving; only our read handle is closed."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        access = 0x80000000 | (0x10000 if for_move else 0)
        # The move handle denies rename/delete by another process until verification ends.
        share = 0x1 if for_move else 0x1 | 0x4
        handle = create(str(path), access, share, None, 3, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except Exception:
            close = kernel.CloseHandle
            close.argtypes = [wintypes.HANDLE]
            close(handle)
            raise
        with os.fdopen(fd, "rb") as stream:
            yield stream
    else:
        with path.open("rb") as stream:
            yield stream


def _hash_stream(stream) -> str:
    stream.seek(0)
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _hash_file(path: Path) -> str:
    with _read_locked(path) as stream:
        return _hash_stream(stream)


def _classify(path: Path, root: Path, mode: str | Iterable[str], *, calendar_period: str = CALENDAR_PERIOD) -> Decision:
    rules = selected_rules(mode)
    if "dispatch" in rules and path.suffix.lower() == ".pdf":
        decision = classify_dispatch(path)
        if decision.status != "ignored":
            return decision
    if is_dispatch_named(path.stem):
        return Decision("ignored")
    if INVOICE_HINT.search(path.name):
        return classify_invoice(path, root) if "invoice" in rules else Decision("ignored")
    if "monthly" in rules and MONTHLY_HINT.search(path.name):
        return classify_monthly(path, root)
    if "news" in rules and is_news_word(path):
        news = classify_news_file(path)
        if news.status != "ignored":
            # Clear weekly evidence takes precedence over an article candidate.
            if not _matches_rules(path.name, ("minutes", "attendance")):
                return news
            weekly = classify_weekly(path.name, read_document_text(path)[0], calendar_period=calendar_period)
            if weekly.status != "ready":
                return news
    if not _matches_rules(path.name, rules):
        return Decision("ignored")
    initial = classify_weekly(path.name, calendar_period=calendar_period)
    if initial.status in {"skip", "ignored"}:
        return initial
    text, limitation = read_document_text(path)
    decision = classify_weekly(path.name, text, calendar_period=calendar_period)
    if (decision.kind in {"会议纪要", "学院党政联席会纪要"} and "minutes" not in rules
            or decision.kind == "考勤记录" and "attendance" not in rules):
        return Decision("ignored")
    if limitation and decision.status == "review":
        decision = replace(decision, reason=f"{decision.reason}；{limitation}")
    elif limitation and not text.strip() and decision.status == "ready":
        decision = replace(decision, reason=f"{decision.reason}；正文未提取，依据文件名及校历核对")
    return with_monthly_summary(decision, path.name, text)


def _matches_rules(name: str, rules: Iterable[str]) -> bool:
    if "dispatch" in rules and Path(name).suffix.lower() == ".pdf":
        return True
    if INVOICE_HINT.search(name):
        return "invoice" in rules
    return bool("monthly" in rules and MONTHLY_HINT.search(name)
                or "minutes" in rules and re.search(r"纪要|例会|会议", name)
                or "attendance" in rules and "考勤" in name)


def _notify(callback, stage: str, completed: int, total: int, message: str, item=None) -> None:
    if callback is not None:
        try:
            callback(ProgressEvent(stage, completed, total, message, replace(item) if item else None))
        except Exception:
            # A display callback must never interrupt or change a file operation.
            pass


def _target(root: Path, decision: Decision, filename: str) -> Path:
    if decision.kind == "学院月报":
        if not decision.target_name:
            raise ValueError("无法确定学院月报统一文件名，请核对单位、月份和人名")
        filename = decision.target_name
    elif decision.kind in {"会议纪要", "考勤记录"} and "党政联席会" not in filename:
        if not decision.target_name:
            raise ValueError("无法确定统一文件名，请核对单位和周次")
        filename = decision.target_name
    elif decision.kind == DISPATCH_KIND and decision.target_name:
        filename = decision.target_name
    if (not filename or Path(filename).name != filename or re.search(r'[<>:"/\\|?*\x00-\x1f]', filename)):
        raise ValueError("归档文件名无效")
    relative = Path(decision.relative_dir)
    if not decision.relative_dir or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("归档目标不正确")
    if decision.kind in {"发票", "发票压缩包"}:
        if not re.fullmatch(r"07_年度工作档案/(20\d{2})年/财务/\1年发票", relative.as_posix()):
            raise ValueError("发票目标不是已核对的年度财务发票目录")
        if not (root / relative).is_dir():
            raise ValueError("现有发票目录已变化，请重新预览")
    elif decision.kind == "学院新闻":
        if relative != Path(NEWS_DIRECTORY):
            raise ValueError("新闻目标不是当前学期新闻目录")
    elif decision.kind == DISPATCH_KIND:
        if not re.fullmatch(r"20\d{2}", decision.period) or relative != Path(DISPATCH_ARCHIVE.format(year=decision.period)):
            raise ValueError("发文目标与文号年份不一致")
    elif relative.parts[0] not in {"月报", "02_学期工作"}:
        raise ValueError("归档目标不在本程序规则内")
    target = _normal_path(root / relative / filename, root=root)
    for parent in target.parents:
        if parent == root:
            break
        if parent.exists() and not parent.is_dir():
            raise ValueError("归档路径被同名文件占用")
    return target


def _destination_state(target: Path, digest: str, size: int) -> tuple[str, str, Path]:
    if target.exists():
        if target.is_file() and not _is_link(target) and target.stat().st_size == size and _hash_file(target) == digest:
            return "duplicate", "目标已有同名且内容相同的文件；源文件保留原处", target
        return "collision", "目标已有同名文件或目录；不覆盖，源文件保留原处", target
    if target.parent.is_dir():
        for other in sorted(target.parent.iterdir(), key=lambda p: p.name.casefold()):
            if not other.is_file() or _is_link(other) or other.stat().st_size != size:
                continue
            if _hash_file(other) == digest:
                return "duplicate", f"归档目录已有相同内容：{other.name}；源文件保留原处", other
    return "", "", target


def _duplicate(target: Path, digest: str, size: int) -> tuple[str, str]:
    status, reason, _ = _destination_state(target, digest, size)
    return status, reason


def _dispatch_duplicate(target: Path, number: str, digest: str, size: int) -> tuple[str, str]:
    if target.parent.is_dir():
        for other in target.parent.iterdir():
            if other.suffix.lower() == ".pdf" and dispatch_number(other.stem) == number:
                if _is_link(other) or not other.is_file() or other.stat().st_size != size or _hash_file(other) != digest:
                    return "collision", f"归档目录已有同文号不同版本：{other.name}"
    return _duplicate(target, digest, size)


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _folder_members(folder: Path) -> dict[str, os.stat_result]:
    members = {}
    pending = [folder]
    while pending:
        parent = _normal_path(pending.pop(), root=folder)
        for path in parent.iterdir():
            info = path.lstat()
            if _is_link(path) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError("新闻文件夹含链接或特殊文件，请核对后重新预览")
            members[path.relative_to(folder).as_posix()] = info
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
    return members


def _folder_layout(members: dict[str, os.stat_result]) -> list[tuple[str, int | None]]:
    return [(name, None if stat.S_ISDIR(info.st_mode) else info.st_size) for name, info in sorted(members.items())]


def _confirm_folder_members(folder: Path, members: dict[str, os.stat_result]) -> None:
    current = _folder_members(folder)
    if current.keys() != members.keys() or any(_signature(info) != _signature(current[name]) for name, info in members.items()):
        raise ValueError("新闻文件夹内容已变化，请重新预览")


def _folder_digest(folder: Path, members: dict[str, os.stat_result]) -> tuple[str, int]:
    entries = []
    size = 0
    for name, length in _folder_layout(members):
        digest = None
        if length is not None:
            with _read_locked(_normal_path(folder / name, root=folder)) as stream:
                if _signature(os.fstat(stream.fileno())) != _signature(members[name]):
                    raise ValueError("新闻文件夹内容已变化，请重新预览")
                digest = _hash_stream(stream)
            size += length
        entries.append((name, length, digest))
    _confirm_folder_members(folder, members)
    data = json.dumps(entries, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(data).hexdigest(), size


def _news_folder_duplicate(target: Path, digest: str, members: dict[str, os.stat_result]) -> tuple[str, str]:
    layout = _folder_layout(members)
    if target.exists():
        if target.is_dir():
            existing = _folder_members(target)
            if _folder_layout(existing) == layout and _folder_digest(target, existing)[0] == digest:
                return "duplicate", "目标已有同名且内容相同的新闻文件夹；原件保留原处"
        return "collision", "目标已有同名文件或目录；新闻原件保留原处"
    if target.parent.is_dir():
        for other in sorted(target.parent.iterdir(), key=lambda path: path.name.casefold()):
            if not other.is_dir() or _is_link(other):
                continue
            try:
                existing = _folder_members(other)
                if _folder_layout(existing) == layout and _folder_digest(other, existing)[0] == digest:
                    return "duplicate", f"新闻目录已有相同整包内容：{other.name}；原件保留原处"
            except (OSError, ValueError):
                # An unrelated archive may be offline or contain a link.
                continue
    return "", ""


def _summary_target(root: Path, decision: Decision, filename: str) -> Path | None:
    if not decision.summary_relative_dir:
        return None
    return _target(root, replace(decision, relative_dir=decision.summary_relative_dir), filename)


def _minute_targets(root: Path, decision: Decision, name: str, digest: str, size: int) -> tuple[Path, Path, str, str, bool, bool]:
    primary = _target(root, decision, name)
    summary = _summary_target(root, decision, name)
    if summary is None:
        raise ValueError("会议纪要缺少月度汇总目标，请重新预览")
    first = _destination_state(primary, digest, size)
    second = _destination_state(summary, digest, size)
    if any(state[0] == "collision" for state in (first, second)):
        status, reason = "collision", "原分类或月度汇总目标同名冲突；两处均不写入，源文件保留原处"
    elif all(state[0] == "duplicate" for state in (first, second)):
        status, reason = "duplicate", "原分类和月度汇总均已有相同内容；源文件保留原处"
    else:
        status, reason = "", ""
    return first[2], second[2], status, reason, first[0] == "duplicate", second[0] == "duplicate"


def scan(root: str | Path, mode: str | Iterable[str], *,
         calendar_period: str = CALENDAR_PERIOD,
         start_date: str = "",
         on_progress: Callable[[ProgressEvent], None] | None = None) -> Plan:
    """Preview leaves source/archive directories unchanged; temporary reading copies are discarded."""
    rules = selected_rules(mode)
    if calendar_period not in ("", CALENDAR_PERIOD):
        raise ValueError("尚未配置该学期校历")
    end_time = datetime.now().astimezone().isoformat() if start_date else ""
    if start_date:
        start_date = validate_start_date(start_date)
    bounds = creation_date_bounds(start_date, end_time) if start_date else None
    root = _root(root)
    plan = Plan(str(root), mode if isinstance(mode, str) else "selected", _now(), uuid.uuid4().hex,
                rules=list(rules), calendar_period=calendar_period, start_date=start_date, end_time=end_time)
    planned_hashes = {}
    paths = sorted((path for path in root.iterdir() if path.is_file() or path.is_symlink()
                    or ("news" in rules and path.is_dir() and is_news_directory_name(path.name))),
                   key=lambda p: p.name.casefold())
    for index, path in enumerate(paths, 1):
        plan.scanned_count += 1
        is_directory = path.is_dir()
        if not (is_directory and "news" in rules or not is_directory and (
                _matches_rules(path.name, rules) or "news" in rules and is_news_word(path))):
            continue
        _notify(on_progress, "scan", index - 1, len(paths), f"正在核对：{path.name}")
        item = PlanItem(path.name, str(path), is_directory=is_directory)
        try:
            _normal_path(path, root=root)
            with _preview_source(path, is_directory) as (before, stream):
                if bounds:
                    item.creation_time_ns = creation_time_ns(before)
                    if not bounds[0] <= item.creation_time_ns <= bounds[1]:
                        plan.date_excluded_count += 1
                        continue
                members = {}
                if is_directory:
                    if not any(is_news_word(child) and (child.is_file() or _is_link(child)) for child in path.iterdir()):
                        continue
                    members = _folder_members(path)
                    decision = _classify_news_folder(path, members)
                else:
                    decision = _classify(path, root, rules, calendar_period=calendar_period)
                if decision.status == "ignored":
                    continue
                item.status, item.kind, item.period = decision.status, decision.kind, decision.period
                item.department, item.reason = decision.department, decision.reason
                item.manual_selection = decision.manual_selection
                item.document_number = decision.document_number
                item.document_title = decision.document_title
                item.document_date = decision.document_date
                item.week_label = decision.week_label
                item.size, item.mtime_ns = before.st_size, before.st_mtime_ns
                if decision.status == "ready":
                    if is_directory:
                        item.sha256, item.size = _folder_digest(path, members)
                    else:
                        item.sha256 = _hash_stream(stream)
                    current = path.stat()
                    if _signature(current) != _signature(before):
                        raise ValueError("扫描时材料发生变化，请重新预览")
                    if bounds and creation_time_ns(current) != item.creation_time_ns:
                        raise ValueError("扫描时文件创建时间发生变化，请重新预览")
                    if decision.summary_relative_dir:
                        target, summary, status, reason, primary_exists, _ = _minute_targets(
                            root, decision, path.name, item.sha256, item.size)
                        item.summary_destination = str(summary)
                        if primary_exists and not status:
                            item.reason += "；原分类已有相同内容，本次补齐月度副本并保留源文件"
                    else:
                        target = _target(root, decision, path.name)
                        if is_directory:
                            status, reason = _news_folder_duplicate(target, item.sha256, members)
                        elif item.document_number:
                            status, reason = _dispatch_duplicate(target, item.document_number, item.sha256, item.size)
                        else:
                            status, reason = _duplicate(target, item.sha256, item.size)
                    item.destination = str(target)
                    if target.name != path.name:
                        item.reason += f"；分发后统一命名为：{target.name}"
                    key = (str(target.parent).casefold(), str(Path(item.summary_destination).parent).casefold()
                           if item.summary_destination else "", item.sha256)
                    if not status and key in planned_hashes:
                        status, reason = "duplicate", f"与本批文件内容相同：{planned_hashes[key]}；先处理该文件，当前源文件保留原处"
                    if status:
                        item.status, item.reason = status, reason
                    else:
                        planned_hashes[key] = path.name
        except Exception as exc:
            item.status = "review"
            item.reason = f"无法安全预览：{exc}"
        plan.items.append(item)
        _notify(on_progress, "scan", index, len(paths), f"已核对：{path.name}", item)
    destinations: dict[str, list[PlanItem]] = {}
    document_numbers: dict[str, list[PlanItem]] = {}
    for item in plan.items:
        if item.document_number and item.sha256:
            document_numbers.setdefault(item.document_number, []).append(item)
        if item.destination and item.sha256 and item.status in {"ready", "duplicate"}:
            for destination in (item.destination, item.summary_destination):
                if destination:
                    destinations.setdefault(destination.casefold(), []).append(item)
    for group in destinations.values():
        if len({item.sha256 for item in group}) > 1:
            for item in group:
                item.status = "collision"
                item.reason = f"本批不同内容将同名为：{Path(item.destination).name}；请核对版本，源文件保留原处"
                _notify(on_progress, "scan", len(paths), len(paths), item.reason, item)
    for number, group in document_numbers.items():
        if len({item.sha256 for item in group}) > 1:
            for item in group:
                item.status, item.reason = "collision", f"本批有多份 {number}，内容不同，请核对正式版本"
                _notify(on_progress, "scan", len(paths), len(paths), item.reason, item)
    _notify(on_progress, "scan", len(paths), len(paths), "预览完成")
    return plan


@contextmanager
def _preview_source(path: Path, is_directory: bool):
    if is_directory:
        yield path.stat(), None
    else:
        with _read_locked(path) as stream:
            yield os.fstat(stream.fileno()), stream


def _classify_news_folder(path: Path, members: dict[str, os.stat_result]) -> Decision:
    files = [path / name for name, info in members.items() if stat.S_ISREG(info.st_mode)]
    return classify_news_folder(path, files)


@contextmanager
def _run_lock(path: Path):
    """A process lock, not a claim of distributed locking across Drive replicas."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        handle = create(str(path), 0x80000000 | 0x40000000, 0, None, 4, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            raise RuntimeError("已有分发正在执行，或记录目录不可写；请等待结束后重试")
        try:
            yield
        finally:
            close = kernel.CloseHandle
            close.argtypes = [wintypes.HANDLE]
            close.restype = wintypes.BOOL
            close(handle)
    else:
        import fcntl
        with path.open("a+b") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError("已有分发正在执行，请等待结束后重试") from exc
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _write_record(stream, event: str, **payload) -> None:
    stream.write(json.dumps({"event": event, "time": _now(), **payload}, ensure_ascii=False) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _move_no_replace(source: Path, target: Path, stream=None) -> None:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt

        if stream is None:
            raise ValueError("Windows移动必须持有已验证的文件句柄")

        class FileRenameInfo(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("RootDirectory", wintypes.HANDLE),
                        ("FileNameLength", wintypes.DWORD), ("FileName", wintypes.WCHAR * 1)]

        name = str(target).encode("utf-16-le")
        offset = FileRenameInfo.FileName.offset
        buffer = ctypes.create_string_buffer(max(ctypes.sizeof(FileRenameInfo), offset + len(name) + 2))
        info = ctypes.cast(buffer, ctypes.POINTER(FileRenameInfo)).contents
        info.Flags = 0  # ReplaceIfExists = FALSE.
        info.RootDirectory = None
        info.FileNameLength = len(name)
        ctypes.memmove(ctypes.addressof(buffer) + offset, name, len(name))
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        rename = kernel.SetFileInformationByHandle
        rename.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        rename.restype = wintypes.BOOL
        if not rename(msvcrt.get_osfhandle(stream.fileno()), 3, buffer, len(buffer)):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        # Same-volume no-overwrite move for tests and optional non-Windows CLI use.
        os.link(source, target, follow_symlinks=False)
        source.unlink()


def _copy_no_replace(stream, target: Path, digest: str) -> None:
    """Only discard an incomplete file created by this copy; never replace existing content."""
    created = None
    try:
        with target.open("xb") as output:
            created = os.fstat(output.fileno())
            stream.seek(0)
            shutil.copyfileobj(stream, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if _hash_file(target) != digest:
            raise ValueError("月度汇总副本内容校验失败，源文件保留")
    except Exception:
        if created and target.exists():
            current = target.lstat()
            if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                target.unlink()
        raise


def _move_directory_no_replace(source: Path, target: Path) -> None:
    if os.name == "nt":
        os.rename(source, target)  # Windows rename fails if the target already exists.
        return
    import ctypes
    import sys

    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        result = libc.renamex_np(os.fsencode(source), os.fsencode(target), 4)  # RENAME_EXCL
    elif hasattr(libc, "renameat2"):
        result = libc.renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1)  # RENAME_NOREPLACE
    else:
        raise OSError("当前系统无法安全移动整个文件夹")
    if result:
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), str(target))


def _execute_news_folder(root: Path, source: Path, item: PlanItem, bounds, log) -> None:
    before = source.stat()
    if bounds and (creation_time_ns(before) != item.creation_time_ns
                   or not bounds[0] <= item.creation_time_ns <= bounds[1]):
        item.status, item.reason = "changed", "文件夹创建时间或筛选范围已变化，请重新预览"
        return
    members = _folder_members(source)
    digest, size = _folder_digest(source, members)
    if (size, before.st_mtime_ns, digest) != (item.size, item.mtime_ns, item.sha256):
        item.status, item.reason = "changed", "预览后新闻文件夹已变化，请重新预览"
        return
    decision = _classify_news_folder(source, members)
    if decision.status != "ready":
        item.status, item.reason = "review", "执行前重新核对未通过，请重新预览"
        return
    target = _target(root, decision, source.name)
    if target != Path(item.destination) or item.summary_destination:
        item.status, item.reason = "changed", "目标与预览不一致，请重新预览"
        return
    status, reason = _news_folder_duplicate(target, digest, members)
    if status:
        item.status, item.reason = status, reason
        return
    _write_record(log, "planned", file=asdict(item))
    target.parent.mkdir(exist_ok=True)
    _target(root, decision, source.name)
    _normal_path(source, root=root)
    _confirm_folder_members(source, members)
    if _signature(source.stat()) != _signature(before):
        raise ValueError("执行前新闻文件夹已变化，请重新预览")
    _move_directory_no_replace(source, target)
    try:
        if _folder_digest(target, _folder_members(target)) != (digest, size):
            raise ValueError("归档目标内容与预览不同")
    except (OSError, ValueError) as exc:
        item.status, item.reason = "error", f"文件夹已整包移至目标，请检查归档和记录：{exc}"
        return
    item.status, item.reason = "moved", "已整包分发，目录结构、文件名和内容校验一致"


def _log_path(root: Path) -> tuple[Path, Path]:
    directory = _normal_path(root / "98_系统" / "文件分发记录", root=root)
    return directory, directory / f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:12]}.jsonl"


def _sync_dispatches(root: Path, items: list[PlanItem], log, on_progress) -> None:
    register = None
    connection_error = ""
    for index, item in enumerate(items, 1):
        _notify(on_progress, "ding_sync", index - 1, len(items), f"正在核对钉钉文号：{item.document_number}")
        try:
            destination = root / DISPATCH_ARCHIVE.format(year=REGISTER_YEAR) / Path(item.destination).name
            destination = _normal_path(destination, root=root)
            if not destination.is_file() or _hash_file(destination) != item.sha256:
                raise DingTalkError("本地归档 PDF 缺失或已变化，待核对")
            if register is None and not connection_error:
                try:
                    register = DingTalkRegister.connect()
                except (DingTalkError, OSError) as exc:
                    connection_error = str(exc) if isinstance(exc, DingTalkError) else "无法读取钉钉连接配置"
            if connection_error:
                raise DingTalkError(connection_error)
            item.ding_reason = register.register(item, destination)
            item.ding_status = "synced"
        except (DingTalkError, OSError, ValueError) as exc:
            item.ding_status = "pending"
            item.ding_reason = str(exc) if isinstance(exc, DingTalkError) else "归档或钉钉响应未能核验，可补同步"
        _write_record(log, "ding_result", file=asdict(item))
        _notify(on_progress, "ding_sync", index, len(items), item.ding_reason, item)


def retry_dispatch_sync(root: str | Path, *, on_progress=None) -> ExecutionResult:
    """Replay only 2026 dispatches already confirmed for distribution."""
    root = _root(root)
    directory, log_path = _log_path(root)
    if not directory.is_dir():
        return ExecutionResult([], "")
    with _run_lock(_normal_path(directory / "running.lock", root=root)):
        pending = {}
        completed = set()
        for file in sorted(directory.glob("*.jsonl")):
            with _normal_path(file, root=root).open(encoding="utf-8") as source:
                for line in source:
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    details = entry.get("file", {})
                    if (entry.get("event") not in {"planned", "ding_result"}
                            or details.get("kind") != DISPATCH_KIND or details.get("period") != REGISTER_YEAR):
                        continue
                    key = (details["document_number"], details["sha256"])
                    if details.get("ding_status") == "synced":
                        completed.add(key)
                    else:
                        # A crash may occur after move but before the `result` event is written.
                        pending[key] = PlanItem(**details)
        items = [item for key, item in pending.items() if key not in completed]
        if not items:
            return ExecutionResult([], "")
        with log_path.open("x", encoding="utf-8", newline="\n") as log:
            _write_record(log, "ding_retry", version=VERSION, root=str(root))
            _sync_dispatches(root, items, log, on_progress)
    return ExecutionResult(items, str(log_path))


def execute(plan: Plan, selected_names: Iterable[str], *,
            on_progress: Callable[[ProgressEvent], None] | None = None) -> ExecutionResult:
    """Only selected ready items from this in-memory preview can be moved."""
    root = _root(plan.root)
    rules = selected_rules(plan.rules or plan.mode)
    if plan.calendar_period not in ("", CALENDAR_PERIOD):
        raise ValueError("预览的校历无效，请重新预览")
    bounds = creation_date_bounds(plan.start_date, plan.end_time) if plan.start_date else None
    selected = set(selected_names)
    if not selected:
        raise ValueError("请先勾选可分发文件")
    items = [replace(item) for item in plan.items]
    by_name = {item.name: item for item in items}
    if len(by_name) != len(items) or not selected.issubset(by_name) or any(by_name[name].status != "ready" for name in selected):
        raise ValueError("只能分发本次预览中勾选的可分发文件，请重新预览")
    log_dir, log_path = _log_path(root)
    log_dir.mkdir(parents=True, exist_ok=True)
    lock_path = _normal_path(log_dir / "running.lock", root=root)
    with _run_lock(lock_path), log_path.open("x", encoding="utf-8", newline="\n") as log:
        _write_record(log, "run", version=VERSION, release_date=RELEASE_DATE,
                      mode=plan.mode, rules=list(rules), calendar_period=plan.calendar_period,
                      date_basis="local_creation_time" if bounds else "all",
                      start_date=plan.start_date, end_time=plan.end_time,
                      root=str(root), plan_id=plan.plan_id, preview_at=plan.created_at)
        completed = 0
        for item in items:
            if item.name not in selected:
                continue
            moved = False
            summary_saved = False
            _notify(on_progress, "moving", completed, len(selected), f"正在分发：{item.name}", item)
            try:
                source = _normal_path(Path(item.source), root=root)
                valid_source = ("news" in rules and is_news_directory_name(source.name) and source.is_dir()
                                if item.is_directory else source.is_file())
                if source.parent != root or source.name != item.name or not valid_source:
                    item.status, item.reason = "changed", "源材料已不在根目录，请重新预览"
                    _write_record(log, "result", file=asdict(item))
                    continue
                if item.is_directory:
                    _execute_news_folder(root, source, item, bounds, log)
                    _write_record(log, "result", file=asdict(item))
                    continue
                with _read_locked(source) as stream:
                    info = os.fstat(stream.fileno())
                    if bounds and (creation_time_ns(info) != item.creation_time_ns
                                   or not bounds[0] <= creation_time_ns(info) <= bounds[1]):
                        item.status, item.reason = "changed", "文件创建时间或筛选范围已变化，请重新预览；本次未移动"
                        _write_record(log, "result", file=asdict(item))
                        continue
                    current_digest = _hash_stream(stream)
                    if (info.st_size, info.st_mtime_ns, current_digest) != (item.size, item.mtime_ns, item.sha256):
                        item.status, item.reason = "changed", "预览后文件已变化，请重新预览；本次未移动"
                        _write_record(log, "result", file=asdict(item))
                        continue
                    decision = _classify(source, root, rules, calendar_period=plan.calendar_period)
                    if decision.status != "ready":
                        item.status, item.reason = "review", "执行前重新核对未通过：" + decision.reason
                        _write_record(log, "result", file=asdict(item))
                        continue
                    summary = None
                    primary_exists = summary_exists = False
                    if decision.summary_relative_dir:
                        target, summary, status, reason, primary_exists, summary_exists = _minute_targets(
                            root, decision, source.name, current_digest, info.st_size)
                    else:
                        target = _target(root, decision, source.name)
                        if decision.kind == DISPATCH_KIND:
                            expected_fields = (item.document_number, item.document_title, item.document_date)
                            if (decision.document_number, decision.document_title, decision.document_date) != expected_fields:
                                item.status, item.reason = "changed", "发文登记信息与预览不一致，请重新预览"
                                _write_record(log, "result", file=asdict(item))
                                continue
                            status, reason = _dispatch_duplicate(target, decision.document_number, current_digest, info.st_size)
                        else:
                            status, reason = _duplicate(target, current_digest, info.st_size)
                    if target != Path(item.destination) or (str(summary) if summary else "") != item.summary_destination:
                        item.status, item.reason = "changed", "目标与预览不一致，请重新预览"
                        _write_record(log, "result", file=asdict(item))
                        continue
                    if status:
                        item.status, item.reason = status, reason
                        _write_record(log, "result", file=asdict(item))
                        continue
                    current = source.stat()
                    if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                        raise ValueError("执行前源路径已变化，本次未移动")
                    with _read_locked(source, for_move=True) as move_stream:
                        locked = os.fstat(move_stream.fileno())
                        if (locked.st_dev, locked.st_ino) != (info.st_dev, info.st_ino) or _hash_stream(move_stream) != item.sha256:
                            raise ValueError("执行前源文件已替换，请重新预览")
                        if bounds and creation_time_ns(locked) != item.creation_time_ns:
                            raise ValueError("执行前文件创建时间已变化，请重新预览")
                        _write_record(log, "planned", file=asdict(item))
                        _target(root, decision, source.name)
                        if summary is not None:
                            summary.parent.mkdir(parents=True, exist_ok=True)
                            _summary_target(root, decision, source.name)
                            _normal_path(summary, root=root)
                            if not summary_exists:
                                _copy_no_replace(move_stream, summary, item.sha256)
                            if _hash_file(summary) != item.sha256:
                                raise ValueError("月度汇总副本已变化，源文件保留")
                            summary_saved = True
                        if not primary_exists:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            _target(root, decision, source.name)
                            _move_no_replace(source, target, move_stream)
                            moved = True
                        if _hash_file(target) != item.sha256:
                            raise ValueError("已移至预览目标，但内容核验未通过，请根据记录检查目标文件")
                        if summary is not None and _hash_file(summary) != item.sha256:
                            raise ValueError("原分类已归档，但月度汇总副本发生变化，请检查记录")
                        item.status = "moved" if moved else "copied"
                        if summary is not None:
                            item.reason = ("已分发，原分类和月度汇总两份内容校验一致" if moved
                                           else "已补齐月度汇总副本，两份内容一致；原分类已有相同内容，源文件保留")
                        else:
                            item.reason = (f"已分发并统一命名为：{target.name}，内容校验一致" if target.name != item.name
                                           else "已分发，原文件名保留，内容校验一致")
            except Exception as exc:
                item.status = "error"
                item.reason = ("文件已移动，请检查记录：" if moved else "未移动：") + str(exc)
                if summary_saved:
                    item.reason += f"；月度副本已保存于：{item.summary_destination}"
            finally:
                completed += 1
                _notify(on_progress, "result", completed, len(selected), item.reason, item)
            _write_record(log, "result", file=asdict(item))
        dispatches = [item for item in items if item.name in selected and item.status == "moved"
                      and item.kind == DISPATCH_KIND and item.period == REGISTER_YEAR]
        _sync_dispatches(root, dispatches, log, on_progress)
        _write_record(log, "complete", moved=sum(item.status == "moved" for item in items),
                      copied=sum(item.status == "copied" for item in items), selected=len(selected))
    return ExecutionResult(items, str(log_path))
