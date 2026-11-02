"""Read-only previews and explicit, verified local moves for M20."""

from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Callable, Iterable
import uuid

from .models import Decision, ExecutionResult, Plan, PlanItem, ProgressEvent, selected_rules
from .file_dates import creation_date_bounds, creation_time_ns, validate_start_date
from .invoices import INVOICE_HINT, classify_invoice
from .monthly import MONTHLY_HINT, classify_monthly
from .readers import read_document_text
from .rules import RELEASE_DATE, VERSION
from .school_calendar import CALENDAR_PERIOD
from .weekly import classify_weekly


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
    if INVOICE_HINT.search(path.name):
        return classify_invoice(path, root) if "invoice" in rules else Decision("ignored")
    if "monthly" in rules and MONTHLY_HINT.search(path.name):
        return classify_monthly(path, root)
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
    return decision


def _matches_rules(name: str, rules: Iterable[str]) -> bool:
    if INVOICE_HINT.search(name):
        return "invoice" in rules
    return bool("monthly" in rules and MONTHLY_HINT.search(name)
                or "minutes" in rules and re.search(r"纪要|例会", name)
                or "attendance" in rules and "考勤" in name)


def _notify(callback, stage: str, completed: int, total: int, message: str, item=None) -> None:
    if callback is not None:
        try:
            callback(ProgressEvent(stage, completed, total, message, replace(item) if item else None))
        except Exception:
            # A display callback must never interrupt or change a file operation.
            pass


def _target(root: Path, decision: Decision, filename: str) -> Path:
    relative = Path(decision.relative_dir)
    if not decision.relative_dir or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("归档目标不正确")
    if decision.kind in {"发票", "发票压缩包"}:
        if not re.fullmatch(r"07_年度工作档案/(20\d{2})年/财务/\1年发票", relative.as_posix()):
            raise ValueError("发票目标不是已核对的年度财务发票目录")
        if not (root / relative).is_dir():
            raise ValueError("现有发票目录已变化，请重新预览")
    elif relative.parts[0] not in {"月报", "02_学期工作"}:
        raise ValueError("归档目标不在本程序规则内")
    target = _normal_path(root / relative / filename, root=root)
    for parent in target.parents:
        if parent == root:
            break
        if parent.exists() and not parent.is_dir():
            raise ValueError("归档路径被同名文件占用")
    return target


def _duplicate(target: Path, digest: str, size: int) -> tuple[str, str]:
    if target.exists():
        if target.is_file() and not _is_link(target) and target.stat().st_size == size and _hash_file(target) == digest:
            return "duplicate", "目标已有同名且内容相同的文件；源文件保留原处"
        return "collision", "目标已有同名文件或目录；不覆盖，源文件保留原处"
    if target.parent.is_dir():
        for other in sorted(target.parent.iterdir(), key=lambda p: p.name.casefold()):
            if not other.is_file() or _is_link(other) or other.stat().st_size != size:
                continue
            if _hash_file(other) == digest:
                return "duplicate", f"归档目录已有相同内容：{other.name}；源文件保留原处"
    return "", ""


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
    paths = sorted((path for path in root.iterdir() if path.is_file() or path.is_symlink()),
                   key=lambda p: p.name.casefold())
    for index, path in enumerate(paths, 1):
        plan.scanned_count += 1
        if not _matches_rules(path.name, rules):
            continue
        _notify(on_progress, "scan", index - 1, len(paths), f"正在核对：{path.name}")
        item = PlanItem(path.name, str(path))
        try:
            _normal_path(path, root=root)
            with _read_locked(path) as stream:
                before = os.fstat(stream.fileno())
                if bounds:
                    item.creation_time_ns = creation_time_ns(before)
                    if not bounds[0] <= item.creation_time_ns <= bounds[1]:
                        plan.date_excluded_count += 1
                        continue
                decision = _classify(path, root, rules, calendar_period=calendar_period)
                if decision.status == "ignored":
                    continue
                item.status, item.kind, item.period = decision.status, decision.kind, decision.period
                item.department, item.reason = decision.department, decision.reason
                item.size, item.mtime_ns = before.st_size, before.st_mtime_ns
                if decision.status == "ready":
                    item.sha256 = _hash_stream(stream)
                    current = path.stat()
                    if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
                        raise ValueError("扫描时文件发生变化，请重新预览")
                    if bounds and creation_time_ns(current) != item.creation_time_ns:
                        raise ValueError("扫描时文件创建时间发生变化，请重新预览")
                    target = _target(root, decision, path.name)
                    item.destination = str(target)
                    status, reason = _duplicate(target, item.sha256, item.size)
                    key = (str(target.parent).casefold(), item.sha256)
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
    _notify(on_progress, "scan", len(paths), len(paths), "预览完成")
    return plan


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
    log_dir = _normal_path(root / "98_系统" / "文件分发记录", root=root)
    log_dir.mkdir(parents=True, exist_ok=True)
    lock_path = _normal_path(log_dir / "running.lock", root=root)
    log_path = log_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:12]}.jsonl"
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
            _notify(on_progress, "moving", completed, len(selected), f"正在分发：{item.name}", item)
            try:
                source = _normal_path(Path(item.source), root=root)
                if source.parent != root or source.name != item.name or not source.is_file():
                    item.status, item.reason = "changed", "源文件已不在根目录，请重新预览"
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
                    target = _target(root, decision, source.name)
                    if target != Path(item.destination):
                        item.status, item.reason = "changed", "目标与预览不一致，请重新预览"
                        _write_record(log, "result", file=asdict(item))
                        continue
                    status, reason = _duplicate(target, current_digest, info.st_size)
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
                        target.parent.mkdir(parents=True, exist_ok=True)
                        _target(root, decision, source.name)
                        _move_no_replace(source, target, move_stream)
                        moved = True
                        if _hash_file(target) != item.sha256:
                            raise ValueError("已移至预览目标，但内容核验未通过，请根据记录检查目标文件")
                        item.status, item.reason = "moved", "已分发，内容校验一致"
            except Exception as exc:
                item.status = "error"
                item.reason = ("文件已移动，请检查记录：" if moved else "未移动：") + str(exc)
            finally:
                completed += 1
                _notify(on_progress, "result", completed, len(selected), item.reason, item)
            _write_record(log, "result", file=asdict(item))
        _write_record(log, "complete", moved=sum(item.status == "moved" for item in items), selected=len(selected))
    return ExecutionResult(items, str(log_path))
