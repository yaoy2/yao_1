"""Official AI RSS summaries, with no AIHOT content API or article fetching.

The ten source names/URLs are adapted from AIHOT's demonstration configuration:
https://github.com/KKKKhazix/AIHOT/blob/main/industry/sources.json
Original configuration license: https://github.com/KKKKhazix/AIHOT/blob/main/LICENSE
The license covers that configuration, not third-party publishers' articles.

MIT License
Copyright (c) 2026 数字生命卡兹克

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
from html import unescape
import re
import time
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import requests


SHANGHAI = timezone(timedelta(hours=8))
MAX_WORKERS = 3
MAX_ITEMS_PER_SOURCE = 10
MAX_AGE_DAYS = 60
MAX_RESPONSE_BYTES = 2_000_000
MAX_REQUEST_SECONDS = 18
REQUEST_TIMEOUT = (3.5, 7)
USER_AGENT = "NewspaperPersonalReader/1.0 (+official RSS summaries)"
SUMMARY_ORIGIN = "官方订阅摘要（保留原始语言）"
CONTENT_ORIGIN = "官方 RSS/Atom 摘要，未核验原文全文"
AI_SECTIONS = {"ai-models": "模型进展", "ai-products": "产品应用", "industry": "行业动态",
               "paper": "研究论文", "tip": "教程与观点"}
ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"


@dataclass(frozen=True)
class AISource:
    id: str
    name: str
    url: str
    hosts: tuple
    default_category: str


AI_SOURCES = (
    AISource("ai_openai", "OpenAI News", "https://openai.com/news/rss.xml", ("openai.com", "www.openai.com"), "industry"),
    AISource("ai_deepmind", "Google DeepMind", "https://deepmind.google/blog/rss.xml", ("deepmind.google",), "ai-models"),
    AISource("ai_google_research", "Google Research", "https://research.google/blog/rss/", ("research.google",), "paper"),
    AISource("ai_huggingface", "Hugging Face Blog", "https://huggingface.co/blog/feed.xml", ("huggingface.co",), "ai-products"),
    AISource("ai_microsoft_research", "Microsoft Research", "https://www.microsoft.com/en-us/research/feed/", ("www.microsoft.com", "microsoft.com"), "paper"),
    AISource("ai_aws_ml", "AWS Machine Learning Blog", "https://aws.amazon.com/blogs/machine-learning/feed/", ("aws.amazon.com",), "tip"),
    AISource("ai_github", "GitHub Blog · AI & ML", "https://github.blog/ai-and-ml/feed/", ("github.blog",), "ai-products"),
    AISource("ai_mistral", "Mistral AI", "https://mistral.ai/news/rss", ("mistral.ai",), "ai-models"),
    AISource("ai_bair", "Berkeley AI Research", "https://bair.berkeley.edu/blog/feed.xml", ("bair.berkeley.edu",), "paper"),
)
# Verified 2026-10-04: this feed returns no-store and is not compatible with the
# application's shared feed cache. Retain the source reference without polling.
INACTIVE_SOURCES = (
    AISource("ai_nvidia", "NVIDIA Blog", "https://blogs.nvidia.com/feed/", ("blogs.nvidia.com",), "industry"),
)
SOURCE_BY_ID = {source.id: source for source in AI_SOURCES}
ALLOWED_FEED_URLS = frozenset(source.url for source in AI_SOURCES)


def _now():
    return datetime.now(SHANGHAI)


def _plain(value, limit=1000):
    if not isinstance(value, str):
        return ""
    value = value[:20000]
    if "<" in value:
        soup = BeautifulSoup(value, "html.parser")
        for element in soup(["script", "style", "noscript", "iframe", "form", "button"]):
            element.decompose()
        value = soup.get_text(" ", strip=True)
    else:
        value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _safe_url(value, source):
    if not isinstance(value, str) or len(value) > 4096:
        return ""
    value = value.strip()
    if not value or re.search(r"[\x00-\x20\x7f\\]", value):
        return ""
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if (parts.scheme not in ("https", "http") or host not in source.hosts
                or parts.username is not None or parts.password is not None
                or parts.port not in (None, 443 if parts.scheme == "https" else 80)):
            return ""
        return urlunsplit(("https", host, parts.path or "/", parts.query, ""))
    except ValueError:
        return ""


def _date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if date.tzinfo is None:
        return None
    return date.astimezone(SHANGHAI)


def _classify(title, default):
    # The section is a transparent local title/source grouping, not an upstream
    # editorial recommendation, a model-generated judgement, or a numeric score.
    rules = (
        ("industry", r"\b(partner(?:ship)?|funding|acquisit\w*|policy|governance|office|investment)\b"),
        ("paper", r"\b(benchmark\w*|research|paper|evaluat\w*|study|studies)\b"),
        ("tip", r"\b(how to|tutorial|guide|walkthrough|best practices|getting started)\b"),
        ("ai-models", r"\b(model[s]?|LLM[s]?|GPT[- ]?\d|Gemini|Llama|language model[s]?)\b"),
        ("ai-products", r"\b(introducing|launch\w*|release\w*|copilot|application[s]?|tool[s]?)\b"),
    )
    for category, pattern in rules:
        if re.search(pattern, title, re.IGNORECASE):
            return category
    return default


class _SafeTreeBuilder(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        # Reject actual DTDs, while allowing literal examples inside CDATA (as
        # used by GitHub's feed). A text search would reject those valid feeds.
        raise ValueError("不支持含实体声明的订阅源")


def _parse_feed(content, source, now=None):
    now = now or _now()
    root = ET.fromstring(content, parser=ET.XMLParser(target=_SafeTreeBuilder()))
    if root.tag == "rss":
        nodes, atom = root.findall("./channel/item"), False
    elif root.tag == ATOM + "feed":
        nodes, atom = root.findall(ATOM + "entry"), True
    else:
        raise ValueError("官方订阅格式已变化")
    result, seen = [], set()
    for node in nodes[:300]:
        if atom:
            title = node.findtext(ATOM + "title")
            url = next((link.get("href") for link in node.findall(ATOM + "link")
                        if link.get("rel", "alternate") == "alternate"), "")
            raw_date = node.findtext(ATOM + "published")
            time_basis = "published" if raw_date else "updated"
            raw_date = raw_date or node.findtext(ATOM + "updated")
            summary = node.findtext(ATOM + "summary")
        else:
            title, url = node.findtext("title"), node.findtext("link")
            raw_date = node.findtext("pubDate") or node.findtext(DC + "date")
            time_basis = "published"
            summary = node.findtext("description")
        title, url, date = _plain(title, 300), _safe_url(url, source), _date(raw_date)
        if (not title or not url or date is None or url in seen
                or date < now - timedelta(days=MAX_AGE_DAYS) or date > now + timedelta(hours=12)):
            continue
        seen.add(url)
        category = _classify(title, source.default_category)
        result.append({
            "id": "ai_official_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
            "title": title, "original_title": title, "source": source.name, "publisher": source.name,
            "source_id": source.id, "source_family": "ai_official",
            "group": "科技与科学", "category": "AI与互联网", "kind": "报道",
            "ai_category": category, "ai_section": AI_SECTIONS[category],
            "url": url, "original_url": url, "summary": _plain(summary),
            "summary_origin": SUMMARY_ORIGIN, "content_origin": CONTENT_ORIGIN,
            "published_at": date.isoformat() if time_basis == "published" else "",
            "updated_at": date.isoformat() if time_basis == "updated" else "",
            "time_basis": time_basis, "date_precision": "minute",
            "time": ("更新 " if time_basis == "updated" else "") + date.strftime("%Y-%m-%d %H:%M"),
            "topic": "", "available": False, "summary_only": True,
        })
    result.sort(key=lambda row: row["published_at"] or row["updated_at"], reverse=True)
    return result[:MAX_ITEMS_PER_SOURCE]


def _fetch_source(source):
    # Only the fixed demonstration feed URLs can become request targets. No
    # article link, external redirect or user-controlled URL is ever fetched.
    if source.url not in ALLOWED_FEED_URLS or _safe_url(source.url, source) != source.url:
        raise ValueError("官方订阅网址不在允许范围内")
    deadline = time.monotonic() + MAX_REQUEST_SECONDS
    with requests.get(source.url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
                      allow_redirects=False, stream=True) as response:
        if 300 <= response.status_code < 400:
            raise ValueError("官方订阅发生跳转，未跟随跳转")
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError("官方订阅暂不可用")
        length = response.headers.get("Content-Length", "")
        if length.isdigit() and int(length) > MAX_RESPONSE_BYTES:
            raise ValueError("官方订阅响应过大")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=32768):
            if time.monotonic() >= deadline:
                raise TimeoutError("读取官方订阅超时")
            content.extend(chunk)
            if len(content) > MAX_RESPONSE_BYTES:
                raise ValueError("官方订阅响应过大")
        return bytes(content), response.headers.get("Cache-Control", "")


def _error_message(error):
    if isinstance(error, (requests.Timeout, TimeoutError)):
        return "读取官方订阅超时"
    if isinstance(error, requests.RequestException):
        return "官方订阅连接暂不可用"
    if isinstance(error, (ET.ParseError, UnicodeError)):
        return "官方订阅格式已变化"
    if isinstance(error, ValueError):
        return str(error)[:120]
    return "官方订阅暂不可用"


def _load_source(source, now):
    content, cache_control = _fetch_source(source)
    if "no-store" in cache_control.lower():
        return [], cache_control, "该官方订阅要求不缓存，本次未载入内容"
    articles = _parse_feed(content, source, now)
    return articles, cache_control, "" if articles else "最近 60 天无新条目"


def load_ai_official_feed():
    """Read at most ten feeds concurrently; failures never manufacture articles.

    No server-side cache or files are created here. Cache-Control is passed to
    callers, including no-store, so a UI need not retain prohibited copies.
    """
    started = _now()
    by_source, states = {}, {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        pending = {pool.submit(_load_source, source, started): source for source in AI_SOURCES}
        for future in as_completed(pending):
            source = pending[future]
            state = {"id": source.id, "name": source.name, "scope": "AI 官方订阅 · 近 60 天",
                     "status": "ok", "count": 0, "checked_at": _now().isoformat(), "error": "",
                     "source_family": "ai_official", "cache_control": "", "note": ""}
            try:
                articles, cache_control, note = future.result()
                by_source[source.id] = articles
                state.update(count=len(articles), cache_control=cache_control, note=note)
            except Exception as error:
                state.update(status="error", error=_error_message(error))
            states[source.id] = state
    articles, seen = [], set()
    for source in AI_SOURCES:
        for article in by_source.get(source.id, []):
            if article["url"] not in seen:
                seen.add(article["url"])
                articles.append(article)
    articles.sort(key=lambda row: row["published_at"] or row["updated_at"], reverse=True)
    sources = [states[source.id] for source in AI_SOURCES]
    controls = [state["cache_control"].lower() for state in sources if state["count"] > 0]
    return {"articles": articles, "sources": sources, "fetched_at": _now().isoformat(),
            "errors": [source["name"] + "：" + source["error"] for source in sources if source["status"] == "error"],
            "cache_policy": {"store": not any("no-store" in value for value in controls),
                             "reuse": not any("no-store" in value or "no-cache" in value for value in controls)}}


def fetch_ai_official_article(article_dict):
    """Return attributed official feed text only; never fetch article pages."""
    article = article_dict if isinstance(article_dict, dict) else {}
    source_id = article.get("source_id")
    source = SOURCE_BY_ID.get(source_id) if isinstance(source_id, str) else None
    url = _safe_url(article.get("url"), source) if source else ""
    summary = _plain(article.get("summary"))
    result = {"id": _plain(article.get("id"), 100), "status": "summary",
              "title": _plain(article.get("title"), 300), "source": source.name if source else "",
              "source_family": "ai_official", "url": url, "original_url": url, "summary_only": True,
              "published_at": _plain(article.get("published_at"), 50),
              "paragraphs": [summary] if summary else [], "summary_origin": SUMMARY_ORIGIN,
              "content_origin": CONTENT_ORIGIN,
              "message": "当前显示官方订阅摘要，保留原始语言；完整内容请打开原文。"}
    if not url:
        result.update(status="error", paragraphs=[], message="文章网址不在对应官方来源范围内")
    elif not summary:
        result["message"] = "官方订阅未提供摘要，请打开原文查看。"
    return result
