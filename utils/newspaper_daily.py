"""Independent daily list delivery; only the private data repository is writable.

No article bodies enter this snapshot. Responses with unknown cache conditions,
no-store/private/no-cache, revalidation requirements or a finite freshness limit
stay in the live reader and are never committed into permanent Git history.
"""

from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from utils import github_backup_sync as sync
from utils import newspaper_ai_sources as ai
from utils import newspaper_data as base
from utils import newspaper_sources as media
from utils.newspaper_interviews import INTERVIEW_CATEGORY, is_recent_interview, without_expired_interviews


NEWSPAPER_DAILY_VERSION = 3
SNAPSHOT_PATH = "data/newspaper_daily.json"
PRIVATE_REPO = "yaoy2/yao_1-data"
PRIVATE_BRANCH = "main"
SHANGHAI = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
LOCAL_DIR = ROOT / ".local" / "newspaper"
MAX_AGE = timedelta(hours=48)
MAX_CONTENT_BYTES = 900_000  # Contents API base64 read-back stays below 1 MB.
MAX_ARTICLES = 1000
SOURCE_MAP = {source.id: source for source in (*base.SOURCES, *ai.AI_SOURCES, *media.PUBLIC_SOURCES)}
INACTIVE_MAP = {source["id"]: source for source in media.INACTIVE_SOURCES}
ARTICLE_FIELDS = frozenset({
    "id", "title", "original_title", "group", "category", "kind", "source", "publisher",
    "source_id", "source_family", "url", "original_url", "summary", "summary_origin",
    "content_origin", "published_at", "updated_at", "discovered_at", "time_basis",
    "date_precision", "time", "topic", "available", "summary_only", "restricted",
    "ai_category", "ai_section", "cache_policy",
})
SOURCE_FIELDS = frozenset({"id", "name", "scope", "status", "count", "fetched_count", "checked_at",
                           "error", "note", "source_family", "excluded_count"})
TOP_FIELDS = frozenset({"schema_version", "edition_date", "started_at", "completed_at", "generated_at",
                       "expires_at", "status", "article_count", "articles", "sources", "errors"})


def _now():
    return datetime.now(SHANGHAI)


def _date(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(SHANGHAI) if result.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def _text(value, maximum=300):
    return base._plain(value, maximum) if isinstance(value, str) else ""


def _family(source_id):
    if source_id in ai.SOURCE_BY_ID:
        return "ai_official"
    return "public_media" if source_id in media.SOURCE_BY_ID else "public_news"


def _safe_article_url(value, source_id):
    if not isinstance(value, str) or len(value) > 4096:
        return ""
    if source_id in ai.SOURCE_BY_ID:
        return ai._safe_url(value, ai.SOURCE_BY_ID[source_id])
    if source_id in media.SOURCE_BY_ID:
        return media._safe_url(value, media.SOURCE_BY_ID[source_id])
    if source_id not in SOURCE_MAP:
        return ""
    url = base._safe_url(value, article_only=True)
    # Base adapters share a URL checker; still require the declared publisher.
    from urllib.parse import urlsplit
    host = urlsplit(url).hostname or ""
    prefix = source_id.split("_", 1)[0]
    return url if ((prefix == "chinanews" and "chinanews" in host)
                   or (prefix == "cctv" and host.endswith(".cctv.com"))
                   or (prefix == "chinawriter" and "chinawriter" in host)) else ""


def _may_persist(article, state, feed):
    """Require observed policy evidence, with every applicable restriction winning."""
    policies = [value for value in (article.get("cache_policy"), state.get("cache_policy"))
                if isinstance(value, dict)]
    control = state.get("cache_control")
    observed = any(type(policy.get("store")) is bool and type(policy.get("reuse")) is bool for policy in policies) or isinstance(control, str)
    if not observed:
        return False
    # An aggregate combines other publishers' restrictions. A checked row/source
    # is evaluated independently; missing source evidence is rejected above.
    for policy in policies:
        if policy.get("store") is False or policy.get("reuse") is False:
            return False
        if policy.get("max_age_seconds") is not None or policy.get("expires_at") is not None:
            return False
    if isinstance(control, str):
        directives = {part.split("=", 1)[0].strip().lower() for part in control.split(",")}
        if directives & {"no-store", "private", "no-cache", "max-age", "s-maxage",
                         "must-revalidate", "proxy-revalidate"}:
            return False
    return True


def _list_article(article, state, feed, now):
    if not isinstance(article, dict) or not _may_persist(article, state, feed):
        return None
    source_id = article.get("source_id")
    if not isinstance(source_id, str) or source_id not in SOURCE_MAP:
        return None
    url = _safe_article_url(article.get("url"), source_id)
    dates = [_date(article.get(key)) for key in ("published_at", "updated_at", "discovered_at")]
    actual_date = next((value for value in dates if value is not None), None)
    max_days = getattr(SOURCE_MAP[source_id], "max_age_days", ai.MAX_AGE_DAYS)
    if not url or actual_date is None or not now - timedelta(days=max_days) <= actual_date <= now + timedelta(days=1):
        return None
    category = article.get("category")
    if category not in base.CATEGORY_GROUP or not _text(article.get("title")):
        return None
    if category == INTERVIEW_CATEGORY and not is_recent_interview(article, now):
        return None
    result = {key: deepcopy(value) for key, value in article.items() if key in ARTICLE_FIELDS}
    for key, value in list(result.items()):
        if isinstance(value, str) and key not in {"url", "original_url"}:
            result[key] = _text(value, 500 if key == "summary" else 300)
    family = _family(source_id)
    prefix = {"ai_official": "ai_official_", "public_media": "media_", "public_news": "news_"}[family]
    expected_id = prefix + hashlib.sha256(url.encode()).hexdigest()[:24]
    # These are the existing adapters' exact ID rules, not a new daily identity.
    if article.get("id") != expected_id:
        return None
    result.update(id=article["id"], url=url,
                  source=SOURCE_MAP[source_id].name, source_family=family,
                  group=base.CATEGORY_GROUP[category], available=False,
                  cache_policy={"store": True, "reuse": True})
    if "original_url" in result:
        result["original_url"] = _safe_article_url(result["original_url"], source_id) or url
    if family == "ai_official" or (family == "public_media" and source_id not in media.PUBLIC_ARTICLE_SOURCES):
        result["summary_only"] = True
    if result.get("content_origin") == "feed_full":
        result["content_origin"] = "source_summary"
    return result


def build_daily_snapshot(now=None):
    """Fetch lists once, preserving actual source checks and honest partial results."""
    started = now or _now()
    if started.tzinfo is None:
        raise ValueError("日报时间必须包含时区")
    started = started.astimezone(SHANGHAI)
    articles, sources, seen_ids, seen_urls = [], [], set(), {}
    loaders = (("public_news", base.load_newspaper_feed), ("ai_official", ai.load_ai_official_feed),
               ("public_media", media.load_extended_news_feed))
    for family, loader in loaders:
        try:
            feed = loader()
            if not isinstance(feed, dict) or not isinstance(feed.get("articles"), list) or not isinstance(feed.get("sources"), list):
                raise ValueError("invalid feed")
        except Exception:
            # Fixed labels only: exceptions may contain a URL, response or credential.
            feed = {"articles": [], "sources": [{"id": source.id, "name": source.name,
                    "status": "error", "count": 0, "error": "本次来源组读取失败",
                    "checked_at": (now or _now()).isoformat()}
                    for source in SOURCE_MAP.values() if _family(source.id) == family]}
        states = {state.get("id"): state for state in feed["sources"]
                  if isinstance(state, dict) and isinstance(state.get("id"), str)}
        accepted, excluded = Counter(), Counter()
        for article in feed["articles"]:
            if not isinstance(article, dict):
                continue
            source_id = article.get("source_id")
            if not isinstance(source_id, str) or source_id not in states or states[source_id].get("status") != "ok":
                continue
            row = _list_article(article, states[source_id], feed, started)
            if row is None:
                excluded[source_id] += 1
            elif row["id"] not in seen_ids and row["url"] not in seen_urls and len(articles) < MAX_ARTICLES:
                seen_urls[row["url"]] = len(articles)
                articles.append(row)
                seen_ids.add(row["id"])
                accepted[source_id] += 1
            elif row["url"] in seen_urls and row.get("category") == INTERVIEW_CATEGORY:
                index = seen_urls[row["url"]]
                if articles[index].get("category") != INTERVIEW_CATEGORY:
                    seen_ids.discard(articles[index]["id"])
                    articles[index] = row
                    seen_ids.add(row["id"])
                    accepted[source_id] += 1
        for source_id, state in states.items():
            if source_id not in SOURCE_MAP and source_id not in INACTIVE_MAP:
                continue
            status = state.get("status") if state.get("status") in {"ok", "error", "excluded"} else "error"
            name = SOURCE_MAP[source_id].name if source_id in SOURCE_MAP else INACTIVE_MAP[source_id]["name"]
            checked = _date(state.get("checked_at"))
            sources.append({"id": source_id, "name": name, "scope": _text(state.get("scope")),
                            "source_family": family, "status": status, "count": accepted[source_id],
                            "fetched_count": max(0, state.get("count", 0)) if type(state.get("count")) is int else 0,
                            "excluded_count": excluded[source_id],
                            "checked_at": checked.isoformat() if checked else "",
                            "error": "本次来源读取失败" if status == "error" else "",
                            "note": "仅保存缓存条件已确认且无需到期重验的列表摘要；其余内容可手动实时读取。"
                                    if excluded[source_id] else _text(state.get("note"))})
    # A dedicated interview may replace a duplicate from an earlier source group.
    final_counts = Counter(article["source_id"] for article in articles)
    for state in sources:
        state["count"] = final_counts[state["id"]]
    completed = (now or _now()).astimezone(SHANGHAI)
    articles.sort(key=lambda row: row.get("published_at") or row.get("updated_at") or row.get("discovered_at") or "", reverse=True)
    errors = [state["name"] + "：" + state["error"] for state in sources if state["status"] == "error"]
    snapshot = {"schema_version": 1, "edition_date": started.date().isoformat(), "started_at": started.isoformat(),
            "completed_at": completed.isoformat(), "generated_at": completed.isoformat(),
            "expires_at": (completed + MAX_AGE).isoformat(), "status": ("partial" if errors else "ok") if articles else "failed",
            "article_count": len(articles), "articles": articles, "sources": sources, "errors": errors}
    # Drop oldest list entries before publishing if a very full edition would
    # exceed GitHub's reliably readable base64 payload size. Never truncate JSON.
    while articles and len(_snapshot_text(snapshot).encode("utf-8")) > MAX_CONTENT_BYTES:
        removed = articles.pop()
        snapshot["article_count"] -= 1
        for state in sources:
            if state["id"] == removed["source_id"]:
                state["count"] -= 1
                state["excluded_count"] += 1
                state["note"] = "本期列表已按可读回的文件大小上限裁剪；可手动更新读取实时内容。"
                break
    if not articles:
        snapshot["status"] = "failed"
    return snapshot


def _snapshot_text(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def validate_daily_snapshot(payload):
    """Return a checked copy, or raise ValueError; never trust remote list URLs."""
    if isinstance(payload, (str, bytes)):
        if len(payload.encode("utf-8") if isinstance(payload, str) else payload) > MAX_CONTENT_BYTES:
            raise ValueError("日报快照过大")
        try:
            payload = json.loads(payload)
        except (ValueError, UnicodeError) as error:
            raise ValueError("日报快照不是有效 JSON") from error
    if not isinstance(payload, dict) or set(payload) != TOP_FIELDS or type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise ValueError("日报快照结构无效")
    try:
        if len(_snapshot_text(payload).encode("utf-8")) > MAX_CONTENT_BYTES:
            raise ValueError("日报快照过大")
    except (TypeError, RecursionError) as error:
        raise ValueError("日报快照结构无效") from error
    start, complete, generated, expires = [_date(payload[key]) for key in ("started_at", "completed_at", "generated_at", "expires_at")]
    if (None in (start, complete, generated, expires) or start > complete or complete != generated
            or not complete < expires <= complete + MAX_AGE or payload["edition_date"] != start.date().isoformat()):
        raise ValueError("日报时间无效")
    articles, sources = payload["articles"], payload["sources"]
    if (not isinstance(articles, list) or len(articles) > MAX_ARTICLES or not isinstance(sources, list) or len(sources) > 80
            or type(payload["article_count"]) is not int or payload["article_count"] != len(articles)
            or payload["status"] not in {"ok", "partial", "failed"}
            or (bool(articles) != (payload["status"] != "failed"))):
        raise ValueError("日报计数或状态无效")
    source_ids, counts = set(), Counter()
    for state in sources:
        if not isinstance(state, dict) or set(state) != SOURCE_FIELDS:
            raise ValueError("日报来源结构无效")
        source_id = state["id"]
        if (not isinstance(source_id, str) or source_id in source_ids or source_id not in SOURCE_MAP and source_id not in INACTIVE_MAP
                or state["status"] not in {"ok", "error", "excluded"}
                or any(type(state[key]) is not int or state[key] < 0 for key in ("count", "fetched_count", "excluded_count"))
                or state["count"] + state["excluded_count"] > state["fetched_count"]
                or any(not isinstance(value, str) or len(value) > 500 for key, value in state.items()
                       if key not in {"count", "fetched_count", "excluded_count"})):
            raise ValueError("日报来源内容无效")
        checked = _date(state["checked_at"])
        if state["checked_at"] and (checked is None or checked > complete + timedelta(minutes=5)):
            raise ValueError("日报来源时间无效")
        source_ids.add(source_id)
    ids, urls = set(), set()
    for article in articles:
        if not isinstance(article, dict) or set(article) - ARTICLE_FIELDS:
            raise ValueError("日报含非列表字段")
        sid, url = article.get("source_id"), article.get("url")
        if (not isinstance(sid, str) or sid not in source_ids or not isinstance(url, str)
                or _safe_article_url(url, sid) != url or article.get("source_family") != _family(sid)
                or article.get("cache_policy") != {"store": True, "reuse": True}
                or article.get("available") is not False):
            raise ValueError("日报来源或链接无效")
        for key, value in article.items():
            if key == "cache_policy":
                continue
            if key in {"available", "summary_only", "restricted"}:
                if not isinstance(value, bool):
                    raise ValueError("日报布尔字段无效")
            elif not isinstance(value, str) or len(value) > (4096 if key in {"url", "original_url"} else 1200):
                raise ValueError("日报文字字段无效")
        prefix = {"ai_official": "ai_official_", "public_media": "media_", "public_news": "news_"}[_family(sid)]
        expected_id = prefix + hashlib.sha256(url.encode()).hexdigest()[:24]
        if article.get("id") != expected_id or expected_id in ids or url in urls or not article.get("title", "").strip():
            raise ValueError("日报条目标识无效或重复")
        category = article.get("category")
        if category not in base.CATEGORY_GROUP or article.get("group") != base.CATEGORY_GROUP[category]:
            raise ValueError("日报分类无效")
        if article.get("original_url") and _safe_article_url(article["original_url"], sid) != article["original_url"]:
            raise ValueError("日报原文链接无效")
        dates = [_date(article.get(key)) for key in ("published_at", "updated_at", "discovered_at")]
        if any(article.get(key) and _date(article[key]) is None for key in ("published_at", "updated_at", "discovered_at")):
            raise ValueError("日报条目时间无效")
        dated = next((value for value in dates if value is not None), None)
        if dated is None or dated > complete + timedelta(days=1) or dated < complete - timedelta(days=366):
            raise ValueError("日报条目时间无效")
        ids.add(expected_id)
        urls.add(url)
        counts[sid] += 1
    if any(state["count"] != counts[state["id"]] or (state["count"] and state["status"] != "ok") for state in sources):
        raise ValueError("日报来源计数不一致")
    errors = [state["name"] + "：" + state["error"] for state in sources if state["status"] == "error"]
    if payload["errors"] != errors or (articles and payload["status"] != ("partial" if errors else "ok")):
        raise ValueError("日报错误状态不一致")
    return deepcopy(payload)


def feed_from_daily_snapshot(snapshot, now=None):
    try:
        snapshot = validate_daily_snapshot(snapshot)
    except (TypeError, ValueError, KeyError):
        return None
    current = now or _now()
    if (not snapshot["articles"] or _date(snapshot["expires_at"]) <= current
            or _date(snapshot["completed_at"]) > current + timedelta(minutes=5)):
        return None
    articles = without_expired_interviews(snapshot["articles"], current)
    return {"articles": articles, "sources": snapshot["sources"], "errors": snapshot["errors"],
            "fetched_at": snapshot["completed_at"], "generated_at": snapshot["generated_at"],
            "started_at": snapshot["started_at"], "completed_at": snapshot["completed_at"],
            "delivery": "daily", "edition_date": snapshot["edition_date"], "expires_at": snapshot["expires_at"],
            "daily_status": snapshot["status"], "cache_policy": {"store": True, "reuse": True},
            "delivery_note": "定时快照仅含可保存的列表摘要；手动更新可读取全部实时来源。"}


def _private_config(secrets, environ):
    config = sync.get_backup_sync_config(secrets, environ)
    if config["repo"].casefold() != PRIVATE_REPO.casefold() or config["branch"] != PRIVATE_BRANCH:
        raise ValueError("wrong_private_target")
    if not config["enabled"]:
        raise ValueError("missing_auth")
    return config


def _verify_private_repository(config):
    session = sync._session(config, None)
    response = session.get(f"{sync.API_ROOT}/repos/{PRIVATE_REPO}", headers={
        "Accept": "application/vnd.github+json", "Authorization": f"Bearer {config['token']}",
        "X-GitHub-Api-Version": "2022-11-28"}, timeout=20, allow_redirects=False)
    if response.status_code != 200:
        raise ValueError("private_repository_unconfirmed")
    metadata = response.json()
    if metadata.get("private") is not True or str(metadata.get("full_name", "")).casefold() != PRIVATE_REPO.casefold():
        raise ValueError("private_repository_unconfirmed")


def read_daily_feed(secrets=None, environ=None):
    """Read valid remote delivery only. Missing, failed, bad or expired -> None."""
    try:
        _private_config(secrets, environ)
        remote = sync.read_file_from_github(SNAPSHOT_PATH, secrets=secrets, environ=environ)
        return feed_from_daily_snapshot(remote["content"]) if remote.get("ok") else None
    except Exception:
        return None


@contextmanager
def _run_lock(directory):
    """OS locks release on process death, so a stale marker cannot block tomorrow."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "daily.lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("daily_locked") from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, suffix=".tmp", delete=False) as handle:
        handle.write(_snapshot_text(payload))
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _failure_reason(error):
    known = {"daily_locked", "missing_remote_version", "newer_remote_snapshot", "remote_unavailable",
             "private_repository_unconfirmed", "missing_auth", "wrong_private_target",
             "publish_unconfirmed", "readback_unconfirmed"}
    return str(error) if str(error) in known else "daily_operation_failed"


@contextmanager
def _reported_run_lock(directory, report):
    with _run_lock(directory):
        try:
            yield
        except Exception as error:
            report["reason"] = _failure_reason(error)
            raise
        finally:
            # Write completion while still owning the lock. An older process
            # must not overwrite the next process's newer completion report.
            report["completed_at"] = _now().isoformat()
            try:
                _atomic_json(directory / "last_run.json", report)
            except OSError:
                pass


def run_daily(dry_run=True, secrets=None, environ=None, force=False):
    """Default is no remote write. Publish uses a fresh SHA and read-back proof."""
    started = _now().astimezone(SHANGHAI)
    cycle_start = started.replace(hour=9, minute=0, second=0, microsecond=0)
    if started < cycle_start:
        cycle_start -= timedelta(days=1)
    report = {"ok": False, "mode": "dry_run" if dry_run else "publish", "status": "failed",
              "started_at": started.isoformat(), "completed_at": "", "edition_date": started.date().isoformat(),
              "cycle_start_at": cycle_start.isoformat(),
              "article_count": 0, "source_count": 0, "source_errors": 0, "excluded_count": 0,
              "path": SNAPSHOT_PATH, "reason": ""}
    try:
        with _reported_run_lock(LOCAL_DIR, report):
            remote, previous = None, None
            if not dry_run:
                _verify_private_repository(_private_config(secrets, environ))
                remote = sync.read_file_from_github(SNAPSHOT_PATH, secrets=secrets, environ=environ)
                if remote.get("ok"):
                    previous = validate_daily_snapshot(remote["content"])
                    if not remote.get("sha"):
                        raise ValueError("missing_remote_version")
                    if _date(previous["completed_at"]) > started:
                        raise ValueError("newer_remote_snapshot")
                    # A pre-09:00 installation check must not consume today's
                    # scheduled update. Deduplicate within the Beijing 09:00 cycle.
                    if _date(previous["completed_at"]) >= cycle_start and previous["articles"] and not force:
                        report.update(ok=True, status="already_published", article_count=previous["article_count"],
                                      edition_date=previous["edition_date"],
                                      snapshot_completed_at=previous["completed_at"], snapshot_status=previous["status"],
                                      source_count=len(previous["sources"]), source_errors=len(previous["errors"]),
                                      excluded_count=sum(state["excluded_count"] for state in previous["sources"]),
                                      reason="same_beijing_cycle")
                        return report
                elif remote.get("reason") != "missing_remote_file":
                    raise ValueError("remote_unavailable")
            snapshot = validate_daily_snapshot(build_daily_snapshot())
            report.update(article_count=snapshot["article_count"], source_count=len(snapshot["sources"]),
                          source_errors=len(snapshot["errors"]), excluded_count=sum(s["excluded_count"] for s in snapshot["sources"]),
                          snapshot_completed_at=snapshot["completed_at"], snapshot_status=snapshot["status"])
            if not snapshot["articles"]:
                report.update(reason="no_eligible_articles")
                return report
            if previous and _date(snapshot["completed_at"]) <= _date(previous["completed_at"]):
                raise ValueError("newer_remote_snapshot")
            if dry_run:
                report.update(ok=True, status="dry_run", reason="validated_without_publishing")
                return report
            local = LOCAL_DIR / "pending_snapshot.json"
            _atomic_json(local, snapshot)
            outcome = sync.sync_file_to_github(local, SNAPSHOT_PATH, "data: update newspaper daily " + snapshot["edition_date"],
                                               secrets=secrets, environ=environ,
                                               expected_sha=remote.get("sha") if remote.get("ok") else None)
            if not outcome.get("ok"):
                raise ValueError("publish_unconfirmed")
            verified = sync.read_file_from_github(SNAPSHOT_PATH, secrets=secrets, environ=environ)
            if (not verified.get("ok") or verified.get("sha") != outcome.get("sha")
                    or validate_daily_snapshot(verified.get("content")) != snapshot):
                raise ValueError("readback_unconfirmed")
            _atomic_json(LOCAL_DIR / "last_success.json", snapshot)
            local.unlink(missing_ok=True)
            report.update(ok=True, status="published", reason="verified_remote_readback")
            return report
    except Exception as error:
        report["reason"] = _failure_reason(error)
        return report
    finally:
        if not report["completed_at"]:
            report["completed_at"] = _now().isoformat()
