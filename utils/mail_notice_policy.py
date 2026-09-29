"""Shared sent-notice boundary, checked before reading message/attachment bodies.

The user permits sent notifications and their non-minutes attachments only.
This module deliberately has no mailbox, file-content, model or network access.
"""

import re
import unicodedata
from urllib.parse import unquote, urlsplit


NOTICE_POLICY_VERSION = "edge-online-sent-dated-notices-no-minutes-v1"
SENT_FOLDER = "已发送"
EDGE_ONLINE_ONLY_MESSAGE = "邮件待办仅允许用 Edge 在线读取已发送通知；禁止 IMAP、收件箱和邮件/附件本地下载。"
SENT_FOLDER_ALIASES = frozenset({
    "sent", "sent items", "sent messages", "已发送", "已发送邮件",
    "已发送的邮件", "已傳送郵件", "已傳送", "寄件備份",
})


class EdgeOnlineOnlyError(RuntimeError):
    code = "EDGE_ONLINE_ONLY"


def reject_legacy_mail_io():
    """Stop old receive/archive entrypoints before credentials or content IO."""
    raise EdgeOnlineOnlyError(EDGE_ONLINE_ONLY_MESSAGE)


def is_edge_source(transport, url):
    """Only evidence observed in the approved Edge webmail page is eligible."""
    if transport != "edge" or not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        path = unquote(parts.path)
        return (parts.scheme == "https" and parts.hostname == "mail.nsu.edu.cn"
                and parts.port in (None, 443) and not parts.username and not parts.password
                and not parts.query and "\\" not in path and ".." not in path.split("/")
                and (path == "/owa" or path.startswith("/owa/")))
    except ValueError:
        return False


def _normalized(value):
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFKC", value)
    value = "".join(c for c in value if unicodedata.category(c) != "Cf")
    return " ".join(value.split()).strip().casefold()


def is_minutes_name(value):
    """Conservatively exclude minutes by subject, filename or sheet title.

    A subject explicitly mentioning minutes is not opened even when it also
    says notification. Ordinary notices without that subject may still require
    submission of minutes as a future deliverable; that is not reading minutes.
    """
    name = _normalized(value)
    compact = re.sub(r"[\s_\-—·.]+", "", name)
    return (any(word in compact for word in ("纪要", "紀要", "会议记录", "會議記錄"))
            or bool(re.search(r"\b(?:meeting[\s_-]*)?minutes\b", name)))


def is_sent_folder(value, attributes=()):
    """Recognize sent mail, never an unsent Outbox or an Inbox fallback."""
    name = _normalized(value).strip('"')
    if name in {"inbox", "收件箱", "收件匣", "outbox", "发件箱", "寄件匣", "草稿", "drafts"}:
        return False
    if isinstance(attributes, str):
        attributes = re.findall(r"\\[A-Za-z]+", attributes)
    if any(_normalized(flag) == "\\sent" for flag in attributes):
        return True
    return name in SENT_FOLDER_ALIASES
