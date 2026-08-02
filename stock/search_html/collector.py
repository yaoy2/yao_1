from __future__ import annotations

import argparse
import html
import http.cookiejar
import json
import math
import os
import re
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit("缺少 beautifulsoup4。请执行：python -m pip install beautifulsoup4") from exc


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LATEST_PATH = DATA_DIR / "latest.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "zh-CN,zh;q=0.9",
}

XUEQIU_HOT_URL = "https://xueqiu.com/hot/stock"
XUEQIU_HOT_API = "https://stock.xueqiu.com/v5/stock/hot_stock/list.json"
XUEQIU_TAG_API = "https://xueqiu.com/query/v1/hot_event/symbol/tag.json"
TAOGUBA_BBS_URL = "https://www.tgb.cn/bbs/"
XUEQIU_SEARCH_PAGE = "https://xueqiu.com/k"
XUEQIU_SEARCH_API = "https://xueqiu.com/query/v1/search/status.json"
TAOGUBA_SEARCH_PAGE = "https://www.tgb.cn/search/search"
TAOGUBA_SEARCH_API = "https://www.tgb.cn/search/getSearchTopicResult"

SEARCH_WINDOW_DAYS = 7
XUEQIU_SEARCH_MAX_PAGES = 30  # 雪球公开搜索当前最多返回 300 条（每页 10 条）。
TAOGUBA_SEARCH_MAX_PAGES = 60  # 控制单次公开请求频率；达到上限时必须在页面提示不完整。

AI_THEME_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("AI营销", ("AI营销", "智能营销", "广告生成", "营销智能")),
    ("AI教育", ("AI教育", "智能教育", "教育大模型", "教学助手")),
    ("AI医疗", ("AI医疗", "医疗大模型", "智能医疗", "辅助诊断")),
    ("AI办公", ("AI办公", "办公软件", "办公助手", "企业智能助手")),
    ("AI Agent", ("AI Agent", "AI智能体", "智能体", "Agent能力", "Agent应用")),
    ("AI内容", ("AIGC", "内容生成", "生成式AI", "数字创意", "文生视频", "多模态应用")),
    ("AI软件", ("AI软件", "企业服务", "行业应用", "应用软件", "软件服务")),
    ("AI终端", ("AI手机", "AI眼镜", "AI PC", "智能终端", "端侧AI")),
    ("AI算力", ("AI算力", "算力", "CPO", "光模块", "服务器", "数据中心", "液冷")),
    ("AI芯片", ("AI芯片", "GPU", "人工智能芯片", "存储芯片")),
    ("AI安全", ("AI安全", "数据安全", "模型安全", "网络安全")),
]

GENERIC_AI_TERMS = (
    "AI应用",
    "人工智能",
    "大模型",
    "生成式AI",
    "AIGC",
    "智能体",
    "AI Agent",
    "AI+",
    "人工智能+",
)

GENERAL_TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("半导体", ("半导体", "芯片", "存储")),
    ("光通信", ("CPO", "光模块", "光通信")),
    ("机器人", ("机器人", "人形机器人")),
    ("人工智能", GENERIC_AI_TERMS + ("AI云", "AI硬件", "AI软件")),
    ("消费", ("消费", "食品", "白酒", "零售")),
    ("金融", ("银行", "证券", "保险")),
    ("资源", ("黄金", "有色", "稀土", "矿业")),
    ("新能源", ("新能源", "光伏", "储能", "锂电")),
]

TAOGUBA_DAILY_TOPIC_TERMS = (
    "复盘",
    "前瞻",
    "行情",
    "市场",
    "板块",
    "策略",
    "指数",
    "题材",
    "热点",
    "涨停",
    "跌停",
    "科技",
    "半导体",
    "芯片",
    "CPO",
    "算力",
    "机器人",
    "消费",
    "证券",
    "银行",
    "黄金",
    "AI",
    "人工智能",
)

# 只用于把正文里的公司名统一到证券代码，不代表项目对其 AI 属性作预设判断。
STOCK_ALIASES: dict[str, str] = {
    "传智教育": "SZ003032",
    "浪潮软件": "SH600756",
    "国新健康": "SZ000503",
    "天地在线": "SZ002995",
    "南天信息": "SZ000948",
    "久其软件": "SZ002279",
    "金桥信息": "SH603918",
    "天融信": "SZ002212",
    "格尔软件": "SH603232",
    "蓝色光标": "SZ300058",
    "昆仑万维": "SZ300418",
    "值得买": "SZ300785",
    "普元信息": "SH688118",
    "凯文教育": "SZ002659",
    "遥望科技": "SZ002291",
    "三维通信": "SZ002115",
    "流金科技": "BJ834021",
}


def now_local() -> datetime:
    return datetime.now().astimezone()


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def compact_excerpt(value: str, limit: int = 220) -> str:
    value = clean_text(value)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip("，。；：、 ") + "…"


def http_json(opener: urllib.request.OpenerDirector, url: str, referer: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={**HEADERS, "Accept": "application/json,text/plain,*/*", "Referer": referer},
    )
    with opener.open(request, timeout=25) as response:
        raw = response.read()
    if not raw:
        raise RuntimeError("接口返回空内容")
    return json.loads(raw.decode("utf-8", "replace"))


def http_text(opener: urllib.request.OpenerDirector, url: str, referer: str | None = None) -> str:
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    request = urllib.request.Request(url, headers=headers)
    with opener.open(request, timeout=25) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8", "replace")


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    return clean_text(BeautifulSoup(value, "html.parser").get_text(" "))


def timestamp_datetime(value: Any, tz: Any = None) -> datetime | None:
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp > 10_000_000_000:
        timestamp /= 1000
    try:
        return datetime.fromtimestamp(timestamp, tz=tz or now_local().tzinfo)
    except (OSError, OverflowError, ValueError):
        return None


def extract_search_mentions(text: str) -> list[dict[str, str]]:
    mentions: dict[str, dict[str, str]] = {}
    for name, market, code in re.findall(r"\$([^$()]{1,30})\((SH|SZ|BJ)(\d{6})\)\$", text or "", re.I):
        symbol = normalize_symbol(market + code)
        mentions[symbol] = {"symbol": symbol, "name": clean_text(name)}
    return list(mentions.values())


def search_engagement(engagement: float) -> tuple[float, str]:
    engagement = max(0.0, float(engagement or 0))
    score = round(math.log10(engagement + 1) * 25, 1)
    if engagement >= 100:
        return score, "high"
    if engagement >= 15:
        return score, "medium"
    return score, "low"


def chromium_executable() -> str | None:
    configured = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    candidates: list[Path] = [Path(configured)] if configured else []
    program_files = os.environ.get("ProgramFiles")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if program_files:
        candidates.extend(
            [
                Path(program_files) / "Google/Chrome/Application/chrome.exe",
                Path(program_files) / "Microsoft/Edge/Application/msedge.exe",
            ]
        )
    if program_files_x86:
        candidates.extend(
            [
                Path(program_files_x86) / "Google/Chrome/Application/chrome.exe",
                Path(program_files_x86) / "Microsoft/Edge/Application/msedge.exe",
            ]
        )
    if local_app_data:
        candidates.append(Path(local_app_data) / "Google/Chrome/Application/chrome.exe")
    candidates.extend(
        [
            Path("/usr/bin/chromium"),
            Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/google-chrome"),
        ]
    )
    return str(next((path for path in candidates if path.exists()), "")) or None


def search_xueqiu_live(query: str, start: datetime, end: datetime) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("缺少浏览器组件 playwright，无法处理雪球公开搜索页") from exc

    results: list[dict[str, Any]] = []
    pages_fetched = 0
    site_total = 0
    site_max_pages = 0
    reached_window_start = False
    limited_note = ""
    executable = chromium_executable()

    with sync_playwright() as playwright:
        launch_options: dict[str, Any] = {
            "headless": True,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if executable:
            launch_options["executable_path"] = executable
        browser = playwright.chromium.launch(**launch_options)
        try:
            page = browser.new_page(locale="zh-CN", user_agent=USER_AGENT)
            landing_url = XUEQIU_SEARCH_PAGE + "?" + urllib.parse.urlencode({"q": query})
            page.goto(landing_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_selector("input[name=queryKeywords]", state="attached", timeout=30_000)

            for page_no in range(1, XUEQIU_SEARCH_MAX_PAGES + 1):
                response = page.evaluate(
                    """async ({query, pageNo}) => {
                        const params = new URLSearchParams({
                            sortId: '2', q: query, count: '20', page: String(pageNo)
                        });
                        const reply = await fetch('/query/v1/search/status.json?' + params, {
                            credentials: 'include', headers: {'Accept': 'application/json,text/plain,*/*'}
                        });
                        return {
                            status: reply.status,
                            contentType: reply.headers.get('content-type') || '',
                            body: await reply.text()
                        };
                    }""",
                    {"query": query, "pageNo": page_no},
                )
                if response.get("status") != 200 or "json" not in response.get("contentType", "").lower():
                    limited_note = "雪球返回了访问限制页面，已停止继续翻页。"
                    break
                try:
                    payload = json.loads(response.get("body") or "{}")
                except json.JSONDecodeError:
                    limited_note = "雪球返回内容无法解析，已停止继续翻页。"
                    break

                items = payload.get("list") or payload.get("statuses") or []
                pages_fetched = page_no
                site_total = max(site_total, int(payload.get("count") or 0))
                site_max_pages = max(site_max_pages, int(payload.get("maxPage") or 0))
                page_dates: list[datetime] = []
                for item in items:
                    published = timestamp_datetime(item.get("created_at"), end.tzinfo)
                    if published:
                        page_dates.append(published)
                    if not published or not (start <= published <= end + timedelta(minutes=5)):
                        continue
                    user = item.get("user") or {}
                    item_id = clean_text(str(item.get("id") or ""))
                    target = clean_text(item.get("target"))
                    if target.startswith("http://") or target.startswith("https://"):
                        url = target
                    elif target.startswith("/"):
                        url = "https://xueqiu.com" + target
                    elif user.get("id") and item_id:
                        url = f"https://xueqiu.com/{user['id']}/{item_id}"
                    else:
                        url = landing_url
                    full_text = html_to_text(item.get("text") or item.get("description"))
                    excerpt = html_to_text(item.get("description")) or compact_excerpt(full_text, 280)
                    title = html_to_text(item.get("title")) or compact_excerpt(excerpt or full_text, 72) or "雪球公开讨论"
                    replies = int(item.get("reply_count") or item.get("comment_count") or 0)
                    retweets = int(item.get("retweet_count") or 0)
                    likes = int(item.get("like_count") or 0)
                    heat_score, heat_tier = search_engagement(replies * 2 + retweets * 1.5 + likes)
                    results.append(
                        {
                            "id": f"xq-search-{item_id or len(results) + 1}",
                            "kind": "post",
                            "source": "雪球",
                            "title": title,
                            "url": url,
                            "heat_score": heat_score,
                            "heat_tier": heat_tier,
                            "published_at": published.strftime("%Y-%m-%d %H:%M"),
                            "author": clean_text(user.get("screen_name")),
                            "excerpt": compact_excerpt(excerpt or full_text, 280),
                            "themes": general_topics(f"{title} {excerpt}"),
                            "mentions": extract_search_mentions(full_text),
                            "why": f"公开搜索结果；转发 {retweets}、评论 {replies}、点赞 {likes}。",
                            "metrics": {"retweets": retweets, "comments": replies, "likes": likes},
                            "evidence_count": 1,
                            "_time_key": published.timestamp(),
                        }
                    )

                if not items:
                    reached_window_start = True
                    break
                if page_dates and max(page_dates) < start:
                    reached_window_start = True
                    break
                if site_max_pages and page_no >= site_max_pages:
                    reached_window_start = True
                    break
                page.wait_for_timeout(80)
        finally:
            browser.close()

    truncated = bool(
        limited_note
        or (
            not reached_window_start
            and pages_fetched >= XUEQIU_SEARCH_MAX_PAGES
            and (not site_max_pages or site_max_pages >= XUEQIU_SEARCH_MAX_PAGES)
        )
    )
    if truncated and not limited_note:
        limited_note = "近7天结果触及雪球公开搜索最多300条的返回上限。"
    return {
        "results": results,
        "status": {
            "source": "雪球",
            "status": "limited" if truncated else "ok",
            "complete": not truncated,
            "pages_fetched": pages_fetched,
            "site_total": site_total,
            "note": limited_note or f"已按最新顺序翻页至7天边界，共读取 {pages_fetched} 页。",
        },
    }


def taoguba_search_json(opener: urllib.request.OpenerDirector, url: str, referer: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            **HEADERS,
            "Accept": "application/json,text/javascript,*/*;q=0.01",
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with opener.open(request, timeout=25) as response:
        raw = response.read()
    if not raw:
        raise RuntimeError("淘股吧搜索接口返回空内容")
    return json.loads(raw.decode("utf-8", "replace"))


def search_taoguba_live(query: str, start: datetime, end: datetime) -> dict[str, Any]:
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    referer = TAOGUBA_SEARCH_PAGE + "?" + urllib.parse.urlencode({"searchContent": query, "type": 0})
    http_text(opener, referer, "https://www.tgb.cn/")

    results: list[dict[str, Any]] = []
    pages_fetched = 0
    site_total = 0
    site_max_pages = 0
    reached_window_start = False
    limited_note = ""

    for page_no in range(1, TAOGUBA_SEARCH_MAX_PAGES + 1):
        params = urllib.parse.urlencode(
            {
                "pageNo": page_no,
                "searchDate": 6,  # 站点最小选项为“半年内”，本地再精确截取7×24小时。
                "subject": query,
                "type": 1,  # 最新发布
            }
        )
        payload = taoguba_search_json(opener, f"{TAOGUBA_SEARCH_API}?{params}", referer)
        if payload.get("status") is False:
            limited_note = clean_text(payload.get("errorMessage")) or "淘股吧限制了继续访问。"
            break
        dto = payload.get("dto") or {}
        items = dto.get("topicAttr") or []
        pages_fetched = page_no
        site_total = max(site_total, int(dto.get("totalNum") or dto.get("topicTotalNum") or 0))
        site_max_pages = max(site_max_pages, int(dto.get("totalPageNum") or 0))
        page_dates: list[datetime] = []

        for item in items:
            published = timestamp_datetime(item.get("postDate"), end.tzinfo)
            if published:
                page_dates.append(published)
            if not published or not (start <= published <= end + timedelta(minutes=5)):
                continue
            title = clean_text(item.get("subject")) or "淘股吧公开讨论"
            excerpt = compact_excerpt(html_to_text(item.get("body")), 280)
            views = int(item.get("totalViewNum") or 0)
            comments = int(item.get("totalReplyNum") or 0)
            likes = int(item.get("usefulNum") or 0)
            heat_score, heat_tier = taoguba_heat(views, comments)
            topic_id = clean_text(str(item.get("newTopicID") or ""))
            results.append(
                {
                    "id": f"tgb-search-{topic_id or len(results) + 1}",
                    "kind": "post",
                    "source": "淘股吧",
                    "title": title,
                    "url": f"https://www.tgb.cn/a/{urllib.parse.quote(topic_id)}" if topic_id else referer,
                    "heat_score": heat_score,
                    "heat_tier": heat_tier,
                    "published_at": published.strftime("%Y-%m-%d %H:%M"),
                    "author": clean_text(item.get("userName")),
                    "excerpt": excerpt,
                    "themes": general_topics(f"{title} {excerpt}"),
                    "mentions": extract_search_mentions(f"{title} {excerpt}"),
                    "why": f"公开搜索结果；浏览 {views}、评论 {comments}、点赞 {likes}。",
                    "metrics": {"views": views, "comments": comments, "likes": likes},
                    "evidence_count": 1,
                    "_time_key": published.timestamp(),
                }
            )

        if not items:
            reached_window_start = True
            break
        if page_dates and max(page_dates) < start:
            reached_window_start = True
            break
        if site_max_pages and page_no >= site_max_pages:
            reached_window_start = True
            break
        time.sleep(0.08)

    truncated = bool(
        limited_note
        or (
            not reached_window_start
            and pages_fetched >= TAOGUBA_SEARCH_MAX_PAGES
            and (not site_max_pages or site_max_pages > TAOGUBA_SEARCH_MAX_PAGES)
        )
    )
    if truncated and not limited_note:
        limited_note = f"近7天结果超过淘股吧本次安全翻页上限（{TAOGUBA_SEARCH_MAX_PAGES}页）。"
    return {
        "results": results,
        "status": {
            "source": "淘股吧",
            "status": "limited" if truncated else "ok",
            "complete": not truncated,
            "pages_fetched": pages_fetched,
            "site_total": site_total,
            "note": limited_note or f"已按最新顺序翻页至7天边界，共读取 {pages_fetched} 页。",
        },
    }


def search_live(
    query: str,
    sort_by: str = "heat",
    reference: datetime | None = None,
    providers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    query = clean_text(query)
    if not query:
        raise ValueError("请输入股票名称、代码或关键词")
    if len(query) > 80:
        raise ValueError("搜索词不能超过 80 个字符")
    if sort_by not in {"heat", "time"}:
        raise ValueError("排序方式只能是 heat 或 time")

    end = reference or now_local()
    start = end - timedelta(days=SEARCH_WINDOW_DAYS)
    provider_map = providers or {
        "雪球": search_xueqiu_live,
        "淘股吧": search_taoguba_live,
    }
    outputs: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=len(provider_map)) as executor:
        futures = {executor.submit(provider, query, start, end): source for source, provider in provider_map.items()}
        for future in as_completed(futures):
            source = futures[future]
            try:
                outputs[source] = future.result()
            except Exception as exc:  # pragma: no cover - live network/browser failure
                outputs[source] = {
                    "results": [],
                    "status": {
                        "source": source,
                        "status": "error",
                        "complete": False,
                        "pages_fetched": 0,
                        "site_total": 0,
                        "note": f"{type(exc).__name__}: {exc}",
                    },
                }

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for source in ("雪球", "淘股吧"):
        for item in outputs.get(source, {}).get("results", []):
            key = (source, canonical_source_url(item.get("url", "")) or clean_text(item.get("id")))
            existing = grouped.get(key)
            if not existing or item.get("_time_key", 0) > existing.get("_time_key", 0):
                grouped[key] = item

    results = list(grouped.values())
    if sort_by == "time":
        results.sort(key=lambda item: (item.get("_time_key", 0), item.get("heat_score", 0)), reverse=True)
    else:
        results.sort(key=lambda item: (item.get("heat_score", 0), item.get("_time_key", 0)), reverse=True)
    for item in results:
        item.pop("_time_key", None)

    statuses = [
        outputs.get(source, {}).get(
            "status",
            {"source": source, "status": "error", "complete": False, "note": "该站未返回状态。"},
        )
        for source in ("雪球", "淘股吧")
    ]
    source_counts = {source: sum(1 for item in results if item.get("source") == source) for source in ("雪球", "淘股吧")}
    return {
        "query": query,
        "sort": sort_by,
        "count": len(results),
        "source_counts": source_counts,
        "results": results,
        "window_days": SEARCH_WINDOW_DAYS,
        "window_start": start.isoformat(timespec="seconds"),
        "window_end": end.isoformat(timespec="seconds"),
        "searched_at": now_local().isoformat(timespec="seconds"),
        "complete": all(status.get("complete") for status in statuses),
        "source_statuses": statuses,
        "scope": "实时检索雪球、淘股吧公开全站搜索入口，并精确保留提交搜索前7×24小时内的结果。",
    }


def ai_themes(text: str) -> list[str]:
    normalized = clean_text(text)
    lowered = normalized.lower()
    themes: list[str] = []
    for theme, terms in AI_THEME_RULES:
        if any(term.lower() in lowered for term in terms):
            themes.append(theme)
    application_themes = {"AI营销", "AI教育", "AI医疗", "AI办公", "AI Agent", "AI内容", "AI软件"}
    if any(term.lower() in lowered for term in GENERIC_AI_TERMS) or application_themes.intersection(themes):
        themes.insert(0, "AI应用")
    return list(dict.fromkeys(themes))


def general_topics(text: str) -> list[str]:
    lowered = clean_text(text).lower()
    result = [name for name, terms in GENERAL_TOPIC_RULES if any(t.lower() in lowered for t in terms)]
    return list(dict.fromkeys(result))


def xueqiu_heat(rank: int) -> tuple[float, str]:
    score = round(max(1.0, 101.0 - rank), 1)
    if rank <= 20:
        return score, "high"
    if rank <= 60:
        return score, "medium"
    return score, "low"


def taoguba_heat(views: int, comments: int) -> tuple[float, str]:
    score = round(min(100.0, math.log10(views + 1) * 14 + math.log10(comments + 1) * 20), 1)
    if views >= 3000 or comments >= 100:
        return score, "high"
    if views >= 300 or comments >= 15:
        return score, "medium"
    return score, "low"


def parse_partial_datetime(value: str, reference: datetime | None = None) -> datetime | None:
    reference = reference or now_local()
    match = re.fullmatch(r"(\d{2})-(\d{2})\s+(\d{2}):(\d{2})", clean_text(value))
    if not match:
        return None
    month, day, hour, minute = map(int, match.groups())
    try:
        candidate = reference.replace(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError:
        return None
    if candidate > reference + timedelta(days=2):
        candidate = candidate.replace(year=candidate.year - 1)
    return candidate


def is_recent_partial(value: str, days: int = 4, reference: datetime | None = None) -> bool:
    reference = reference or now_local()
    candidate = parse_partial_datetime(value, reference)
    if not candidate:
        return False
    age = reference - candidate
    return timedelta(days=-1) <= age <= timedelta(days=days)


def normalize_symbol(symbol: str) -> str:
    symbol = re.sub(r"[^A-Za-z0-9]", "", symbol or "").upper()
    if re.fullmatch(r"\d{6}", symbol):
        if symbol.startswith(("0", "2", "3")):
            return "SZ" + symbol
        if symbol.startswith(("4", "8")):
            return "BJ" + symbol
        return "SH" + symbol
    return symbol


def is_a_share(symbol: str) -> bool:
    return bool(re.fullmatch(r"(?:SH|SZ|BJ)\d{6}", normalize_symbol(symbol)))


def search_time_key(value: str | None, snapshot_date: str) -> float:
    candidates = [clean_text(value), clean_text(snapshot_date)]
    for candidate in candidates:
        if not candidate:
            continue
        normalized = candidate.replace("T", " ").replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            pass
        partial = parse_partial_datetime(candidate)
        if partial:
            return partial.timestamp()
    return 0.0


def canonical_source_url(value: str | None) -> str:
    value = clean_text(value)
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    query = [
        (key, val)
        for key, val in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"from", "share_source"}
    ]
    return urllib.parse.urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            urllib.parse.urlencode(sorted(query)),
            "",
        )
    )


def heat_reason(source: str, metrics: dict[str, Any], tier: str) -> str:
    tier_text = "高热" if tier == "high" else "中热" if tier == "medium" else "低热"
    if source == "淘股吧" and ("views" in metrics or "comments" in metrics):
        return (
            f"公开页面显示 {int(metrics.get('views') or 0)} 阅读、"
            f"{int(metrics.get('comments') or 0)} 评论；按互动阈值判为{tier_text}。"
        )
    if source == "雪球" and "rank" in metrics:
        return f"雪球公开热股榜第 {int(metrics.get('rank') or 0)} 名；按榜单名次判为{tier_text}。"
    return f"按当前公开互动或榜单口径判为{tier_text}。"


def search_snapshots(
    snapshots: list[dict[str, Any]], query: str, sort_by: str = "heat"
) -> dict[str, Any]:
    query = clean_text(query)
    if not query:
        raise ValueError("请输入股票名称、代码或关键词")
    if len(query) > 80:
        raise ValueError("搜索词不能超过 80 个字符")
    if sort_by not in {"heat", "time"}:
        raise ValueError("排序方式只能是 heat 或 time")

    needle = re.sub(r"\s+", "", query).lower()
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    for snapshot in snapshots:
        snapshot_date = clean_text(snapshot.get("date"))
        candidates: list[tuple[str, dict[str, Any]]] = [
            ("hotspot", item) for item in snapshot.get("hotspots", [])
        ] + [("evidence", item) for item in snapshot.get("evidence", [])]

        for kind, item in candidates:
            source = clean_text(item.get("source"))
            url = clean_text(item.get("url"))
            canonical_url = canonical_source_url(url)
            fallback_id = clean_text(item.get("id")) or clean_text(item.get("title"))
            identity = canonical_url or f"{kind}:{fallback_id}:{snapshot_date}"
            group_key = (source, identity)
            mentions = list(item.get("mentions") or [])
            if kind == "evidence":
                mentions = [
                    {
                        "symbol": clean_text(item.get("symbol")),
                        "name": clean_text(item.get("name")),
                    }
                ]
            mentions = [mention for mention in mentions if mention.get("symbol") or mention.get("name")]
            published_at = clean_text(item.get("published_at")) or None
            time_key = search_time_key(published_at, snapshot_date)
            heat_score = float(item.get("heat_score") or 0)
            excerpt = clean_text(item.get("excerpt") or item.get("summary"))
            fragment = {
                "excerpt": excerpt,
                "searchable": re.sub(
                    r"\s+",
                    "",
                    json.dumps(
                        {
                            "title": item.get("title"),
                            "excerpt": excerpt,
                            "why": item.get("why"),
                            "themes": item.get("themes") or [],
                            "mentions": mentions,
                            "source": source,
                        },
                        ensure_ascii=False,
                    ),
                ).lower(),
            }
            if group_key not in groups:
                groups[group_key] = {
                    "id": clean_text(item.get("id")) or f"result-{len(groups) + 1}",
                    "kind": "post" if source == "淘股吧" else "topic",
                    "source": source,
                    "title": clean_text(item.get("title")),
                    "url": url,
                    "heat_score": heat_score,
                    "heat_tier": clean_text(item.get("heat_tier")) or "low",
                    "published_at": published_at,
                    "snapshot_date": snapshot_date,
                    "why": clean_text(item.get("why")),
                    "metrics": dict(item.get("metrics") or {}),
                    "_time_key": time_key,
                    "_themes": {},
                    "_mentions": {},
                    "_fragments": [],
                    "_snapshot_dates": set(),
                    "_evidence_count": 0,
                }
            group = groups[group_key]
            group["_fragments"].append(fragment)
            group["_snapshot_dates"].add(snapshot_date)
            group["_evidence_count"] += 1
            if snapshot_date > group["snapshot_date"]:
                group["snapshot_date"] = snapshot_date
            if time_key > group["_time_key"]:
                group["_time_key"] = time_key
                if published_at:
                    group["published_at"] = published_at
            if heat_score > group["heat_score"]:
                group["heat_score"] = heat_score
                group["heat_tier"] = clean_text(item.get("heat_tier")) or "low"
            if not group["why"] and item.get("why"):
                group["why"] = clean_text(item.get("why"))
            for metric, value in dict(item.get("metrics") or {}).items():
                existing = group["metrics"].get(metric)
                if isinstance(value, (int, float)) and isinstance(existing, (int, float)):
                    group["metrics"][metric] = max(existing, value)
                elif existing is None:
                    group["metrics"][metric] = value
            for theme in item.get("themes") or []:
                group["_themes"].setdefault(clean_text(theme), None)
            for mention in mentions:
                symbol = normalize_symbol(clean_text(mention.get("symbol")))
                name = clean_text(mention.get("name"))
                mention_key = symbol or name
                if mention_key:
                    current = group["_mentions"].get(mention_key)
                    if not current or current.get("name") == current.get("symbol"):
                        group["_mentions"][mention_key] = {"symbol": symbol, "name": name or symbol}

    results: list[dict[str, Any]] = []
    for group in groups.values():
        fragments = group["_fragments"]
        if not any(needle in fragment["searchable"] for fragment in fragments):
            continue
        matching_fragments = [fragment for fragment in fragments if needle in fragment["searchable"]]
        excerpt = next(
            (fragment["excerpt"] for fragment in matching_fragments if fragment["excerpt"]),
            next((fragment["excerpt"] for fragment in fragments if fragment["excerpt"]), ""),
        )
        mentions = list(group["_mentions"].values())
        mentions.sort(
            key=lambda mention: (
                needle not in re.sub(r"\s+", "", json.dumps(mention, ensure_ascii=False)).lower(),
                mention.get("name") or mention.get("symbol"),
            )
        )
        result = {
            key: value for key, value in group.items() if not key.startswith("_")
        }
        result.update(
            {
                "excerpt": excerpt,
                "themes": list(group["_themes"]),
                "mentions": mentions,
                "why": group["why"] or heat_reason(
                    group["source"], group["metrics"], group["heat_tier"]
                ),
                "snapshot_count": len(group["_snapshot_dates"]),
                "evidence_count": group["_evidence_count"],
                "_time_key": group["_time_key"],
            }
        )
        results.append(result)

    if sort_by == "time":
        results.sort(key=lambda item: (item["_time_key"], item["heat_score"]), reverse=True)
    else:
        results.sort(key=lambda item: (item["heat_score"], item["_time_key"]), reverse=True)
    for item in results:
        item.pop("_time_key", None)

    source_counts = {
        source: sum(1 for item in results if item["source"] == source)
        for source in ("雪球", "淘股吧")
    }
    return {
        "query": query,
        "sort": sort_by,
        "count": len(results),
        "source_counts": source_counts,
        "results": results,
        "scope": "仅检索本机已采集保存的雪球、淘股吧公开资料，不包含需登录的站内搜索结果。",
    }


def search_archive(query: str, sort_by: str = "heat") -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    dated_paths = sorted(DATA_DIR.glob("20??-??-??.json"), reverse=True)
    if not dated_paths and LATEST_PATH.exists():
        dated_paths = [LATEST_PATH]
    for path in dated_paths:
        try:
            snapshots.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    result = search_snapshots(snapshots, query, sort_by)
    result["snapshot_count"] = len(snapshots)
    return result


def fetch_xueqiu() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    http_text(opener, XUEQIU_HOT_URL)
    params = urllib.parse.urlencode(
        {
            "page": 1,
            "size": 100,
            "order": "desc",
            "order_by": "value",
            "_": int(time.time() * 1000),
            "type": "10",
            "x": ".5",
        }
    )
    payload = http_json(opener, f"{XUEQIU_HOT_API}?{params}", XUEQIU_HOT_URL)
    stocks = payload.get("data", {}).get("items", [])
    if not stocks:
        raise RuntimeError("雪球热股榜没有返回股票")

    tags_by_symbol: dict[str, dict[str, Any]] = {}
    symbols = [normalize_symbol(item.get("symbol") or item.get("code") or "") for item in stocks]
    for offset in range(0, len(symbols), 35):
        batch = ",".join(symbols[offset : offset + 35])
        tag_url = XUEQIU_TAG_API + "?" + urllib.parse.urlencode({"symbols": batch})
        try:
            tag_payload = http_json(opener, tag_url, XUEQIU_HOT_URL)
            for item in tag_payload.get("data", []) or []:
                tags_by_symbol[normalize_symbol(item.get("symbol", ""))] = item
        except Exception:
            continue

    name_map: dict[str, str] = dict(STOCK_ALIASES)
    hotspots: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    normalized_stocks: list[dict[str, Any]] = []

    for rank, raw in enumerate(stocks, start=1):
        symbol = normalize_symbol(raw.get("symbol") or raw.get("code") or "")
        name = clean_text(str(raw.get("name") or symbol))
        if name and symbol:
            name_map[name] = symbol
        score, tier = xueqiu_heat(rank)
        tag_info = tags_by_symbol.get(symbol, {})
        tag = clean_text(tag_info.get("tag"))
        url = "https://xueqiu.com/S/" + urllib.parse.quote(symbol)
        tag_url = "https://xueqiu.com/k?q=" + urllib.parse.quote(tag) if tag else url
        normalized = {
            "rank": rank,
            "symbol": symbol,
            "name": name,
            "value": float(raw.get("value") or 0),
            "percent": raw.get("percent"),
            "tag": tag,
            "url": url,
            "tag_url": tag_url,
            "heat_score": score,
            "heat_tier": tier,
        }
        normalized_stocks.append(normalized)

        if rank <= 12:
            reason = f"雪球热搜榜第 {rank} 名，站内热度 {normalized['value']:.0f}"
            if tag:
                reason += f"；关联话题“{tag.strip('#')}”"
            hotspots.append(
                {
                    "id": f"xq-{symbol}",
                    "source": "雪球",
                    "title": tag.strip("#") if tag else f"{name}进入雪球热股榜前列",
                    "summary": (
                        f"{name}（{symbol}）当前位列雪球热股榜第 {rank} 名。"
                        + (f"页面将其与“{tag.strip('#')}”关联。" if tag else "公开榜单未附关联话题。")
                    ),
                    "url": tag_url,
                    "heat_score": score,
                    "heat_tier": tier,
                    "why": reason,
                    "themes": general_topics(tag),
                    "metrics": {"rank": rank, "platform_heat": normalized["value"], "change_pct": raw.get("percent")},
                    "published_at": None,
                    "mentions": [{"symbol": symbol, "name": name}],
                }
            )

        themes = ai_themes(tag)
        if is_a_share(symbol) and tier in {"medium", "high"} and themes:
            evidence.append(
                {
                    "source": "雪球",
                    "symbol": symbol,
                    "name": name,
                    "themes": themes,
                    "title": tag.strip("#") or f"{name}的雪球热榜关联话题",
                    "excerpt": f"雪球热股榜第 {rank} 名，热度 {normalized['value']:.0f}；关联话题：{tag.strip('#')}。",
                    "url": tag_url,
                    "heat_score": score,
                    "heat_tier": tier,
                    "published_at": None,
                    "metrics": {"rank": rank, "platform_heat": normalized["value"]},
                }
            )

    health = {
        "source": "雪球",
        "status": "ok",
        "item_count": len(stocks),
        "note": "公开热股榜及其关联话题可用；未登录站内讨论搜索不纳入采集。",
        "url": XUEQIU_HOT_URL,
    }
    return hotspots, evidence, name_map, {"health": health, "stocks": normalized_stocks}


def parse_tgb_listing(page_html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(page_html, "html.parser")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in soup.select(".Nbbs-tiezi-lists"):
        link = row.select_one(".middle-list-tittle a[href^='/a/']")
        metrics_node = row.select_one(".middle-list-talk")
        if not link or not metrics_node:
            continue
        href = str(link.get("href") or "")
        if href in seen:
            continue
        seen.add(href)
        metric_match = re.search(r"([\d,]+)\s*/\s*([\d,]+)", clean_text(metrics_node.get_text(" ")))
        comments = int(metric_match.group(1).replace(",", "")) if metric_match else 0
        views = int(metric_match.group(2).replace(",", "")) if metric_match else 0
        score, tier = taoguba_heat(views, comments)
        title = clean_text(link.get("title") or link.get_text(" "))
        results.append(
            {
                "id": href.rsplit("/", 1)[-1],
                "title": title,
                "url": urllib.parse.urljoin(TAOGUBA_BBS_URL, href),
                "comments": comments,
                "views": views,
                "reply_time": clean_text((row.select_one(".middle-list-reply") or {}).get_text(" ") if row.select_one(".middle-list-reply") else ""),
                "post_time": clean_text((row.select_one(".middle-list-post") or {}).get_text(" ") if row.select_one(".middle-list-post") else ""),
                "author": clean_text((row.select_one(".middle-list-user") or {}).get_text(" ") if row.select_one(".middle-list-user") else ""),
                "heat_score": score,
                "heat_tier": tier,
            }
        )
    return results


def parse_tgb_detail(page_html: str, fallback: dict[str, Any]) -> dict[str, Any]:
    soup = BeautifulSoup(page_html, "html.parser")
    body = soup.select_one(".article-text.p_coten") or soup.select_one(".article-text")
    content = clean_text(body.get_text(" ")) if body else ""
    article = soup.select_one(".article-content")
    meta_text = clean_text(article.get_text(" ")) if article else ""
    meta_match = re.search(
        r"(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*\|\s*浏览\s*([\d,]+)\s*\|\s*评论\s*([\d,]+)",
        meta_text,
    )
    published_at = meta_match.group(1) if meta_match else None
    views = int(meta_match.group(2).replace(",", "")) if meta_match else fallback["views"]
    comments = int(meta_match.group(3).replace(",", "")) if meta_match else fallback["comments"]
    score, tier = taoguba_heat(views, comments)

    stocks: dict[str, str] = {}
    if body:
        for link in body.select("a[href*='/quotes/']"):
            href = str(link.get("href") or "")
            match = re.search(r"/quotes/((?:sh|sz|bj)?\d{6})", href, re.I)
            if match:
                symbol = normalize_symbol(match.group(1))
                name = clean_text(link.get_text(" ")).strip("$ ")
                name = re.sub(r"\s*[（(](?:sh|sz|bj)\d{6}[）)]\s*$", "", name, flags=re.I)
                if name and is_a_share(symbol):
                    stocks[symbol] = name
    return {
        **fallback,
        "content": content,
        "published_at": published_at,
        "views": views,
        "comments": comments,
        "heat_score": score,
        "heat_tier": tier,
        "linked_stocks": stocks,
    }


def stock_mentions(text: str, linked: dict[str, str], name_map: dict[str, str]) -> list[dict[str, str]]:
    found: dict[str, str] = dict(linked)
    normalized = clean_text(text)
    for name, symbol in sorted(name_map.items(), key=lambda item: len(item[0]), reverse=True):
        if len(name) >= 2 and name in normalized and is_a_share(symbol):
            found.setdefault(normalize_symbol(symbol), name)
    # 裸六位数字可能是日期、浏览量、订单号等，只接受带交易所前缀的正文代码。
    for match in re.finditer(r"(?<![A-Za-z0-9])(SH|SZ|BJ)\s*([0368]\d{5})(?!\d)", normalized, re.I):
        symbol = normalize_symbol(match.group(1) + match.group(2))
        if is_a_share(symbol):
            found.setdefault(symbol, symbol)
    return [{"symbol": symbol, "name": name} for symbol, name in sorted(found.items())]


def local_mention_context(text: str, name: str, symbol: str, radius: int = 210) -> str:
    normalized = clean_text(text)
    candidates = [name, symbol, symbol[2:] if len(symbol) == 8 else ""]
    positions = [normalized.find(candidate) for candidate in candidates if candidate]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return compact_excerpt(normalized, radius * 2)
    position = min(positions)
    start = max(0, position - radius)
    end = min(len(normalized), position + max(len(name), len(symbol)) + radius)
    return normalized[start:end]


def fetch_taoguba(name_map: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    opener = urllib.request.build_opener()
    listing_html = http_text(opener, TAOGUBA_BBS_URL)
    rows = parse_tgb_listing(listing_html)
    if not rows:
        raise RuntimeError("淘股吧公开论坛列表未解析到帖子")

    reference = now_local()
    medium_rows = [
        row
        for row in rows
        if row["heat_tier"] in {"medium", "high"}
        and is_recent_partial(row["post_time"], reference=reference)
    ]
    ranked = sorted(medium_rows, key=lambda row: (row["comments"], row["views"]), reverse=True)
    ai_title_rows = [row for row in medium_rows if ai_themes(row["title"])]
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for row in ai_title_rows + ranked[:18]:
        if row["id"] not in selected_ids and len(selected) < 24:
            selected.append(row)
            selected_ids.add(row["id"])

    details: dict[str, dict[str, Any]] = {}
    detail_errors = 0
    for row in selected:
        try:
            detail_html = http_text(opener, row["url"], TAOGUBA_BBS_URL)
            details[row["id"]] = parse_tgb_detail(detail_html, row)
            time.sleep(0.08)
        except Exception:
            details[row["id"]] = {**row, "content": "", "published_at": None, "linked_stocks": {}}
            detail_errors += 1

    topical = [
        row
        for row in ranked
        if ai_themes(row["title"])
        or general_topics(row["title"])
        or any(term.lower() in row["title"].lower() for term in TAOGUBA_DAILY_TOPIC_TERMS)
    ]
    if len(topical) < 8:
        topical_ids = {row["id"] for row in topical}
        topical.extend(row for row in ranked if row["id"] not in topical_ids)

    hotspots: list[dict[str, Any]] = []
    for row in topical[:10]:
        detail = details.get(row["id"], {**row, "content": "", "published_at": None, "linked_stocks": {}})
        context = detail.get("content") or row["title"]
        mentions = stock_mentions(context, detail.get("linked_stocks", {}), name_map)
        hotspots.append(
            {
                "id": f"tgb-{row['id']}",
                "source": "淘股吧",
                "title": row["title"],
                "summary": compact_excerpt(detail.get("content") or "公开列表未提供正文摘要，请打开原帖查看。"),
                "url": row["url"],
                "heat_score": detail["heat_score"],
                "heat_tier": detail["heat_tier"],
                "why": (
                    f"原帖发表于 {detail.get('published_at') or row.get('post_time') or '时间未公开'}，"
                    f"当前仍在公开论坛活跃列表；页面显示 {detail['views']} 阅读、{detail['comments']} 评论，"
                    f"按互动阈值判为{('高热' if detail['heat_tier'] == 'high' else '中热')}。"
                ),
                "themes": general_topics(context),
                "metrics": {"views": detail["views"], "comments": detail["comments"]},
                "published_at": detail.get("published_at") or row.get("post_time"),
                "mentions": mentions,
            }
        )

    evidence: list[dict[str, Any]] = []
    for detail in details.values():
        context = f"{detail['title']} {detail.get('content', '')}"
        themes = ai_themes(context)
        if not themes or detail["heat_tier"] not in {"medium", "high"}:
            continue
        mentions = stock_mentions(detail.get("content", ""), detail.get("linked_stocks", {}), name_map)
        for stock in mentions:
            context_near_stock = local_mention_context(
                detail.get("content", ""), stock["name"], stock["symbol"]
            )
            stock_themes = ai_themes(f"{detail['title']} {context_near_stock}")
            if not stock_themes:
                continue
            evidence.append(
                {
                    "source": "淘股吧",
                    "symbol": stock["symbol"],
                    "name": stock["name"],
                    "themes": stock_themes,
                    "title": detail["title"],
                    "excerpt": compact_excerpt(context_near_stock or detail["title"], 280),
                    "url": detail["url"],
                    "heat_score": detail["heat_score"],
                    "heat_tier": detail["heat_tier"],
                    "published_at": detail.get("published_at") or detail.get("post_time"),
                    "metrics": {"views": detail["views"], "comments": detail["comments"]},
                }
            )

    health = {
        "source": "淘股吧",
        "status": "ok" if detail_errors < len(selected) else "degraded",
        "item_count": len(rows),
        "note": f"公开论坛列表可用；抽取 {len(details) - detail_errors}/{len(selected)} 篇详情。搜索页需要登录，未绕过。",
        "url": TAOGUBA_BBS_URL,
    }
    return hotspots, evidence, {"health": health, "rows": rows}


def build_ai_pools(evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in evidence:
        grouped[normalize_symbol(item["symbol"])].append(item)

    confirmed: list[dict[str, Any]] = []
    disputed: list[dict[str, Any]] = []
    for symbol, items in grouped.items():
        source_themes: dict[str, set[str]] = defaultdict(set)
        source_items: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            source_themes[item["source"]].update(item["themes"])
            source_items[item["source"]].append(item)
        sources = set(source_themes)
        common = set.intersection(*(source_themes[source] for source in sorted(sources))) if len(sources) >= 2 else set()
        name = next((item["name"] for item in items if item["name"] != symbol), symbol)
        entry = {
            "symbol": symbol,
            "name": name,
            "themes": sorted(set().union(*(set(item["themes"]) for item in items))),
            "common_themes": sorted(common),
            "sources": sorted(sources),
            "evidence": sorted(items, key=lambda item: item["heat_score"], reverse=True),
            "max_heat_score": max(item["heat_score"] for item in items),
            "max_heat_tier": "high" if any(item["heat_tier"] == "high" for item in items) else "medium",
        }
        if {"雪球", "淘股吧"}.issubset(sources) and common:
            entry["reason"] = "两站均达到中热以上，且共同归入：" + "、".join(sorted(common))
            confirmed.append(entry)
        else:
            if len(sources) == 1:
                only = next(iter(sources))
                missing = "淘股吧" if only == "雪球" else "雪球"
                entry["reason"] = f"仅{only}发现中热以上 AI 证据；{missing}当前公开采集范围未发现同股同主题证据。"
            else:
                parts = [f"{source}：{'、'.join(sorted(themes))}" for source, themes in sorted(source_themes.items())]
                entry["reason"] = "两站均有提及，但 AI 子主题未形成交集；" + "；".join(parts)
            disputed.append(entry)

    confirmed.sort(key=lambda item: item["max_heat_score"], reverse=True)
    disputed.sort(key=lambda item: item["max_heat_score"], reverse=True)
    return {"confirmed": confirmed, "disputed": disputed}


def collect() -> dict[str, Any]:
    generated = now_local()
    source_health: list[dict[str, Any]] = []
    hotspots: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {}
    name_map = dict(STOCK_ALIASES)

    try:
        xq_hotspots, xq_evidence, xq_names, xq_meta = fetch_xueqiu()
        hotspots.extend(xq_hotspots)
        evidence.extend(xq_evidence)
        name_map.update(xq_names)
        source_health.append(xq_meta["health"])
        diagnostics["xueqiu_hot_count"] = len(xq_meta["stocks"])
    except Exception as exc:
        source_health.append(
            {"source": "雪球", "status": "error", "item_count": 0, "note": f"采集失败：{type(exc).__name__}: {exc}", "url": XUEQIU_HOT_URL}
        )

    try:
        tgb_hotspots, tgb_evidence, tgb_meta = fetch_taoguba(name_map)
        hotspots.extend(tgb_hotspots)
        evidence.extend(tgb_evidence)
        source_health.append(tgb_meta["health"])
        diagnostics["taoguba_listing_count"] = len(tgb_meta["rows"])
    except Exception as exc:
        source_health.append(
            {"source": "淘股吧", "status": "error", "item_count": 0, "note": f"采集失败：{type(exc).__name__}: {exc}", "url": TAOGUBA_BBS_URL}
        )

    # 同一来源、同一股票、同一原帖只保留一次证据。
    deduped: list[dict[str, Any]] = []
    seen_evidence: set[tuple[str, str, str]] = set()
    for item in evidence:
        key = (item["source"], normalize_symbol(item["symbol"]), item["url"])
        if key not in seen_evidence:
            deduped.append(item)
            seen_evidence.add(key)

    pools = build_ai_pools(deduped)
    payload = {
        "schema_version": 1,
        "date": generated.strftime("%Y-%m-%d"),
        "generated_at": generated.isoformat(timespec="seconds"),
        "title": "雪球 × 淘股吧 · AI 股票舆情看板",
        "disclaimer": "本页只整理公开讨论及热度，不构成投资建议。来源观点可能错误、滞后或受情绪影响，请回看原文并独立判断。",
        "source_health": source_health,
        "hotspots": sorted(hotspots, key=lambda item: (item["heat_tier"] == "high", item["heat_score"]), reverse=True),
        "ai_pool": pools,
        "evidence": deduped,
        "methodology": {
            "xueqiu_heat": "热股榜第1–20名=高热，第21–60名=中热，其余=低热；AI池只接收中热以上且关联话题明确含AI逻辑的A股。",
            "taoguba_heat": "阅读≥3000或评论≥100=高热；阅读≥300或评论≥15=中热；只分析近4日仍在活跃列表的帖子，AI池还要求正文有AI逻辑并明确提及股票。",
            "confirmed": "同一证券代码在雪球、淘股吧均有中热以上证据，且至少一个AI子主题一致。",
            "disputed": "只有一站提及，或两站均提及但AI子主题不一致。",
            "scope": "仅采集无需登录即可访问的公开页面；遇到登录、验证码或访问限制不绕过。",
        },
        "diagnostics": diagnostics,
    }
    return payload


def write_snapshot(payload: dict[str, Any]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    day_path = DATA_DIR / f"{payload['date']}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    day_path.write_text(text, encoding="utf-8")
    LATEST_PATH.write_text(text, encoding="utf-8")
    return day_path


class DashboardHandler(SimpleHTTPRequestHandler):
    server_version = "StockPulse/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/data":
            if LATEST_PATH.exists():
                self._send_json(json.loads(LATEST_PATH.read_text(encoding="utf-8")))
            else:
                self._send_json({"error": "尚未采集数据"}, status=404)
            return
        if parsed.path == "/api/search":
            params = urllib.parse.parse_qs(parsed.query)
            query = (params.get("q") or [""])[0]
            sort_by = (params.get("sort") or ["heat"])[0]
            try:
                self._send_json(search_live(query, sort_by))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=400)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/refresh":
            self._send_json({"error": "not found"}, status=404)
            return
        try:
            payload = collect()
            path = write_snapshot(payload)
            self._send_json({"ok": True, "path": str(path), "data": payload})
        except Exception as exc:  # pragma: no cover - network failure path
            self._send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def serve(host: str, port: int, open_browser: bool) -> None:
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    url = f"http://{host}:{port}/index.html"
    print(f"AI 股票舆情看板已启动：{url}")
    print("关闭此窗口即可停止本地服务。")
    if open_browser:
        fresh_url = f"{url}?v={int(time.time())}"
        threading.Timer(0.8, lambda: webbrowser.open(fresh_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="雪球 × 淘股吧 AI 股票舆情采集与看板服务")
    parser.add_argument("--refresh", action="store_true", help="立即采集并保存当日快照")
    parser.add_argument("--serve", action="store_true", help="启动本地看板服务")
    parser.add_argument("--open", action="store_true", help="启动服务后自动打开浏览器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.refresh or not LATEST_PATH.exists():
        path = write_snapshot(collect())
        print(f"已保存：{path}")
    if args.serve:
        serve(args.host, args.port, args.open)


if __name__ == "__main__":
    main()
