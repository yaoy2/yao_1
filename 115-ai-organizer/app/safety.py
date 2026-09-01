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
            f"路径超出允许范围：{candidate}。本项目只能访问 {settings.allowed_root}"
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
                f"WRITE_MODE 未开启，通用入口禁止执行 {operation}。请使用带确认码的审核清单执行器。"
            )
        raise WriteDisabledError(
            f"通用写入入口不执行 {operation}。远程整理只能通过带确认码的审核清单执行器完成。"
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
    note: str = "dry-run only; generic write entry never writes to 115"


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
