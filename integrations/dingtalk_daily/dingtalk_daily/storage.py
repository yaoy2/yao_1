"""Atomic private results and a process lock with automatic OS release."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import uuid


class RunBusy(RuntimeError):
    pass


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", delete=False,
            dir=path.parent, prefix=".writing-", suffix=".tmp",
        ) as stream:
            temp_path = Path(stream.name)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        if temp_path.read_bytes() != value.encode("utf-8"):
            raise OSError("输出回读校验失败。")
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def write_json(path: Path, value: dict) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


@contextmanager
def desktop_lock():
    """One reader per Windows session, even across configs and output folders."""
    if os.name != "nt":
        # The live adapter is Windows-only. This path keeps simulated runs and
        # CI deterministic while sharing a single lock per local user.
        import getpass
        import hashlib
        user_tag = hashlib.sha256(getpass.getuser().encode()).hexdigest()[:16]
        with run_lock(Path(tempfile.gettempdir()) / ("dingtalk-ui-" + user_tag)):
            yield
        return
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, True, "Local\\YaoTools.DingTalkDaily.UI")
    if not handle:
        raise OSError("无法取得本机钉钉采集锁。")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        raise RunBusy("本机钉钉已有采集或适配操作，不重复操作同一桌面。")
    try:
        yield
    finally:
        kernel32.ReleaseMutex(handle)
        kernel32.CloseHandle(handle)


@contextmanager
def run_lock(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    # Never unlink this file: another process may already hold its handle.
    with (output / ".run.lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            raise RunBusy("已有一次整理正在执行，本次未重复启动。") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def start_run(output: Path, when: datetime) -> Path:
    folder = output / when.date().isoformat() / (
        when.strftime("%H%M%S") + "-" + uuid.uuid4().hex[:8]
    )
    folder.mkdir(parents=True, exist_ok=False)
    write_json(folder / "status.json", {
        "status": "running", "started_at": when.isoformat(),
        "message": "采集中；仅 complete 表示本次覆盖检查通过。",
    })
    return folder


def finish_run(folder: Path, status: dict) -> None:
    write_json(folder / "status.json", status)
    pointer = {"run": folder.name, **status}
    write_json(folder.parent / "latest.json", pointer)
    if status["status"] == "complete":
        write_json(folder.parent / "latest_success.json", pointer)
