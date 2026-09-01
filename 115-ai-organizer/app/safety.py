from __future__ import annotations

from dataclasses import dataclass

from .config import Settings, normalize_path


class SafetyError(RuntimeError):
    pass


class WriteDisabledError(SafetyError):
    pass


class PathNotAllowedError(SafetyError):
    pass


class NativeIdMissingError(SafetyError):
    pass


FORBIDDEN_OPERATIONS = ("delete", "remove", "unlink")
WRITE_OPERATIONS = ("mkdir", "move", "rename", "copy", "upload", "overwrite")


def is_under_root(path: str, allowed_root: str) -> bool:
    candidate = normalize_path(path)
    root = normalize_path(allowed_root)
    if root == "/":
        return True
    return candidate == root or candidate.startswith(root + "/")


def assert_under_allowed_root(path: str, settings: Settings) -> str:
    candidate = normalize_path(path)
    if not is_under_root(candidate, settings.allowed_root):
        raise PathNotAllowedError(
            f"路径超出允许范围：{candidate}。第一版只能访问 {settings.allowed_root}"
        )
    return candidate


def assert_write_blocked(operation: str, settings: Settings | None = None) -> None:
    name = (operation or "").strip().lower()
    if name in FORBIDDEN_OPERATIONS:
        raise WriteDisabledError("禁止删除 115 文件。即使以后需要删除，也必须单独设计。")
    write_mode = bool(settings and settings.write_mode)
    if name in WRITE_OPERATIONS:
        if not write_mode:
            raise WriteDisabledError(
                f"WRITE_MODE 未开启，禁止执行 {operation}。第一版只生成整理计划，不修改 115 文件。"
            )
        raise WriteDisabledError(
            f"第一版不提供可调用的远程写入接口，即使 WRITE_MODE=true 也不会执行 {operation}。"
        )
    raise WriteDisabledError(f"未知写入操作已被拦截：{operation}")


@dataclass(frozen=True)
class DryRunPreview:
    operation: str
    old_path: str
    new_path: str
    old_name: str
    new_name: str
    would_execute: bool = False
    note: str = "dry-run only; phase 1 never writes to 115"


def preview_write(
    operation: str,
    old_path: str,
    new_path: str = "",
    old_name: str = "",
    new_name: str = "",
    settings: Settings | None = None,
) -> DryRunPreview:
    assert_write_blocked(operation, settings)
    return DryRunPreview(
        operation=operation,
        old_path=old_path,
        new_path=new_path,
        old_name=old_name,
        new_name=new_name,
    )
