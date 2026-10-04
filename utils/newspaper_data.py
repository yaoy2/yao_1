"""Public, read-only news acquisition for M28. No accounts or local storage.

Sources are deliberately explicit. A successful HTTP response is not enough:
items need a valid official article URL, a title and a real publication date.
The caller may cache these functions; failures are reported per source.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import re
import time
from urllib.parse import urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import requests


SHANGHAI = timezone(timedelta(hours=8))
REQUEST_TIMEOUT = (3.5, 7)
MAX_RESPONSE_BYTES = 2_000_000
MAX_REQUEST_SECONDS = 18
MAX_WORKERS = 4
MAX_ARTICLES = 450
USER_AGENT = "NewspaperPersonalReader/1.0 (+public news reading)"
ALLOWED_HOSTS = frozenset({
    "www.chinanews.com.cn", "chinanews.com.cn",
    "www.chinanews.com", "chinanews.com",
    "news.cctv.com", "military.cctv.com", "jingji.cctv.com",
    "www.chinawriter.com.cn", "chinawriter.com.cn",
})

CATALOG = (
    ("时政与国防", ("时政要闻", "政策解读", "公共治理", "法治司法", "港澳台", "国防军事")),
    ("全球视野", ("国际要闻", "大国关系", "区域观察", "冲突与安全", "国际组织", "全球议题")),
    ("经济与产业", ("宏观经济", "产业制造", "公司商业", "消费零售", "能源资源", "三农乡村")),
    ("金融与市场", ("A股市场", "港股与海外市场", "银行保险", "基金理财", "债券汇率与大宗", "房产楼市")),
    ("科技与科学", ("AI与互联网", "芯片与通信", "数码产品", "科学前沿", "航天航空", "汽车与交通技术")),
    ("社会与民生", ("地方城市", "教育校园", "就业职场", "医疗健康", "社保养老", "消费维权")),
    ("生活与人文", ("旅行地理", "美食与饮食", "居家生活", "历史文博", "艺术展览", "环境自然")),
    ("体育与运动", ("足球", "篮球", "乒羽网球", "综合竞技", "电竞", "全民健身与户外")),
    ("阅读与文学", ("小说推荐", "网络文学", "散文随笔", "诗歌", "文学评论", "新书与综合书单")),
    ("电影与电视", ("电影资讯与片单", "电视剧与网剧", "纪录片", "动画动漫", "综艺音乐", "影评与主创访谈")),
)
CATEGORY_GROUP = {category: group for group, categories in CATALOG for category in categories}


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    scope: str
    url: str
    parser: str
    category: str
    limit: int = 30
    max_age_days: int = 30


def _cn(channel, scope, category):
    return Source("chinanews_" + channel, "中新网", scope,
                  "https://www.chinanews.com.cn/rss/" + channel + ".xml", "rss", category)


def _cctv(channel, scope, category):
    return Source("cctv_" + channel, "央视网", scope,
                  "https://news.cctv.com/2019/07/gaiban/cmsdatainterface/page/" + channel + "_1.jsonp",
                  "cctv", category)


# Old it/estate/mil RSS feeds are empty; jk/auto were stale during verification.
# They are intentionally excluded instead of presenting old items as live news.
SOURCES = (
    _cn("china", "时政", "时政要闻"),
    _cn("world", "国际", "国际要闻"),
    _cn("finance", "经济、金融与产业", "宏观经济"),
    _cn("society", "社会与民生", "地方城市"),
    _cn("culture", "文化、文学与影视", "历史文博"),
    _cn("sports", "体育", "综合竞技"),
    _cn("edu", "教育", "教育校园"),
    _cn("life", "生活与健康", "居家生活"),
    _cctv("china", "国内与民生", "地方城市"),
    _cctv("tech", "科技", "科学前沿"),
    _cctv("life", "生活与健康", "居家生活"),
    _cctv("economy_zixun", "经济与金融", "宏观经济"),
    Source("cctv_military", "央视网", "国防军事",
           "https://military.cctv.com/data/index.json", "military", "国防军事"),
    Source("chinawriter_books", "中国作家网", "新书、小说与文学",
           "https://www.chinawriter.com.cn/404058/index.html", "books", "新书与综合书单", 30, 365),
)


def _now():
    return datetime.now(SHANGHAI)


def _plain(value, limit=2000):
    soup = BeautifulSoup(str(value or ""), "html.parser")
    for element in soup(["script", "style", "noscript", "iframe", "form", "button"]):
        element.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()[:limit]


def _safe_url(value, *, article_only=False):
    """Return an HTTPS official URL, rejecting credentials, ports and lookalikes."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or re.search(r"[\x00-\x20\x7f\\]", value):
        return ""
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        if (parts.scheme not in ("http", "https") or host not in ALLOWED_HOSTS
                or parts.username is not None or parts.password is not None
                or parts.port not in (None, 80 if parts.scheme == "http" else 443)):
            return ""
        if article_only:
            if "chinanews" in host:
                pattern = r"/[a-z]+/\d{4}/\d{2}-\d{2}/\d+\.shtml"
            elif "cctv" in host:
                pattern = r"/\d{4}/\d{2}/\d{2}/[A-Za-z0-9]+\.shtml"
            else:
                pattern = r"/n1/\d{4}/\d{4}/c\d+-\d+\.html"
            if not re.fullmatch(pattern, parts.path):
                return ""
        return urlunsplit(("https", host, parts.path or "/", parts.query, ""))
    except ValueError:
        return ""


def _fetch_bytes(url, *, article_only=False):
    """Bound size/idle waits and validate each redirect; total deadline is best effort."""
    current = _safe_url(url, article_only=article_only)
    if not current:
        raise ValueError("来源网址不在允许范围内")
    deadline = time.monotonic() + MAX_REQUEST_SECONDS
    for _ in range(3):
        if time.monotonic() >= deadline:
            raise TimeoutError("读取来源超时")
        with requests.get(current, headers={"User-Agent": USER_AGENT},
                          timeout=REQUEST_TIMEOUT, allow_redirects=False, stream=True) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                current = _safe_url(urljoin(current, response.headers.get("Location", "")),
                                    article_only=article_only)
                if not current:
                    raise ValueError("来源跳转到不允许的网址")
                continue
            response.raise_for_status()
            length = response.headers.get("Content-Length", "")
            if length.isdigit() and int(length) > MAX_RESPONSE_BYTES:
                raise ValueError("来源响应过大")
            content = bytearray()
            for chunk in response.iter_content(chunk_size=32768):
                if time.monotonic() >= deadline:
                    raise TimeoutError("读取来源超时")
                content.extend(chunk)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise ValueError("来源响应过大")
            return bytes(content)
    raise ValueError("来源跳转次数过多")


def _publication(value):
    value = str(value or "").strip()
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=SHANGHAI)
    return result.astimezone(SHANGHAI)


def _classify(title, default):
    # Classify only explicit title terms, not speculative generated content.
    if default == "国防军事":
        return default
    if default == "国际要闻":
        rules = (("国际组织", r"联合国|世卫组织|国际原子能|世贸组织"),
                 ("冲突与安全", r"空袭|停火|袭击|交火|战争|战火"),
                 ("大国关系", r"中美关系|中俄关系|美俄|中欧关系"))
    elif default == "综合竞技":
        rules = (("足球", r"足球|足协|中超|英超|欧冠|女足|男足"),
                 ("篮球", r"篮球|NBA|CBA|男篮|女篮"),
                 ("乒羽网球", r"乒乓|羽毛球|网球|大满贯|温网|美网|法网|澳网"),
                 ("电竞", r"电竞|电子竞技"),
                 ("全民健身与户外", r"马拉松|全民健身|骑行|徒步"))
    else:
        rules = (
            ("网络文学", r"网络文学|网文|网络小说"),
            ("小说推荐", r"小说|小说家"),
            ("诗歌", r"诗歌|诗集|诗人"),
            ("散文随笔", r"散文|随笔"),
            ("文学评论", r"文学评论|文学批评"),
            ("影评与主创访谈", r"影评|剧评"),
            ("电视剧与网剧", r"电视剧|网剧|剧集"),
            ("纪录片", r"纪录片"),
            ("动画动漫", r"动画|动漫"),
            ("电影资讯与片单", r"电影|票房|影展|电影节"),
            ("综艺音乐", r"综艺|音乐|演唱会|歌剧"),
            ("房产楼市", r"楼市|房贷|房地产|购房|商品房|住房公积金"),
            ("银行保险", r"银行|保险|险企"),
            ("基金理财", r"基金|理财|养老金投资"),
            ("港股与海外市场", r"港股|美股|纳斯达克|恒生指数"),
            ("A股市场", r"A股|沪指|深指|上证|深证|沪深|北交所"),
            ("债券汇率与大宗", r"债券|国债|汇率|期货|金价|油价"),
            ("AI与互联网", r"人工智能|大模型|互联网|机器人|(?<![A-Za-z])AI(?![A-Za-z])"),
            ("芯片与通信", r"芯片|半导体|[56]G|量子通信"),
            ("航天航空", r"航天|卫星|空间站|火箭|载人飞船|探月"),
            ("数码产品", r"手机|平板电脑|笔记本电脑|智能穿戴"),
            ("汽车与交通技术", r"汽车|新能源车|电动车|自动驾驶|高铁技术"),
            ("医疗健康", r"医院|医疗|医生|疾病|健康|癌症|疫苗|流感|青光眼"),
            ("教育校园", r"学校|高校|教育|大学|校园|中小学|高考|考研"),
            ("就业职场", r"就业|招聘|求职|职场|劳动者|劳动合同"),
            ("社保养老", r"社保|养老|医保|退休"),
            ("消费维权", r"维权|消费者权益|消费投诉|假冒|产品召回"),
            ("法治司法", r"法院|检察|司法|判决|起诉|法治"),
            ("港澳台", r"香港|澳门|台湾|两岸|大湾区"),
            ("三农乡村", r"农业|农民|乡村振兴|秋收|丰收|粮食"),
            ("能源资源", r"能源|油气|气田|矿产|煤炭|光伏|风电|电力"),
            ("产业制造", r"制造业|工业|产业链|工厂"),
            ("消费零售", r"消费|零售|电商|商场|购物"),
            ("历史文博", r"博物馆|文物|考古|历史|非遗|遗址"),
            ("艺术展览", r"艺术|画展|美术|书法|展览"),
            ("环境自然", r"生态|环保|气候|野生动物|湿地|生物多样性"),
            ("旅行地理", r"旅游|文旅|游客|旅行|景区|出游"),
            ("美食与饮食", r"美食|饮食|菜肴|食材|烹饪"),
        )
    for category, pattern in rules:
        if re.search(pattern, title, flags=re.IGNORECASE):
            return category
    return default


def _article(source, title, url, published, summary="", *, precision="minute"):
    title = _plain(title, 300)
    url = _safe_url(url, article_only=True)
    date = _publication(published)
    if len(title) < 3 or not url or date is None:
        return None
    category = _classify(title, source.category)
    kind = "推荐" if source.parser == "books" else "报道"
    if re.search(r"评论|快评|述评|影评|剧评", title):
        kind = "评论"
    elif re.search(r"深读|深度|调查报道|独家调查|专访", title):
        kind = "深读"
    return {
        "id": "news_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
        "title": title, "group": CATEGORY_GROUP[category], "category": category,
        "kind": kind, "source": source.name, "source_id": source.id,
        "published_at": date.isoformat(), "date_precision": precision,
        "time": date.strftime("%Y-%m-%d" if precision == "day" else "%Y-%m-%d %H:%M"),
        "url": url, "summary": _plain(summary, 800), "available": False, "topic": "",
    }


def _parse_rss(content, source):
    # No DTD/entity processing is needed by these public RSS 2.0 feeds.
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("不支持含外部实体的 RSS")
    root = ET.fromstring(content)
    result = []
    for item in root.findall("./channel/item")[:200]:
        article = _article(source, item.findtext("title"), item.findtext("link"),
                           item.findtext("pubDate"), item.findtext("description"))
        if article:
            result.append(article)
    return result


def _parse_cctv(content, source):
    text = content.decode("utf-8-sig")
    if source.parser == "military":
        rows = json.loads(text).get("rollData", [])
    else:
        match = re.fullmatch(r"\s*[A-Za-z_$][\w$]*\s*\((.*)\)\s*;?\s*", text, re.DOTALL)
        if not match:
            raise ValueError("央视列表格式已变化")
        rows = json.loads(match.group(1)).get("data", {}).get("list", [])
    if not isinstance(rows, list):
        raise ValueError("央视列表格式已变化")
    result = []
    for row in rows[:200]:
        if not isinstance(row, dict):
            continue
        article = _article(source, row.get("title"), row.get("url"),
                           row.get("focus_date") or row.get("dateTime"),
                           row.get("brief") or row.get("description"))
        if article:
            result.append(article)
    return result


def _parse_books(content, source):
    soup = BeautifulSoup(content, "html.parser", from_encoding="utf-8")
    result = []
    for link in soup.select("a[href]"):
        url = urljoin(source.url, link.get("href", "").strip())
        match = re.search(r"/n1/(\d{4})/(\d{2})(\d{2})/c\d+-\d+\.html", url)
        if not match or not link.get_text(strip=True):
            continue
        date = "-".join(match.groups())
        title = link.get_text(" ", strip=True)
        parent = link.parent
        summary = parent.get_text(" ", strip=True) if parent else ""
        if summary == title or len(summary) > 1200:
            summary = ""
        article = _article(source, title, url, date, summary, precision="day")
        if article:
            result.append(article)
    return result


def _deduplicate(articles):
    result, seen = [], set()
    for article in articles:
        if article["url"] not in seen:
            result.append(article)
            seen.add(article["url"])
    return result


def _load_source(source, now):
    content = _fetch_bytes(source.url)
    if source.parser == "rss":
        articles = _parse_rss(content, source)
    elif source.parser in ("cctv", "military"):
        articles = _parse_cctv(content, source)
    elif source.parser == "books":
        articles = _parse_books(content, source)
    else:
        raise ValueError("未知的来源格式")
    if not articles:
        raise ValueError("来源未返回含有效标题、日期和链接的新闻")
    cutoff = now - timedelta(days=source.max_age_days)
    articles = [a for a in articles if cutoff <= _publication(a["published_at"]) <= now + timedelta(days=1)]
    if not articles:
        raise ValueError("来源没有近期有效内容，暂不收入报纸")
    return sorted(_deduplicate(articles), key=lambda a: a["published_at"], reverse=True)[:source.limit]


def _error_message(error):
    if isinstance(error, requests.HTTPError):
        status = getattr(error.response, "status_code", "未知")
        return "来源暂不可访问（HTTP %s）" % status
    if isinstance(error, (requests.Timeout, TimeoutError)):
        return "读取来源超时"
    if isinstance(error, requests.RequestException):
        return "网络连接失败"
    if isinstance(error, (ET.ParseError, json.JSONDecodeError, UnicodeError)):
        return "来源内容格式无法解析"
    if isinstance(error, ValueError):
        return _plain(str(error), 150)
    return "来源读取失败"


def load_newspaper_feed():
    """Fetch public lists concurrently; one failed source never discards others."""
    started = _now()
    by_source, statuses = {}, {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        pending = {pool.submit(_load_source, source, started): source for source in SOURCES}
        for future in as_completed(pending):
            source = pending[future]
            state = {"id": source.id, "name": source.name, "scope": source.scope,
                     "status": "ok", "count": 0, "checked_at": _now().isoformat(), "error": ""}
            try:
                articles = future.result()
                by_source[source.id] = articles
                state["count"] = len(articles)
            except Exception as error:
                state.update(status="error", error=_error_message(error))
            statuses[source.id] = state
    # Source priority is stable, independently of which network call finished first.
    articles = _deduplicate([a for source in SOURCES for a in by_source.get(source.id, [])])
    articles.sort(key=lambda article: article["published_at"], reverse=True)
    sources = [statuses[source.id] for source in SOURCES]
    return {"articles": articles[:MAX_ARTICLES], "sources": sources,
            "fetched_at": _now().isoformat(),
            "errors": ["%s · %s：%s" % (s["name"], s["scope"], s["error"])
                       for s in sources if s["status"] == "error"]}


def _extract_paragraphs(content, url):
    soup = BeautifulSoup(content, "html.parser", from_encoding="utf-8")
    host = urlsplit(url).hostname
    if "chinanews" in host:
        container = soup.select_one(".left_zw")
    elif "cctv" in host:
        container = soup.select_one("#text_area, .content_area, .cnt_bd")
    else:
        container = soup.select_one(".end_article")
    if not container:
        return []
    # Never present a login/subscription notice as a complete article.
    if re.search(r"订阅后(?:阅读|查看)|付费(?:后)?阅读|登录后(?:查看|阅读)|登录.*阅读全文|开通会员|付费解锁",
                 container.get_text()):
        return []
    for node in container.select("script, style, iframe, form, button, .ad, .advertisement"):
        node.decompose()
    paragraphs = []
    for node in container.find_all("p"):
        text = _plain(node.get_text(" ", strip=True), MAX_RESPONSE_BYTES)
        if not text or re.match(r"^(责任编辑|编辑[:：]|【编辑|更多精彩|扫码|相关阅读)", text):
            continue
        # Repeated paragraphs can be intentional, particularly in literature.
        paragraphs.append(text)
    # A teaser, image caption or video-only page is not a verified full-text article.
    if len(paragraphs) < 2 or sum(map(len, paragraphs)) < 160:
        return []
    # Keep the full/summary distinction honest instead of silently truncating.
    if len(paragraphs) > 150 or any(len(text) > 6000 for text in paragraphs):
        return []
    return paragraphs


def fetch_newspaper_article(article_dict):
    """Read an allowed public article, falling back truthfully to its feed summary."""
    article = article_dict if isinstance(article_dict, dict) else {}
    url = _safe_url(article.get("url"), article_only=True)
    summary = _plain(article.get("summary"), 800)
    result = {"id": str(article.get("id") or ""), "status": "summary",
              "paragraphs": [summary] if summary else [],
              "source": _plain(article.get("source"), 80), "url": url,
              "title": _plain(article.get("title"), 300),
              "published_at": str(article.get("published_at") or ""), "message": ""}
    if not url:
        result.update(status="error", paragraphs=[], message="文章网址不在允许的官方来源范围内")
        return result
    try:
        paragraphs = _extract_paragraphs(_fetch_bytes(url, article_only=True), url)
        if paragraphs:
            result.update(status="full", paragraphs=paragraphs, message="已提取来源公开正文，原文链接保留。")
        else:
            result["message"] = "当前只显示来源摘要；完整内容或视频请打开原文。"
    except Exception as error:
        result.update(status="error", message=_error_message(error) + "；保留来源摘要与原文链接。")
    return result
