"""Private, uncached CAS transport for M28 reading records and preferences.

The browser owns three-way merging. This module validates complete documents,
never truncates personal material, and performs all compression in memory.
"""

import base64
from datetime import datetime
from email.utils import parsedate_to_datetime
import gzip
import hashlib
import hmac
import json
import math
import re
from urllib.parse import urlsplit
import zlib

from utils import github_backup_sync as sync


READER_PATH = "data/newspaper_reader.json"
PRIVATE_REPO = "yaoy2/yao_1-data"
PRIVATE_BRANCH = "main"
MAX_FILE_BYTES = 900_000
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 20_000
MAX_PARAGRAPHS = 1000
MAX_PARAGRAPH_CHARS = 20_000
MAX_PROFILE_EVENTS = 600
MAX_HIDDEN_IDS = 2000
UNSAFE_KEYS = frozenset({"__proto__", "prototype", "constructor"})
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,179}\Z")
SHA_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
FOLDERS = frozenset({"未分类", "工作资料", "长读收藏", "书影资料"})
MARKS = frozenset({"", "待读", "重要", "待核实"})
ARTICLE_TEXT_FIELDS = frozenset({"title", "group", "category", "kind", "source", "source_id", "source_family",
                               "publisher", "summary", "topic", "summary_origin", "content_origin", "ai_category", "ai_section"})
ARTICLE_DATE_FIELDS = frozenset({"published_at", "updated_at", "discovered_at"})
ARTICLE_METADATA_FIELDS = frozenset({"attribution", "links", "canonical", "attributions", "rights", "license", "notice"})
ARTICLE_FIELDS = ARTICLE_TEXT_FIELDS | ARTICLE_DATE_FIELDS | ARTICLE_METADATA_FIELDS | {
    "id", "time_basis", "date_precision", "url", "summary_only"}
DETAIL_FIELDS = frozenset({"id", "status", "paragraphs", "source", "url", "title", "published_at", "content_origin", "message"})
RECORD_FIELDS = frozenset({"article", "saved", "hidden", "read", "mark", "note", "tags", "folder", "saved_at", "detail"})
LIBRARY_FIELDS = frozenset({"version", "records", "pins", "pinsCustomized", "following", "lastArticle", "lastRead", "design"})
RECOMMENDATION_FIELDS = frozenset({"version", "personalized", "strength", "diversity", "profile"})
ENVELOPE_FIELDS = frozenset({"format", "version", "encoding", "uncompressed_bytes", "sha256", "data"})

MESSAGES = {
    "auth": "尚未配置阅读资料同步凭据；本地资料保留。",
    "target": "阅读资料同步目标不符合指定私有仓库配置；本地资料保留。",
    "private": "未能确认目标仓库为指定私有仓库，已停止同步。",
    "schema": "阅读资料包含不受支持的结构、字段或值；未截断或改写本地资料。",
    "size": "阅读资料超过同步容量上限（解压后 10 MiB、存储文件 900 KB），未截断或改写本地资料。",
    "records": "阅读资料超过 20000 条记录上限，未截断或改写本地资料。",
    "remote": "云端阅读资料格式或版本无法验证，已停止覆盖；本地资料保留。",
    "read": "暂时无法读取云端阅读资料；本地资料保留，可稍后重试。",
    "write": "云端保存结果尚未确认；本地资料保留，请先重新读取云端再重试。",
    "verify": "云端读回内容或版本与本次保存不一致；本地资料保留，请重新读取并合并。",
    "conflict": "其他设备已更新云端资料，本次未覆盖；请先合并最新版本。",
}


class _SyncFailure(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(MESSAGES[code])


def _require(condition, code="schema"):
    if not condition:
        raise _SyncFailure(code)


def _keys(value, allowed, required=None):
    _require(type(value) is dict and set(value) <= allowed and (required or set()) <= set(value))


def _string(value, maximum, *, nonempty=False):
    _require(type(value) is str and len(value) <= maximum and (not nonempty or bool(value.strip())))


def _id(value):
    _require(type(value) is str and value not in UNSAFE_KEYS and bool(ID_PATTERN.fullmatch(value)))


def _version(value):
    _require(type(value) is int and value == 1)


def _url(value):
    _string(value, 8192)
    if not value:
        return
    _require(not re.search(r"[\x00-\x20\x7f\\]", value))
    try:
        parsed = urlsplit(value)
        _require(parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)
                 and parsed.username is None and parsed.password is None
                 and (parsed.port is None or 0 < parsed.port <= 65535))
    except ValueError as error:
        raise _SyncFailure("schema") from error


def _date(value):
    if value is None:
        return
    _string(value, 100, nonempty=True)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return
    except ValueError:
        pass
    try:
        parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise _SyncFailure("schema") from error


def _safe_tree(document):
    """Reject unsafe keys, non-JSON values, cycles and excessive nesting early."""
    stack, ancestors, nodes = [(document, 0, False)], set(), 0
    while stack:
        value, depth, leaving = stack.pop()
        if leaving:
            ancestors.remove(id(value))
            continue
        nodes += 1
        _require(depth <= 16 and nodes <= 1_000_000, "size")
        if type(value) in {dict, list}:
            _require(id(value) not in ancestors)
            ancestors.add(id(value))
            stack.append((value, depth, True))
            if type(value) is dict:
                _require(all(type(key) is str and key not in UNSAFE_KEYS for key in value))
                stack.extend((child, depth + 1, False) for child in value.values())
            else:
                stack.extend((child, depth + 1, False) for child in value)
        elif type(value) is float:
            _require(math.isfinite(value))
        else:
            _require(value is None or type(value) in {str, int, bool})


def _metadata(value, depth=0, *, urls=False):
    _require(depth <= 4)
    if value is None or type(value) is bool:
        return
    if type(value) is str:
        _string(value, 2000)
        if urls:
            _url(value)
    elif type(value) in {int, float}:
        _require(math.isfinite(value) and abs(value) <= 1e100)
    elif type(value) is list:
        _require(len(value) <= 20)
        for child in value:
            _metadata(child, depth + 1, urls=urls)
    else:
        _require(type(value) is dict and len(value) <= 20)
        for key, child in value.items():
            _string(key, 80, nonempty=True)
            is_url = key.lower() in {"url", "uri", "href", "link", "canonical"} or key.lower().endswith("_url")
            named_target = key.lower() in {"original", "source", "article", "story", "item", "api", "web", "html", "json", "feed", "homepage", "download"}
            # Link objects can contain titles, labels and descriptions alongside
            # URLs. Keep that prose intact; validate only URL-bearing members.
            _metadata(child, depth + 1, urls=is_url or (urls and (named_target or type(child) in {dict, list})))


def _article(article):
    _keys(article, ARTICLE_FIELDS, {"id", "title"})
    _id(article["id"])
    for key in ARTICLE_TEXT_FIELDS & article.keys():
        _string(article[key], 32000 if key == "summary" else 2000, nonempty=key == "title")
    for key in ARTICLE_DATE_FIELDS & article.keys():
        _date(article[key])
    for key in ARTICLE_METADATA_FIELDS & article.keys():
        _metadata(article[key], urls=key in {"links", "canonical"})
    if "url" in article:
        _url(article["url"])
    if "summary_only" in article:
        _require(type(article["summary_only"]) is bool)
    if "time_basis" in article:
        _require(article["time_basis"] in {"published", "updated", "collected"})
    if "date_precision" in article:
        _require(article["date_precision"] in {"day", "minute"})


def _detail(detail, article):
    _keys(detail, DETAIL_FIELDS, {"id", "status", "paragraphs"})
    _require(detail["id"] == article["id"] and detail["status"] in {"full", "summary", "error"})
    paragraphs = detail["paragraphs"]
    _require(type(paragraphs) is list and len(paragraphs) <= MAX_PARAGRAPHS)
    for paragraph in paragraphs:
        _string(paragraph, MAX_PARAGRAPH_CHARS)
    if detail["status"] == "full":
        _require(bool(paragraphs) and article.get("summary_only") is not True)
    if "url" in detail:
        _url(detail["url"])
    if "published_at" in detail:
        _date(detail["published_at"])
    for key in {"source", "title", "content_origin", "message"} & detail.keys():
        _string(detail[key], 2000)


def _unique_strings(values, maximum, *, identifiers=False):
    _require(type(values) is list and len(values) <= maximum)
    for value in values:
        _id(value) if identifiers else _string(value, 100, nonempty=True)
    _require(len(set(values)) == len(values))


def _library(library):
    _keys(library, LIBRARY_FIELDS, LIBRARY_FIELDS)
    _version(library["version"])
    records = library["records"]
    _require(type(records) is dict)
    _require(len(records) <= MAX_RECORDS, "records")
    for article_id, record in records.items():
        _id(article_id)
        _keys(record, RECORD_FIELDS, {"article"})
        _article(record["article"])
        _require(record["article"]["id"] == article_id)
        for key in {"saved", "hidden", "read"} & record.keys():
            _require(type(record[key]) is bool)
        for key, limit in (("note", 8000), ("tags", 500)):
            if key in record:
                _string(record[key], limit)
        if "folder" in record:
            _require(record["folder"] in FOLDERS)
        if "mark" in record:
            _require(record["mark"] in MARKS)
        if "saved_at" in record:
            _date(record["saved_at"])
        if record.get("detail") is not None:
            _detail(record["detail"], record["article"])
    _unique_strings(library["pins"], 100)
    _unique_strings(library["following"], 100, identifiers=True)
    _require(type(library["pinsCustomized"]) is bool)
    if library["lastArticle"] is not None:
        _article(library["lastArticle"])
    if library["lastRead"] is not None:
        _id(library["lastRead"])
    if library["lastArticle"] is not None:
        _require(library["lastArticle"]["id"] == library["lastRead"])
    design = library["design"]
    _keys(design, {"columns", "title", "read"}, {"columns", "title", "read"})
    for key, choices in (("columns", {2, 3, 4}), ("title", {15, 17, 19, 21}), ("read", {18, 20, 22, 24})):
        _require(type(design[key]) is int and design[key] in choices)


def _recommendations(recommendations):
    _keys(recommendations, RECOMMENDATION_FIELDS, RECOMMENDATION_FIELDS)
    _version(recommendations["version"])
    _require(type(recommendations["personalized"]) is bool
             and recommendations["strength"] in {"light", "balanced", "strong"}
             and recommendations["diversity"] in {"standard", "wide"})
    profile = recommendations["profile"]
    _keys(profile, {"version", "events", "hiddenIds"}, {"version", "events", "hiddenIds"})
    _version(profile["version"])
    _unique_strings(profile["hiddenIds"], MAX_HIDDEN_IDS, identifiers=True)
    events = profile["events"]
    _require(type(events) is list and len(events) <= MAX_PROFILE_EVENTS)
    seen = set()
    for event in events:
        _keys(event, {"id", "category", "group", "source", "type", "at"}, {"id", "category", "group", "source", "type", "at"})
        _id(event["id"])
        for key in ("category", "group", "source"):
            _string(event[key], 100, nonempty=True)
        _require(event["type"] in {"read", "save", "important", "dislike"}
                 and type(event["at"]) in {int, float} and math.isfinite(event["at"])
                 and 0 <= event["at"] <= 8_640_000_000_000_000)
        identity = (event["id"], event["type"])
        _require(identity not in seen)
        seen.add(identity)


def _json_bytes(document):
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def validate_reader_document(document):
    """Validate without repair or truncation; return a detached, exact JSON copy."""
    try:
        _safe_tree(document)
        _keys(document, {"version", "library", "recommendations"}, {"version", "library", "recommendations"})
        _version(document["version"])
        _library(document["library"])
        _recommendations(document["recommendations"])
        encoded = _json_bytes(document)
        _require(len(encoded) <= MAX_DOCUMENT_BYTES, "size")
        return json.loads(encoded)
    except _SyncFailure:
        raise
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise _SyncFailure("schema") from error


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result and key not in UNSAFE_KEYS)
        result[key] = value
    return result


def _parse_json(raw):
    def bad_constant(_value):
        raise _SyncFailure("schema")
    try:
        return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=bad_constant)
    except _SyncFailure:
        raise
    except (ValueError, UnicodeError, RecursionError) as error:
        raise _SyncFailure("schema") from error


def _encode_document(document):
    raw = _json_bytes(document)
    _require(len(raw) <= MAX_DOCUMENT_BYTES, "size")
    envelope = {"format": "newspaper-reader-state", "version": 1, "encoding": "gzip+base64",
                "uncompressed_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                "data": base64.b64encode(gzip.compress(raw, mtime=0)).decode("ascii")}
    encoded = _json_bytes(envelope)
    _require(len(encoded) <= MAX_FILE_BYTES, "size")
    return encoded


def _decode_document(raw):
    _require(type(raw) is bytes and len(raw) <= MAX_FILE_BYTES, "size")
    envelope = _parse_json(raw)
    # Accept a previously stored plain wire document if it fits the same file
    # size bound; subsequent writes consistently use the compressed envelope.
    if type(envelope) is dict and "library" in envelope:
        return validate_reader_document(envelope)
    _keys(envelope, ENVELOPE_FIELDS, ENVELOPE_FIELDS)
    _version(envelope["version"])
    _require(envelope["format"] == "newspaper-reader-state" and envelope["encoding"] == "gzip+base64")
    _require(type(envelope["uncompressed_bytes"]) is int and 0 < envelope["uncompressed_bytes"] <= MAX_DOCUMENT_BYTES, "size")
    _require(type(envelope["sha256"]) is str and bool(re.fullmatch(r"[0-9a-f]{64}", envelope["sha256"])))
    _string(envelope["data"], MAX_FILE_BYTES)
    try:
        compressed = base64.b64decode(envelope["data"], validate=True)
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        content = decoder.decompress(compressed, MAX_DOCUMENT_BYTES + 1)
        _require(len(content) <= MAX_DOCUMENT_BYTES and not decoder.unconsumed_tail, "size")
        _require(decoder.eof and not decoder.unused_data)
    except (ValueError, zlib.error) as error:
        if isinstance(error, _SyncFailure):
            raise
        raise _SyncFailure("schema") from error
    _require(len(content) == envelope["uncompressed_bytes"]
             and hmac.compare_digest(hashlib.sha256(content).hexdigest(), envelope["sha256"]))
    return validate_reader_document(_parse_json(content))


def _sha(value):
    _require(type(value) is str and bool(SHA_PATTERN.fullmatch(value)), "remote")
    return value


def _connection(secrets, environ, session):
    config = sync.get_backup_sync_config(secrets, environ)
    _require(config["repo"].casefold() == PRIVATE_REPO.casefold() and config["branch"] == PRIVATE_BRANCH, "target")
    _require(config["enabled"], "auth")
    transport = sync._session(config, session)
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {config['token']}",
               "X-GitHub-Api-Version": "2022-11-28", "Cache-Control": "no-cache, no-store"}
    response = transport.get(f"{sync.API_ROOT}/repos/{PRIVATE_REPO}", headers=headers, timeout=20, allow_redirects=False)
    _require(response.status_code == 200, "private")
    metadata = response.json()
    _require(type(metadata) is dict and metadata.get("private") is True
             and str(metadata.get("full_name", "")).casefold() == PRIVATE_REPO.casefold(), "private")
    return transport, headers


def _current(transport, headers):
    url = f"{sync.API_ROOT}/repos/{PRIVATE_REPO}/contents/{READER_PATH}"
    response = transport.get(url, headers=headers, params={"ref": PRIVATE_BRANCH}, timeout=20, allow_redirects=False)
    if response.status_code == 404:
        return None, None
    _require(response.status_code == 200, "read")
    payload = response.json()
    _require(type(payload) is dict and payload.get("encoding") == "base64", "remote")
    sha = _sha(payload.get("sha"))
    if "size" in payload:
        _require(type(payload["size"]) is int and 0 <= payload["size"] <= MAX_FILE_BYTES, "remote")
    content = payload.get("content")
    _require(type(content) is str and len(content) <= MAX_FILE_BYTES * 2, "remote")
    compact = "".join(content.split())
    _require(len(compact) <= ((MAX_FILE_BYTES + 2) // 3) * 4, "remote")
    try:
        decoded = base64.b64decode(compact, validate=True)
        if "size" in payload:
            _require(payload["size"] == len(decoded), "remote")
        document = _decode_document(decoded)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise _SyncFailure("remote") from error
    return document, sha


def _error(error, fallback):
    code = error.code if isinstance(error, _SyncFailure) else fallback
    return {"ok": False, "status": "error", "message": MESSAGES[code]}


def load_reader_state(secrets=None, environ=None, session=None):
    """Return a validated private document, or None when the file is absent."""
    try:
        transport, headers = _connection(secrets, environ, session)
        document, sha = _current(transport, headers)
        return {"ok": True, "status": "loaded", "document": document, "sha": sha}
    except Exception as error:
        return _error(error, "read")


def _conflict(transport, headers):
    document, sha = _current(transport, headers)
    return {"ok": False, "status": "conflict", "document": document, "sha": sha, "message": MESSAGES["conflict"]}


def save_reader_state(document, expected_sha, secrets=None, environ=None, session=None):
    """Compare a fresh version, write with CAS, then verify the exact read-back."""
    write_started = False
    try:
        transport, headers = _connection(secrets, environ, session)
        _require(expected_sha is None or type(expected_sha) is str and bool(SHA_PATTERN.fullmatch(expected_sha)))
        document = validate_reader_document(document)
        encoded = _encode_document(document)
        current, sha = _current(transport, headers)
        if sha != expected_sha:
            return {"ok": False, "status": "conflict", "document": current, "sha": sha, "message": MESSAGES["conflict"]}
        payload = {"message": "data: sync newspaper reading records", "branch": PRIVATE_BRANCH,
                   "content": base64.b64encode(encoded).decode("ascii")}
        if sha is not None:
            payload["sha"] = sha
        write_started = True
        response = transport.put(f"{sync.API_ROOT}/repos/{PRIVATE_REPO}/contents/{READER_PATH}",
                                 headers=headers, json=payload, timeout=20, allow_redirects=False)
        if response.status_code == 409:
            return _conflict(transport, headers)
        if response.status_code == 422:
            # A concurrent creation can be returned as 422 (missing SHA), not
            # 409. Only classify it as conflict after reading a changed version.
            latest, latest_sha = _current(transport, headers)
            if latest_sha != sha:
                return {"ok": False, "status": "conflict", "document": latest, "sha": latest_sha, "message": MESSAGES["conflict"]}
            raise _SyncFailure("write")
        _require(response.status_code in {200, 201}, "write")
        result = response.json()
        _require(type(result) is dict and type(result.get("content")) is dict, "write")
        new_sha = _sha(result["content"].get("sha"))
        verified, verified_sha = _current(transport, headers)
        _require(verified_sha == new_sha and verified == document, "verify")
        return {"ok": True, "status": "saved", "document": verified, "sha": verified_sha}
    except Exception as error:
        if write_started and isinstance(error, _SyncFailure) and error.code in {"read", "remote"}:
            return _error(_SyncFailure("verify"), "write")
        return _error(error, "write")
