"""Parse fetched RFC 822 messages without network access or filesystem writes.

Authentication notices are detected conservatively and returned as metadata-only
records. Callers must also skip saving the raw message when that flag is true.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from email import policy
from email.errors import (
    CloseBoundaryNotFoundDefect,
    InvalidBase64CharactersDefect,
    InvalidBase64LengthDefect,
    InvalidBase64PaddingDefect,
    MultipartInvariantViolationDefect,
    NoBoundaryInMultipartDefect,
    StartBoundaryNotFoundDefect,
)
from email.header import decode_header
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser


_SAFE_HEADERS = ("From", "To", "Cc", "Date", "Subject", "Message-ID")
_STRUCTURAL_DEFECTS = (NoBoundaryInMultipartDefect, StartBoundaryNotFoundDefect,
                       CloseBoundaryNotFoundDefect, MultipartInvariantViolationDefect)
_AUTH_NOTICE = re.compile(
    r"验证码|校验码|动态(?:口令|码)|一次性(?:密码|口令)|"
    r"(?:重置|重设|找回|恢复)\s*(?:您的|你的|账户|帐号|账号)?\s*密码|"
    r"密码\s*(?:重置|重设|找回|恢复)|"
    r"(?:验证|确认)(?:您的|你的)?(?:电子邮箱|电子邮件|邮箱)(?:地址)?|"
    r"\b(?:otp|one[-\s]*time\s+(?:password|passcode|code)|"
    r"(?:verification|security|authentication|sign[-\s]*in|login)\s+(?:code|passcode)|"
    r"(?:reset|recover)\s+(?:(?:your|the|account)\s+)?password|"
    r"password\s+(?:reset|recovery)|magic\s+(?:login\s+|sign[-\s]*in\s+)?link|"
    r"(?:verify|confirm)\s+(?:(?:your|the)\s+)?(?:email|e-mail)(?:\s+address)?)\b",
    re.IGNORECASE,
)
_EXTENSIONS = {
    "application/pdf": ".pdf", "application/zip": ".zip",
    "application/gzip": ".gz", "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls", "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/webp": ".webp", "image/svg+xml": ".svg", "image/bmp": ".bmp",
    "text/plain": ".txt", "text/html": ".html", "text/calendar": ".ics",
    "text/csv": ".csv", "message/rfc822": ".eml", "message/global": ".eml",
}


def _decode_bytes(value: bytes, charset: str | None = None) -> str:
    # gb18030 includes GBK/GB2312 and recovers common undeclared Chinese mail.
    candidates = [charset, "utf-8-sig", "gb18030", "windows-1252"]
    for candidate in dict.fromkeys(candidates):
        if not candidate:
            continue
        try:
            return value.decode(candidate)
        except (LookupError, UnicodeError):
            pass
    return value.decode("utf-8", errors="replace")


def _clean_header(value: str) -> str:
    value = "".join(c for c in value if unicodedata.category(c) != "Cf")
    return re.sub(r"[\x00-\x20\x7f]+", " ", value).strip()


def _decode_header(value: str) -> str:
    try:
        parts = decode_header(value)
    except (ValueError, UnicodeError):
        parts = [(value, None)]
    decoded = []
    for piece, charset in parts:
        if isinstance(piece, bytes):
            decoded.append(_decode_bytes(piece, charset))
        else:
            # raw_items() retains undecoded 8-bit headers via surrogateescape.
            try:
                decoded.append(_decode_bytes(piece.encode("ascii", "surrogateescape")))
            except UnicodeError:
                decoded.append(piece)
    return _clean_header("".join(decoded))


def _header(message: Message, name: str) -> str:
    values = [_decode_header(value) for key, value in message.raw_items()
              if key.casefold() == name.casefold()]
    return ", ".join(values)


def _filename(part: Message, index: int, content_type: str) -> str:
    value = part.get_filename()
    if value:
        value = _decode_header(str(value))
        value = unicodedata.normalize("NFC", value.replace("\\", "/").rsplit("/", 1)[-1])
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", value).strip(" .")
        if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", value, re.I):
            value = "_" + value
    if not value or value in {".", ".."}:
        value = f"attachment-{index:03d}{_EXTENSIONS.get(content_type, '.bin')}"
    if len(value) > 150:
        stem, dot, suffix = value.rpartition(".")
        if dot and len(suffix) <= 15:
            value = stem[:149 - len(suffix)].rstrip(" .") + dot + suffix
        else:
            value = value[:150].rstrip(" .")
    return value


def _clean_body(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = "".join(c for c in value if c in "\n\t" or unicodedata.category(c) not in {"Cc", "Cf"})
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in value.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


class _VisibleHTML(HTMLParser):
    _HIDDEN = {"head", "script", "style", "template", "noscript", "iframe", "object", "svg", "canvas"}
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    _BLOCK = {"address", "article", "aside", "blockquote", "div", "dl", "dt", "dd", "fieldset", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table", "tr", "ul"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.text = []

    def _hidden(self):
        return bool(self.stack and self.stack[-1][1])

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        hidden = (self._hidden() or tag in self._HIDDEN or "hidden" in attributes
                  or str(attributes.get("aria-hidden", "")).casefold() == "true"
                  or bool(re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden|mso-hide\s*:\s*all|opacity\s*:\s*0(?:\.0+)?(?:\s*!important)?\s*(?:;|$))",
                                    attributes.get("style") or "", re.I)))
        if not hidden:
            if tag in self._BLOCK or tag == "br":
                self.text.append("\n")
            elif tag in {"td", "th"}:
                self.text.append(" ")
        if tag not in self._VOID:
            self.stack.append((tag, hidden))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        was_hidden = self._hidden()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if not was_hidden and tag in self._BLOCK:
            self.text.append("\n")

    def handle_data(self, data):
        if not self._hidden():
            self.text.append(data)


def _html_text(value: str) -> str:
    parser = _VisibleHTML()
    parser.feed(value)
    parser.close()
    return _clean_body("".join(parser.text))


def _payload_bytes(part: Message, *, attachment: bool = False) -> bytes:
    transfer_encoding = str(part.get("Content-Transfer-Encoding", "")).strip().lower()
    if attachment and transfer_encoding not in {"", "7bit", "8bit", "binary", "base64", "quoted-printable"}:
        raise ValueError("unsupported attachment content transfer encoding")
    decoded = part.get_payload(decode=True)
    if attachment and any(isinstance(defect, (InvalidBase64CharactersDefect,
                                               InvalidBase64LengthDefect,
                                               InvalidBase64PaddingDefect))
                          for defect in part.defects):
        raise ValueError("attachment content transfer decoding failed")
    if decoded is not None:
        return decoded
    payload = part.get_payload()
    if isinstance(payload, list):
        # An attached message is one .eml, not another body or attachment tree.
        return b"\r\n".join(child.as_bytes(policy=policy.SMTP) for child in payload)
    if isinstance(payload, str):
        try:
            return payload.encode("ascii", "surrogateescape")
        except UnicodeError:
            return payload.encode("utf-8")
    return b""


def _received_time(message: Message, received_at: str) -> str:
    if received_at:
        return received_at
    try:
        timestamp = parsedate_to_datetime(_header(message, "Date"))
        return timestamp.isoformat(timespec="seconds") if timestamp.tzinfo else ""
    except (TypeError, ValueError, OverflowError):
        return ""


def parse_message(raw: bytes, *, received_at: str, folder: str, source_url: str) -> dict:
    """Return decoded metadata, visible text and attachment bytes from one mail.

    ``received_at`` should be the collector's ISO-formatted IMAP INTERNALDATE;
    a timezone-bearing Date header is only used if that argument is empty.
    Attachment ids distinguish duplicate filenames and identical MIME parts.
    No actions, deadlines, file writes or network requests are generated here.
    """
    if not isinstance(raw, bytes):
        raise TypeError("raw must be RFC 822 bytes")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    internet_message_id = _header(message, "Message-ID")
    message_id = internet_message_id or f"sha256:{raw_sha256}"
    subject = _header(message, "Subject") or "（无主题）"
    plain_parts, html_parts, attachments = [], [], []
    part_index = 0

    def visit(part):
        nonlocal part_index
        part_index += 1
        index = part_index
        content_type = part.get_content_type().lower()
        is_attachment = (bool(part.get_filename()) or part.get_content_disposition() == "attachment"
                         or content_type in {"message/rfc822", "message/global"})
        if part.is_multipart() and not is_attachment:
            for child in part.get_payload():
                visit(child)
            return
        if part.get_content_maintype() == "multipart" and not part.is_multipart():
            # A broken container has no reliable attachment tree. Its bytes are
            # retained in the caller's raw message, not invented as a .bin file.
            return
        is_body = not is_attachment and content_type in {"text/plain", "text/html"}
        payload = _payload_bytes(part, attachment=not is_body)
        if is_body:
            decoded = _decode_bytes(payload, part.get_content_charset())
            if content_type == "text/plain":
                plain_parts.append(_clean_body(decoded))
            else:
                html_parts.append(_html_text(decoded))
            return
        name = _filename(part, index, content_type)
        digest = hashlib.sha256(payload).hexdigest()
        identity = f"{message_id}\x00{index}\x00{name}\x00{digest}".encode("utf-8")
        attachment = {"id": "attachment-" + hashlib.sha256(identity).hexdigest(),
                      "name": name, "content_type": content_type, "data": payload,
                      "size": len(payload), "sha256": digest}
        if not payload:
            # A present MIME part does not prove its file content was supplied.
            # Retain the empty bytes as evidence, but never claim completeness.
            attachment.update(status="missing", error="MIME_ATTACHMENT_EMPTY")
        attachments.append(attachment)

    visit(message)
    structure_complete = not any(isinstance(defect, _STRUCTURAL_DEFECTS)
                                 for part in message.walk() for defect in part.defects)
    texts = [text for text in plain_parts if text] or [text for text in html_parts if text]
    body_text = "\n\n".join(dict.fromkeys(texts))
    authentication_notice = bool(_AUTH_NOTICE.search("\n".join([subject, *plain_parts, *html_parts])))
    summary_text = re.sub(r"\s+", " ", body_text).strip()
    summary = summary_text[:200] + ("…" if len(summary_text) > 200 else "")
    headers_text = "\n".join(f"{name}: {value}" for name in _SAFE_HEADERS
                             if (value := _header(message, name)))
    if authentication_notice:
        subject = "认证通知（已跳过敏感内容）"
        summary = "认证通知，已跳过正文和附件归档。"
        body_text, headers_text, attachments = "", "", []
    return {"id": message_id, "received_at": _received_time(message, received_at),
            "sender": _header(message, "From"), "subject": subject, "folder": folder,
            "category": "待整理", "summary": summary, "source_url": source_url,
            "body_text": body_text, "headers_text": headers_text,
            "internet_message_id": internet_message_id, "attachments": attachments,
            "attachments_complete": structure_complete and all(attachment["size"] > 0 for attachment in attachments),
            "expected_attachment_count": len(attachments),
            "raw_sha256": raw_sha256, "authentication_notice": authentication_notice}
