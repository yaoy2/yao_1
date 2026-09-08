"""Save explicitly filed attachments directly in the configured local root.

Only the fixed receiver configuration chooses a destination. Mail text and
remote filing metadata never supply filesystem paths or commands.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from utils import mail_workspace
from utils.mail_filing_source import read_source


class FilingFileError(RuntimeError):
    pass


def _is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024))


def checked_root(value):
    path = Path(value)
    if not path.is_absolute() or not path.is_dir():
        raise FilingFileError("DESTINATION_UNAVAILABLE")
    for part in (path, *path.parents):
        if _is_link(part):
            raise FilingFileError("DESTINATION_UNSAFE")
    return path.resolve()


def _child(root, relative):
    if not relative or "\\" in relative or ":" in relative or any(
            part in {"", ".", ".."} for part in relative.split("/")):
        raise FilingFileError("DESTINATION_UNSAFE")
    path = root.joinpath(*relative.split("/"))
    if not path.resolve().is_relative_to(root) or path == root:
        raise FilingFileError("DESTINATION_UNSAFE")
    cursor = root
    for part in relative.split("/"):
        cursor = cursor / part
        if cursor.exists() or cursor.is_symlink():
            if _is_link(cursor):
                raise FilingFileError("DESTINATION_UNSAFE")
    return path


def _name(value, limit=240):
    value = unicodedata.normalize("NFC", str(value or "附件"))
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", value).strip(" .") or "附件"
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", value, re.I):
        value = "_" + value
    suffix = Path(value).suffix[:16]
    if len(value) > limit:
        value = value[:limit - len(suffix)].rstrip(" .") + suffix
    return value


@contextmanager
def _pinned_directory(root):
    """Keep Windows ancestors fixed while files are created and renamed.

    Reject reparse points on the opened handles. Omitting FILE_SHARE_DELETE
    prevents a checked directory from being renamed into a junction mid-copy.
    """
    if os.name != "nt":
        checked_root(root)
        yield
        return
    import ctypes
    from ctypes import wintypes

    class Info(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("creation", wintypes.FILETIME),
                    ("access", wintypes.FILETIME), ("write", wintypes.FILETIME),
                    ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD),
                    ("size_low", wintypes.DWORD), ("links", wintypes.DWORD),
                    ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    inspect = kernel.GetFileInformationByHandle
    inspect.argtypes = [wintypes.HANDLE, ctypes.POINTER(Info)]
    inspect.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    handles = []
    directories = [*reversed(root.parents), root]
    try:
        for directory in directories:
            if not directory.exists():
                raise FilingFileError("DESTINATION_UNAVAILABLE")
            # FILE_LIST_DIRECTORY participates in Windows share checks;
            # FILE_READ_ATTRIBUTES alone would still permit directory renames.
            handle = create(str(directory), 0x81, 0x3, None, 3, 0x02200000, None)
            if handle == ctypes.c_void_p(-1).value:
                raise FilingFileError("DESTINATION_UNAVAILABLE")
            handles.append(handle)
            info = Info()
            if not inspect(handle, ctypes.byref(info)):
                raise FilingFileError("DESTINATION_UNSAFE")
            if not info.attributes & 0x10 or info.attributes & 0x400:
                raise FilingFileError("DESTINATION_UNSAFE")
        checked_root(root)
        yield
    finally:
        for handle in reversed(handles):
            close(handle)


def _save_bytes(root, name, content, expected_sha):
    checked_root(root)
    with _pinned_directory(root):
        return _save_bytes_in_pinned_directory(root, name, content, expected_sha)


def _save_bytes_in_pinned_directory(root, name, content, expected_sha):
    """Exclusive final creation; preserve conflicting user files as versions."""
    if not content:
        raise FilingFileError("ATTACHMENT_EMPTY")
    sha = hashlib.sha256(content).hexdigest()
    if sha != expected_sha:
        raise FilingFileError("ATTACHMENT_HASH_MISMATCH")
    target = _child(root, name)
    for attempt in range(2):
        if target.exists():
            if target.is_file() and target.stat().st_size == len(content) and mail_workspace._sha_file(target) == sha:
                return target.relative_to(root).as_posix()
            if attempt:
                raise FilingFileError("DESTINATION_CONFLICT")
            suffix = Path(name).suffix
            stem = name[:-len(suffix)] if suffix else name
            # Reserve room for the conflict hash within Windows' filename limit.
            stem = stem[:237 - len(suffix)].rstrip(" .") or "附件"
            target = _child(root, f"{stem}__{sha[:16]}{suffix}")
            continue
        temporary = _child(root, ".filing-" + uuid4().hex + ".partial")
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if temporary.stat().st_size != len(content) or mail_workspace._sha_file(temporary) != sha:
                raise FilingFileError("FILE_VERIFY_FAILED")
            # Windows rename refuses an existing target. POSIX link has the
            # same exclusive-creation property (replace would overwrite it).
            if os.name == "nt":
                os.rename(temporary, target)
            else:
                os.link(temporary, target)
            if target.stat().st_size != len(content) or mail_workspace._sha_file(target) != sha:
                raise FilingFileError("FILE_VERIFY_FAILED")
            return target.relative_to(root).as_posix()
        except FileExistsError:
            # A concurrent receiver/user won the filename. Recheck the exact
            # content next pass; never overwrite an existing file.
            if attempt:
                raise FilingFileError("DESTINATION_CONFLICT") from None
        finally:
            if temporary.exists():
                temporary.unlink()  # Only the unique file created above.
    raise FilingFileError("DESTINATION_CONFLICT")


def export_message(workspace_root, destination_root, message, *, source_reader=read_source, allow_imap=True):
    """Return verified file receipts and a compact filing outcome, no secrets."""
    result = {"status": "error", "destination": "", "saved_count": 0,
              "total_count": len(message.get("attachments", [])), "error_count": 0,
              "error_codes": [], "files": []}
    errors = result["error_codes"]
    try:
        destination_root = checked_root(destination_root)
        source = source_reader(Path(workspace_root), message, allow_imap=allow_imap)
        errors.extend(source.get("error_codes", []))
        parsed = source.get("parsed")
        if not parsed:
            if not errors:
                errors.append("SOURCE_EML_MISSING")
            return result
        if parsed.get("id") != message["id"]:
            errors.append("SOURCE_ID_MISMATCH")
            return result
        if parsed.get("skip_sensitive") or parsed.get("authentication_notice"):
            errors.append("SENSITIVE_SOURCE_SKIPPED")
            return result
        attachments = parsed.get("attachments", [])
        expected = parsed.get("expected_attachment_count")
        result["total_count"] = max(len(attachments), expected if type(expected) is int and expected >= 0 else 0)
        if parsed.get("attachments_complete") is not True or expected != len(attachments):
            errors.append("ATTACHMENT_INVENTORY_INCOMPLETE")
        for attachment in attachments:
            content = attachment.get("data")
            if not isinstance(content, bytes) or not content:
                errors.append("ATTACHMENT_EMPTY" if content == b"" else "ATTACHMENT_MISSING")
                continue
            if attachment.get("size") != len(content):
                errors.append("ATTACHMENT_HASH_MISMATCH")
                continue
            name = _name(attachment.get("name"))
            try:
                relative = _save_bytes(destination_root, name, content, attachment.get("sha256"))
                result["files"].append({"name": attachment.get("name", "附件"), "path": relative,
                                        "size": len(content), "sha256": attachment["sha256"]})
                result["saved_count"] += 1
                result["destination"] = "."
            except FilingFileError as exc:
                errors.append(str(exc))
            except OSError:
                errors.append("FILE_COPY_FAILED")
        if not attachments and not errors:
            result["destination"] = ""
        if errors or result["saved_count"] != result["total_count"]:
            result["status"] = "partial" if result["saved_count"] else "error"
        else:
            result["status"] = "success"
    except FilingFileError as exc:
        errors.append(str(exc))
    except (OSError, ValueError, TypeError, KeyError):
        errors.append("FILE_COPY_FAILED")
    finally:
        result["error_count"] = len(errors)
        result["error_codes"] = sorted(set(errors))
    return result
