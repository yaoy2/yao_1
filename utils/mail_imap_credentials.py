"""Windows Credential Manager storage for explicitly saved IMAP credentials.

This module does not enumerate credentials or inspect other mail clients. Callers
must supply the exact dedicated target. No credential values are logged.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2  # Persistent for this Windows user on this machine.
ERROR_NOT_FOUND = 1168
TARGET_PREFIX = "CodexMailWorkbench/IMAP/"
MAX_BLOB_SIZE = 2560


class CredentialError(RuntimeError):
    """A fixed error code safe to display or log."""


class CredentialNotFound(CredentialError):
    """The user has not saved credentials for this exact IMAP target."""


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _validate_target(target):
    if (not isinstance(target, str) or not target.startswith(TARGET_PREFIX)
            or len(target) > 1024 or len(target) <= len(TARGET_PREFIX)
            or any(ord(char) < 32 or ord(char) == 127 for char in target)):
        raise CredentialError("invalid_credential_target")


def _advapi():
    if os.name != "nt":
        raise CredentialError("windows_credential_manager_required")
    dll = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    dll.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    dll.CredWriteW.restype = wintypes.BOOL
    dll.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
    dll.CredReadW.restype = wintypes.BOOL
    dll.CredFree.argtypes = [ctypes.c_void_p]
    dll.CredFree.restype = None
    return dll


def save_credential(target, username, password):
    """Save only after the user explicitly opts in to local persistence."""
    _validate_target(target)
    if (not isinstance(username, str) or not username or "\x00" in username
            or not isinstance(password, str) or not password or "\x00" in password):
        raise CredentialError("invalid_credential")
    encoded = password.encode("utf-16-le")
    if len(encoded) > MAX_BLOB_SIZE:
        raise CredentialError("credential_too_long")
    blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    credential = CREDENTIALW()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.UserName = username
    credential.CredentialBlobSize = len(encoded)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    try:
        if not _advapi().CredWriteW(ctypes.byref(credential), 0):
            raise CredentialError("credential_save_failed")
    finally:
        # Best effort for this mutable buffer; Python string copies cannot be
        # reliably wiped, so this is not a claim of complete secure erasure.
        ctypes.memset(ctypes.addressof(blob), 0, len(blob))
        encoded = None
        password = None


def read_credential(target):
    """Return (username, password) for one dedicated target, without logging."""
    _validate_target(target)
    dll = _advapi()
    pointer = ctypes.POINTER(CREDENTIALW)()
    if not dll.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        if ctypes.get_last_error() == ERROR_NOT_FOUND:
            raise CredentialNotFound("imap_credential_not_saved")
        raise CredentialError("credential_read_failed")
    try:
        if not pointer:
            raise CredentialError("invalid_stored_credential")
        credential = pointer.contents
        size = credential.CredentialBlobSize
        if (credential.Type != CRED_TYPE_GENERIC or not credential.UserName
                or not credential.CredentialBlob or not size
                or size > MAX_BLOB_SIZE or size % 2):
            raise CredentialError("invalid_stored_credential")
        try:
            password = ctypes.string_at(credential.CredentialBlob, size).decode("utf-16-le")
        except UnicodeError:
            raise CredentialError("invalid_stored_credential") from None
        if not password or "\x00" in password:
            raise CredentialError("invalid_stored_credential")
        return credential.UserName, password
    finally:
        if pointer:
            dll.CredFree(pointer)
