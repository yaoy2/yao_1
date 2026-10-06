"""Bounded public publisher feeds and on-demand public article reading.

Each adapter has an explicit origin. There are no account cookies, private APIs,
JavaScript execution, login workarounds or requests to arbitrary article hosts.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
from html import unescape
import json
import re
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import requests

from utils.newspaper_data import CATEGORY_GROUP
from utils.newspaper_interviews import INTERVIEW_CATEGORY, has_interview_label, is_recent_interview, retain_interviews


NEWSPAPER_MEDIA_VERSION = 3
SHANGHAI = timezone(timedelta(hours=8))
MAX_WORKERS = 4
MAX_ITEMS_PER_SOURCE = 20
MAX_RESPONSE_BYTES = 2_000_000
MAX_REQUEST_SECONDS = 18
REQUEST_TIMEOUT = (3.5, 7)
USER_AGENT = "NewspaperPersonalReader/1.0 (+public publisher feeds)"
ATOM = "{http://www.w3.org/2005/Atom}"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
RSS1 = "{http://purl.org/rss/1.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"
SUMMARY_ORIGIN = "来源公开摘要（保留原始语言）"
RESTRICTED_TEXT = re.compile(
    r"订阅后(?:阅读|查看)|付费(?:后)?阅读|登录后(?:查看|阅读)|开通会员|付费解锁|购买后阅读全文|"
    r"登录.{0,8}阅读全文|subscribe to (?:read|continue)|sign in to (?:read|continue)|"
    r"continue reading|read the full (?:article|story)", re.I)


@dataclass(frozen=True)
class PublicSource:
    id: str
    name: str
    url: str
    hosts: tuple
    category: str
    parser: str = "rss"
    max_age_days: int = 30
    description_is_body: bool = False


PUBLIC_SOURCES = (
    PublicSource("media_ithome", "IT之家", "https://www.ithome.com/rss/", ("www.ithome.com", "ithome.com"), "数码产品", description_is_body=True),
    PublicSource("media_solidot", "Solidot", "https://www.solidot.org/index.rss", ("www.solidot.org", "solidot.org"), "科学前沿"),
    PublicSource("media_sspai", "少数派", "https://sspai.com/feed", ("sspai.com", "www.sspai.com"), "数码产品"),
    PublicSource("media_yicai", "第一财经", "https://www.yicai.com/", ("www.yicai.com", "m.yicai.com"), "宏观经济", "yicai"),
    PublicSource("media_toutiao", "今日头条热榜", "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc", ("www.toutiao.com",), "地方城市", "toutiao", 7),
    PublicSource("media_lifeweek", "三联生活周刊", "https://www.lifeweek.com.cn/", ("www.lifeweek.com.cn",), "散文随笔", "lifeweek", 60),
    PublicSource("media_lifeweek_interviews", "三联生活周刊", "https://www.lifeweek.com.cn/column/79",
                 ("www.lifeweek.com.cn",), INTERVIEW_CATEGORY, "lifeweek_interviews", 7),
    PublicSource("media_chinawriter_interviews", "中国作家网", "https://www.chinawriter.com.cn/403997/405057/index.html",
                 ("www.chinawriter.com.cn",), INTERVIEW_CATEGORY, "chinawriter_interviews", 7),
    PublicSource("media_chinanews_interviews", "中新网·东西问", "https://www.chinanews.com.cn/dxw/",
                 ("www.chinanews.com.cn",), INTERVIEW_CATEGORY, "chinanews_interviews", 7),
    PublicSource("media_cctv_dialogue", "央视《对话》",
                 "https://api.cntv.cn/NewVideo/getVideoListByColumn?id=TOPC1451530382483536&sort=desc&serviceId=tvcctv&mode=0&n=20&p=1&t=json",
                 ("api.cntv.cn", "tv.cctv.com"), INTERVIEW_CATEGORY, "cctv_interviews", 7),
    PublicSource("media_cctv_face_to_face", "央视《面对面》",
                 "https://api.cntv.cn/NewVideo/getVideoListByColumn?id=TOPC1451559038345600&n=20&sort=desc&p=1&mode=0&serviceId=tvcctv&t=json",
                 ("api.cntv.cn", "tv.cctv.com"), INTERVIEW_CATEGORY, "cctv_interviews", 7),
    PublicSource("media_bbc", "BBC News", "https://feeds.bbci.co.uk/news/world/rss.xml", ("feeds.bbci.co.uk", "www.bbc.co.uk", "www.bbc.com", "bbc.com"), "国际要闻"),
    PublicSource("media_guardian", "The Guardian", "https://www.theguardian.com/world/rss", ("www.theguardian.com",), "国际要闻"),
    PublicSource("media_france24", "France 24", "https://www.france24.com/en/rss", ("www.france24.com",), "国际要闻"),
    PublicSource("media_dw", "德国之声中文", "https://rss.dw.com/rdf/rss-chi-all", ("rss.dw.com", "www.dw.com", "dw.com"), "国际要闻"),
    PublicSource("media_aeon", "Aeon", "https://aeon.co/feed.rss", ("aeon.co", "www.aeon.co"), "散文随笔", max_age_days=60),
    PublicSource("media_espn", "ESPN", "https://www.espn.com/espn/rss/news", ("www.espn.com", "espn.com"), "综合竞技"),
    PublicSource("media_nature", "Nature", "https://www.nature.com/nature.rss", ("www.nature.com", "nature.com"), "科学前沿", max_age_days=60),
    PublicSource("media_sciencenews", "Science News", "https://www.sciencenews.org/feed", ("www.sciencenews.org", "sciencenews.org"), "科学前沿", max_age_days=60),
)
SOURCE_BY_ID = {source.id: source for source in PUBLIC_SOURCES}
INTERVIEW_SOURCE_IDS = frozenset(source.id for source in PUBLIC_SOURCES if source.category == INTERVIEW_CATEGORY)
PUBLIC_ARTICLE_SOURCES = frozenset({"media_yicai", "media_chinawriter_interviews", "media_chinanews_interviews"})
ALLOWED_FEEDS = frozenset(source.url for source in PUBLIC_SOURCES)
INACTIVE_SOURCES = (
    {"id": "media_xiaohongshu", "name": "小红书", "scope": "社区内容",
     "note": "公开浏览需要登录，尚无已核实可用的公开新闻订阅；暂未接入。"},
    {"id": "media_thepaper", "name": "澎湃新闻", "scope": "综合新闻",
     "note": "已核实公开页面，独立列表适配尚未完成；暂未接入。"},
)


def _now():
    return datetime.now(SHANGHAI)


def _cache_policy(cache_control):
    """Describe whether this response may enter the application's shared cache."""
    directives = {part.split("=", 1)[0].strip().lower()
                  for part in cache_control.split(",") if part.strip()}
    maximum = (re.search(r'(?:^|,)\s*s-maxage\s*=\s*"?(\d+)', cache_control, re.I)
               or re.search(r'(?:^|,)\s*max-age\s*=\s*"?(\d+)', cache_control, re.I))
    max_age = int(maximum.group(1)) if maximum else None
    store = not bool(directives & {"private", "no-store"})
    policy = {"store": store, "reuse": store and "no-cache" not in directives and max_age != 0}
    if max_age is not None:
        policy["max_age_seconds"] = max_age
    return policy


def _combine_cache_policies(*policies):
    result = {"store": True, "reuse": True}
    for policy in policies:
        if not isinstance(policy, dict):
            continue
        for key in ("store", "reuse"):
            if policy.get(key) is False:
                result[key] = False
        age = policy.get("max_age_seconds")
        if isinstance(age, int) and age >= 0:
            result["max_age_seconds"] = min(age, result.get("max_age_seconds", age))
    return result


def _cache_note(policy):
    if not policy["store"]:
        return "来源要求私有缓存或不存储，当前读取的内容不进入本站共享缓存。"
    if not policy["reuse"]:
        return "来源要求重新验证，后续读取须重新请求来源。"
    return ""


def _plain(value, limit=1200):
    if not isinstance(value, str):
        return ""
    value = value[:MAX_RESPONSE_BYTES]
    if "<" in value:
        soup = BeautifulSoup(value, "html.parser")
        for node in soup.select("script,style,noscript,iframe,form,button"):
            node.decompose()
        value = soup.get_text(" ", strip=True)
    else:
        value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _safe_url(value, source, *, canonical=True):
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
        query = parts.query
        if canonical:
            query = urlencode([(k, v) for k, v in parse_qsl(query, keep_blank_values=True)
                               if not k.lower().startswith(("utm_", "at_"))
                               and k.lower() not in ("maca", "ocid", "fbclid", "gclid")])
            if source.id == "media_toutiao" and re.fullmatch(r"/(?:trending|article)/\d+/?", parts.path):
                query = ""
            if source.id == "media_yicai" and host == "m.yicai.com":
                host = "www.yicai.com"
        return urlunsplit(("https", host, parts.path or "/", query, ""))
    except ValueError:
        return ""


def _date(value, *, local=False):
    if not isinstance(value, str) or not value.strip():
        return None, "unknown"
    value = value.strip()
    precision = "day" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else "minute"
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None, "unknown"
    if date.tzinfo is None:
        if precision != "day" and not local:
            return None, "unknown"
        date = date.replace(tzinfo=SHANGHAI if local else timezone.utc)
    return date.astimezone(SHANGHAI), precision


def _category(title, default):
    rules = (
        ("篮球", r"NBA|WNBA|basketball|basket-ball|篮球"),
        ("足球", r"football|soccer|premier league|足球|英超|西甲"),
        ("AI与互联网", r"\bAI\b|\bLLM\b|ChatGPT|OpenAI|人工智能|大模型"),
        ("航天航空", r"NASA|spacecraft|astronaut|航天|宇航|卫星"),
        ("芯片与通信", r"semiconductor|芯片|半导体"),
        ("教育校园", r"教育|校园|大学|高考|school|university|education"),
        ("医疗健康", r"医疗|癌症|健康|hospital|cancer|health"),
        ("旅行地理", r"旅游|游客|早市|旅行|travel|tourism"),
        ("房产楼市", r"房地产|楼市|房价"),
        ("公司商业", r"并购|融资|上市公司"),
        ("电影资讯与片单", r"电影|film|cinema"),
    )
    for category, pattern in rules:
        if re.search(pattern, title, re.IGNORECASE):
            return category
    return default


def _body_paragraphs(value, *, min_paragraphs=2, min_characters=160):
    if not isinstance(value, str) or len(value) > 120000:
        return []
    soup = BeautifulSoup(value, "html.parser")
    text = soup.get_text(" ", strip=True)
    if RESTRICTED_TEXT.search(text):
        return []
    for node in soup.select("script,style,iframe,form,button,noscript,.ad,.advertisement"):
        node.decompose()
    paragraphs = [_plain(node.get_text(" ", strip=True), 120000)
                  for node in soup.find_all(["p", "h2", "h3", "li"])
                  if not node.find_parent(["p", "li"])]
    paragraphs = [text for text in paragraphs if text]
    if (len(paragraphs) < min_paragraphs or len(paragraphs) > 150
            or sum(map(len, paragraphs)) < min_characters or any(len(p) > 6000 for p in paragraphs)):
        return []
    return paragraphs


def _article(source, title, url, raw_date, summary, now, *, local=False,
             time_basis="published", body="", publisher="", restricted=False):
    title, url = _plain(title, 300), _safe_url(url, source)
    if not title or not url:
        return None
    date, precision = _date(raw_date, local=local)
    if date and (date < now - timedelta(days=source.max_age_days) or date > now + timedelta(minutes=5)):
        return None
    is_interview = source.category == INTERVIEW_CATEGORY or has_interview_label(title)
    category = INTERVIEW_CATEGORY if is_interview else _category(title, source.category)
    if is_interview and not is_recent_interview({"category": category, "published_at": date.isoformat() if date else "",
                                               "time_basis": time_basis}, now):
        return None
    paragraphs = [] if restricted else _body_paragraphs(body)
    time_basis = time_basis if date else "collected"
    return {
        "id": "media_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
        "title": title, "original_title": title, "source": source.name,
        "publisher": _plain(publisher, 100) or source.name,
        "source_id": source.id, "source_family": "public_media",
        "group": CATEGORY_GROUP[category], "category": category,
        "kind": "访谈" if category == INTERVIEW_CATEGORY else "深读" if source.id in ("media_lifeweek", "media_aeon") else "报道",
        "url": url, "original_url": url, "summary": _plain(summary),
        "summary_origin": SUMMARY_ORIGIN,
        "content_origin": "feed_full" if paragraphs else "source_summary",
        "published_at": date.isoformat() if date and time_basis == "published" else "",
        "updated_at": date.isoformat() if date and time_basis == "updated" else "",
        "discovered_at": now.isoformat(), "time_basis": time_basis,
        "date_precision": precision,
        "time": (("更新 " if time_basis == "updated" else "") + date.strftime("%Y-%m-%d" if precision == "day" else "%Y-%m-%d %H:%M")) if date else "收录 " + now.strftime("%Y-%m-%d %H:%M"),
        "topic": "", "available": bool(paragraphs), "summary_only": not bool(paragraphs),
        "feed_paragraphs": paragraphs, "restricted": bool(restricted),
    }


class _SafeTreeBuilder(ET.TreeBuilder):
    def doctype(self, name, pubid, system):
        raise ValueError("不支持含实体声明的订阅源")


def _parse_feed(content, source, now):
    root = ET.fromstring(content, parser=ET.XMLParser(target=_SafeTreeBuilder()))
    if root.tag == "rss":
        nodes, namespace, atom = root.findall("./channel/item"), "", False
    elif root.tag == RDF + "RDF":
        nodes, namespace, atom = root.findall(RSS1 + "item"), RSS1, False
    elif root.tag == ATOM + "feed":
        nodes, namespace, atom = root.findall(ATOM + "entry"), ATOM, True
    else:
        raise ValueError("公开订阅格式已变化")
    articles = []
    for node in nodes[:300]:
        if atom:
            url = next((link.get("href") for link in node.findall(ATOM + "link")
                        if link.get("rel", "alternate") == "alternate"), "")
            raw_date = node.findtext(ATOM + "published")
            basis = "published" if raw_date else "updated"
            raw_date = raw_date or node.findtext(ATOM + "updated")
            summary, body = node.findtext(ATOM + "summary"), node.findtext(ATOM + "content")
        else:
            url = node.findtext(namespace + "link")
            raw_date = node.findtext(namespace + "pubDate") or node.findtext(DC + "date")
            basis = "published"
            summary = node.findtext(namespace + "description")
            body = node.findtext(CONTENT + "encoded") or (summary if source.description_is_body else "")
        article = _article(source, node.findtext(namespace + "title"), url, raw_date,
                           summary, now, time_basis=basis, body=body)
        if article:
            articles.append(article)
    return articles


def _parse_yicai(content, source, now):
    text = content.decode("utf-8-sig")
    articles = []
    for match in re.finditer(r"var\s+(?:breakNews|headList|latestList)\s*=\s*(\[)", text):
        rows, _ = json.JSONDecoder().raw_decode(text[match.start(1):])
        if not isinstance(rows, list):
            continue
        for row in rows[:150]:
            if not isinstance(row, dict) or row.get("OuterUrl"):
                continue
            url = row.get("url") or ""
            if not isinstance(url, str) or not re.fullmatch(r"/news/\d+\.html", url):
                continue
            article = _article(source, row.get("NewsTitle"), urljoin(source.url, url),
                               row.get("EntityPublishDate") or row.get("CreateDate"),
                               row.get("NewsNotes"), now, local=True,
                               publisher=row.get("NewsSource"),
                               restricted=row.get("LoginLimit") or row.get("isPrivate") or bool(row.get("ProductId")))
            if article:
                # False permits an on-demand read; it is not a claim that the
                # list already contains a complete article.
                article["summary_only"] = bool(article["restricted"])
                articles.append(article)
    if not articles:
        raise ValueError("第一财经公开列表格式已变化")
    return articles


def _parse_toutiao(content, source, now):
    data = json.loads(content)
    if data.get("status") != "success" or not isinstance(data.get("data"), list):
        raise ValueError("今日头条公开热榜暂不可用")
    articles = []
    for row in data["data"][:100]:
        if not isinstance(row, dict):
            continue
        url = _safe_url(row.get("Url"), source)
        if not re.fullmatch(r"https://www\.toutiao\.com/(?:trending|article)/\d+/?", url):
            continue
        article = _article(source, row.get("Title"), url, "", "", now)
        if article:
            interests = row.get("InterestCategory")
            interests = interests if isinstance(interests, list) else [interests]
            categories = {"international": "国际要闻", "sports": "综合竞技", "technology": "AI与互联网", "finance": "宏观经济"}
            category = next((categories[tag] for tag in interests if isinstance(tag, str) and tag in categories), None)
            if category:
                article.update(category=category, group=CATEGORY_GROUP[category])
            article.update(kind="热点", summary_origin="公开热榜标题（未提供摘要与发表时间）")
            articles.append(article)
    return articles


class _LiteralParser:
    """Read only JSON-like Nuxt literals; never evaluate JavaScript expressions."""

    def __init__(self, text, variables=None):
        self.text, self.pos, self.variables = text, 0, variables or {}

    def read(self, depth=0):
        if depth > 80:
            raise ValueError("页面数据嵌套过深")
        self.pos += len(self.text[self.pos:]) - len(self.text[self.pos:].lstrip())
        if self.pos >= len(self.text):
            raise ValueError("页面数据不完整")
        char = self.text[self.pos]
        if char == '"':
            value, end = json.JSONDecoder().raw_decode(self.text[self.pos:])
            self.pos += end
            return value
        if char in "[{":
            self.pos += 1
            result = [] if char == "[" else {}
            end = "]" if char == "[" else "}"
            while True:
                self.text_at_space()
                if self.text[self.pos:self.pos + 1] == end:
                    self.pos += 1
                    return result
                key = None
                if char == "{":
                    if self.text[self.pos:self.pos + 1] == '"':
                        key = self.read(depth + 1)
                    else:
                        match = re.match(r"[A-Za-z_$][\w$]*", self.text[self.pos:])
                        if not match:
                            raise ValueError("页面数据字段格式已变化")
                        key = match.group()
                        self.pos += len(key)
                    self.text_at_space()
                    if self.text[self.pos:self.pos + 1] != ":":
                        raise ValueError("页面数据字段格式已变化")
                    self.pos += 1
                value = self.read(depth + 1)
                if char == "[":
                    result.append(value)
                else:
                    result[key] = value
                self.text_at_space()
                if self.text[self.pos:self.pos + 1] == ",":
                    self.pos += 1
                elif self.text[self.pos:self.pos + 1] != end:
                    raise ValueError("页面含不支持的数据表达式")
        match = re.match(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?", self.text[self.pos:])
        if match:
            self.pos += len(match.group())
            return json.loads(match.group())
        match = re.match(r"void\s+0\b|[A-Za-z_$][\w$]*", self.text[self.pos:])
        if not match:
            raise ValueError("页面含不支持的数据表达式")
        token = match.group()
        self.pos += len(token)
        constants = {"null": None, "true": True, "false": False}
        if token in constants:
            return constants[token]
        if re.fullmatch(r"void\s+0", token):
            return None
        if token in self.variables:
            return self.variables[token]
        raise ValueError("页面含不支持的数据表达式")

    def text_at_space(self):
        self.pos += len(self.text[self.pos:]) - len(self.text[self.pos:].lstrip())

    def complete(self):
        value = self.read()
        if self.text[self.pos:].strip():
            raise ValueError("页面含不支持的数据表达式")
        return value


def _nuxt_data(content):
    soup = BeautifulSoup(content, "html.parser", from_encoding="utf-8")
    script = next((node.get_text() for node in soup.find_all("script")
                   if node.get_text().startswith("window.__NUXT__=")), "")
    prefix = re.match(r"window\.__NUXT__=\(function\(([^)]*)\)\{return\s+", script)
    call = script.rfind("}(")
    if not prefix or call < prefix.end() or not script.rstrip().endswith("));"):
        raise ValueError("三联公开页面数据格式已变化")
    args = _LiteralParser("[" + script[call + 2:].rstrip()[:-3] + "]").complete()
    params = prefix.group(1).split(",")
    if len(args) != len(params):
        raise ValueError("三联公开页面数据格式已变化")
    return _LiteralParser(script[prefix.end():call], dict(zip(params, args))).complete()


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _parse_lifeweek(content, source, now):
    # The site's public router maps article content types to /article/{id}.
    # Require the article's own publication field, excluding magazine/course
    # promotions and undated audio recommendations from the home page.
    data = _nuxt_data(content)
    articles = []
    for row in _walk(data):
        article_id = row.get("article_id") or row.get("contentId") or row.get("id")
        if (row.get("contentType") not in (4, 11, 12, 44, 54)
                or not isinstance(article_id, int) or article_id <= 0 or not row.get("pubTime")):
            continue
        url = urljoin(source.url, "article/" + str(article_id))
        article = _article(source, row.get("title"), url, row.get("pubTime"),
                           row.get("summary") or row.get("daodu") or row.get("subTitle"),
                           now, local=True)
        if article:
            articles.append(article)
    if not articles:
        raise ValueError("三联公开页面未提供可验证的文章链接")
    return articles


def _parse_lifeweek_interviews(content, source, now):
    # This is the publisher's Culture / Interviews column. Recommendations
    # elsewhere in the Nuxt state do not establish membership of this column.
    data = _nuxt_data(content).get("data")
    rows = data[0].get("articleList") if isinstance(data, list) and data and isinstance(data[0], dict) else None
    if not isinstance(rows, list):
        raise ValueError("三联专访列表格式已变化")
    articles, verified = [], 0
    for row in rows[:100]:
        if not isinstance(row, dict):
            continue
        article_id = row.get("id")
        published, _ = _date(row.get("pubTime"), local=True)
        if (type(article_id) is not int or article_id <= 0 or row.get("contentType") not in (4, 44, 54)
                or not _plain(row.get("title")) or published is None):
            continue
        verified += 1
        article = _article(source, row["title"], "https://www.lifeweek.com.cn/article/" + str(article_id),
                           row["pubTime"], row.get("summary") or row.get("daodu"), now, local=True)
        if article and is_recent_interview(article, now):
            articles.append(article)
    if rows and not verified:
        raise ValueError("三联专访列表未提供可验证的文章与发布日期")
    return articles


def _parse_chinawriter_interviews(content, source, now):
    soup = BeautifulSoup(content, "html.parser", from_encoding="utf-8")
    listing = soup.select_one("ul.previous_list")
    if listing is None:
        raise ValueError("中国作家网访谈列表格式已变化")
    articles, verified = [], 0
    rows = listing.select(":scope > li")
    for row in rows[:100]:
        link, date_node = row.select_one("span > a[href]"), row.select_one("em")
        if link is None or date_node is None:
            continue
        url = _safe_url(urljoin(source.url, link.get("href", "")), source)
        date = date_node.get_text(strip=True)
        if (not re.fullmatch(r"https://www\.chinawriter\.com\.cn/n1/\d{4}/\d{4}/c405057-\d+\.html", url)
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or _date(date, local=True)[0] is None
                or not link.get_text(strip=True)):
            continue
        # The list's date is evidence; the date-like URL path is not a fallback.
        verified += 1
        article = _article(source, link.get_text(" ", strip=True), url, date, "", now, local=True)
        if article and is_recent_interview(article, now):
            article["summary_only"] = False  # Public text is fetched only when opened.
            articles.append(article)
    if rows and not verified:
        raise ValueError("中国作家网访谈列表未提供可验证的文章与发布日期")
    return articles


def _parse_chinanews_interviews(content, source, now):
    soup = BeautifulSoup(content, "html.parser", from_encoding="utf-8")
    listing = soup.select_one("#newlist > ul.news_list_ul")
    if listing is None:
        raise ValueError("中新网人物访谈列表格式已变化")
    articles, verified = [], 0
    rows = listing.select(":scope > li")
    for row in rows[:100]:
        link, date_node = row.select_one(".news_title a[href]"), row.select_one(".news_content p.time")
        if link is None or date_node is None:
            continue
        try:
            published = datetime.strptime(date_node.get_text(strip=True), "%Y-%m-%d %H:%M").replace(tzinfo=SHANGHAI)
        except ValueError:
            continue
        url = _safe_url(urljoin(source.url, link.get("href", "")), source)
        if not url or not link.get_text(strip=True):
            continue
        verified += 1
        # The general column also publishes commentary and same-topic videos.
        if not re.fullmatch(r"https://www\.chinanews\.com\.cn/dxw/\d{4}/\d{2}-\d{2}/\d+\.shtml", url):
            continue
        title = link.get_text(" ", strip=True)
        summary_node = row.select_one(".news_content a")
        summary = summary_node.get_text(" ", strip=True) if summary_node else ""
        if not (has_interview_label(title + " " + summary) or re.search(r"——\s*访[^问]", summary)):
            continue
        article = _article(source, title, url, published.isoformat(), summary, now)
        if article:
            article["summary_only"] = False
            articles.append(article)
    if rows and not verified:
        raise ValueError("中新网人物访谈列表未提供可验证的文章与发布日期")
    return articles


def _parse_cctv_interviews(content, source, now):
    payload = json.loads(content)
    data = payload.get("data") if isinstance(payload, dict) else None
    rows = data.get("list") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("央视访谈节目列表格式已变化")
    articles, verified = [], 0
    for row in rows[:100]:
        if not isinstance(row, dict) or type(row.get("mode")) is not int or row["mode"] != 0:
            continue
        stamp = row.get("focus_date")
        if type(stamp) is not int or stamp <= 0:
            continue
        try:
            published = datetime.fromtimestamp(stamp / 1000, tz=SHANGHAI)
        except (ValueError, OverflowError, OSError):
            continue
        url, title = _safe_url(row.get("url"), source), _plain(row.get("title"), 300)
        if not re.fullmatch(r"https://tv\.cctv\.com/\d{4}/\d{2}/\d{2}/VIDE[A-Za-z0-9]+\.shtml", url) or not title:
            continue
        verified += 1
        if re.search(r"预告|宣传片|花絮|精彩片段", title):
            continue
        # focus_date matches the official page's release stamp; time is the
        # earlier broadcast time. Neither the title nor URL substitutes for it.
        article = _article(source, title, url, published.isoformat(), row.get("brief"), now)
        if article:
            article["kind"] = "视频访谈"
            article["summary_origin"] = "来源公开节目简介（完整访谈视频请访问原站）"
            articles.append(article)
    if rows and not verified:
        raise ValueError("央视访谈列表未提供可验证的完整节目与发布时间")
    return articles


def _request(url, source, *, article=False):
    if _safe_url(url, source, canonical=False) != url or (not article and url not in ALLOWED_FEEDS):
        raise ValueError("请求网址不在对应公开来源范围内")
    deadline = time.monotonic() + MAX_REQUEST_SECONDS
    with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT,
                      allow_redirects=False, stream=True) as response:
        if 300 <= response.status_code < 400:
            raise ValueError("来源发生跳转，暂未跟随跳转")
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError("公开来源暂不可用")
        cache_control = response.headers.get("Cache-Control", "")
        length = response.headers.get("Content-Length", "")
        if length.isdigit() and int(length) > MAX_RESPONSE_BYTES:
            raise ValueError("公开来源响应过大")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=32768):
            if time.monotonic() >= deadline:
                raise TimeoutError("读取公开来源超时")
            content.extend(chunk)
            if len(content) > MAX_RESPONSE_BYTES:
                raise ValueError("公开来源响应过大")
        return bytes(content), cache_control


def _deduplicate(articles):
    by_url = {}
    for row in articles:
        previous = by_url.get(row["url"])
        if (previous is None
                or (row.get("category") == INTERVIEW_CATEGORY and previous.get("category") != INTERVIEW_CATEGORY)
                or ((previous.get("category") != INTERVIEW_CATEGORY or row.get("category") == INTERVIEW_CATEGORY)
                    and not previous.get("summary") and row.get("summary"))):
            by_url[row["url"]] = row
    return list(by_url.values())


def _load_source(source, now):
    content, cache_control = _request(source.url, source)
    parser = {"rss": _parse_feed, "yicai": _parse_yicai,
              "toutiao": _parse_toutiao, "lifeweek": _parse_lifeweek,
              "lifeweek_interviews": _parse_lifeweek_interviews,
              "chinawriter_interviews": _parse_chinawriter_interviews,
              "chinanews_interviews": _parse_chinanews_interviews,
              "cctv_interviews": _parse_cctv_interviews}[source.parser]
    articles = _deduplicate(parser(content, source, now))
    articles.sort(key=lambda row: row["published_at"] or row["updated_at"] or row["discovered_at"], reverse=True)
    policy = _cache_policy(cache_control)
    articles = retain_interviews(articles, MAX_ITEMS_PER_SOURCE)
    for article in articles:
        article["cache_policy"] = dict(policy)
    return articles, cache_control


def _error_message(error):
    if isinstance(error, (requests.Timeout, TimeoutError)):
        return "读取公开来源超时"
    if isinstance(error, requests.RequestException):
        return "公开来源连接暂不可用"
    if isinstance(error, (ET.ParseError, json.JSONDecodeError, UnicodeError)):
        return "公开来源格式已变化"
    if isinstance(error, ValueError):
        return _plain(str(error), 120)
    return "公开来源暂不可用"


def load_extended_news_feed():
    """Fetch public lists independently; report failure without invented news."""
    started = _now()
    by_source, states = {}, {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        pending = {pool.submit(_load_source, source, started): source for source in PUBLIC_SOURCES}
        for future in as_completed(pending):
            source = pending[future]
            state = {"id": source.id, "name": source.name, "scope": "公开媒体 · " + source.category,
                     "status": "ok", "count": 0, "checked_at": _now().isoformat(),
                     "source_family": "public_media", "error": "", "note": ""}
            try:
                rows, cache_control = future.result()
                by_source[source.id] = rows
                policy = _cache_policy(cache_control)
                state.update(count=len(rows), cache_control=cache_control, cache_policy=policy,
                             note=_cache_note(policy) or ("" if rows else "近 7 天暂无新访谈" if source.id in INTERVIEW_SOURCE_IDS else "近期无有效条目"))
            except Exception as error:
                state.update(status="error", error=_error_message(error))
            states[source.id] = state
    articles = _deduplicate([row for source in PUBLIC_SOURCES for row in by_source.get(source.id, [])])
    articles.sort(key=lambda row: row["published_at"] or row["updated_at"] or row["discovered_at"], reverse=True)
    sources = [states[source.id] for source in PUBLIC_SOURCES]
    sources.extend({**source, "status": "excluded", "count": 0, "error": "",
                    "source_family": "public_media", "checked_at": ""}
                   for source in INACTIVE_SOURCES)
    policy = _combine_cache_policies(*(state.get("cache_policy") for state in states.values()))
    return {"articles": articles, "sources": sources, "fetched_at": _now().isoformat(),
            "cache_policy": policy,
            "errors": [s["name"] + "：" + s["error"] for s in sources if s["status"] == "error"]}


def fetch_extended_article(article_dict):
    """Use publisher-supplied feed text or explicitly supported public pages."""
    article = article_dict if isinstance(article_dict, dict) else {}
    source_id = article.get("source_id")
    source = SOURCE_BY_ID.get(source_id) if isinstance(source_id, str) else None
    url = _safe_url(article.get("url"), source) if source else ""
    summary = _plain(article.get("summary"))
    result = {"id": _plain(article.get("id"), 100), "status": "summary",
              "title": _plain(article.get("title"), 300), "source": source.name if source else "",
              "source_family": "public_media", "url": url, "original_url": url,
              "published_at": _plain(article.get("published_at"), 50),
              "paragraphs": [summary] if summary else [], "summary_only": True,
              "summary_origin": SUMMARY_ORIGIN, "content_origin": "source_summary",
              "cache_policy": _combine_cache_policies(article.get("cache_policy")),
              "message": "当前显示来源公开摘要；完整内容请查看原文。"}
    if not url:
        result.update(status="error", paragraphs=[], message="文章网址不在对应公开来源范围内")
        return result
    paragraphs = article.get("feed_paragraphs")
    if (not article.get("restricted") and article.get("content_origin") == "feed_full" and isinstance(paragraphs, list)
            and 1 < len(paragraphs) <= 150 and all(isinstance(p, str) and len(p) <= 6000 for p in paragraphs)):
        result.update(status="full", paragraphs=[_plain(p, 6000) for p in paragraphs],
                      summary_only=False, content_origin="feed_full",
                      message="显示来源订阅提供的正文，保留原始语言与原文链接。")
        return result
    readable = ((source.id == "media_yicai" and re.fullmatch(r"https://www\.yicai\.com/news/\d+\.html", url))
                or (source.id == "media_chinawriter_interviews"
                    and re.fullmatch(r"https://www\.chinawriter\.com\.cn/n1/\d{4}/\d{4}/c405057-\d+\.html", url))
                or (source.id == "media_chinanews_interviews"
                    and re.fullmatch(r"https://www\.chinanews\.com\.cn/dxw/\d{4}/\d{2}-\d{2}/\d+\.shtml", url)))
    if readable and not article.get("restricted"):
        try:
            content, cache_control = _request(url, source, article=True)
            result["cache_policy"] = _combine_cache_policies(result["cache_policy"], _cache_policy(cache_control))
            soup = BeautifulSoup(content, "html.parser", from_encoding="utf-8")
            selector = {"media_yicai": "#multi-text", "media_chinawriter_interviews": ".end_article",
                        "media_chinanews_interviews": ".left_zw"}[source.id]
            container = soup.select_one(selector)
            restricted = RESTRICTED_TEXT.search(soup.get_text(" ", strip=True))
            minimum_count, minimum_length = (1, 60) if source.id == "media_yicai" else (2, 160)
            paragraphs = _body_paragraphs(str(container), min_paragraphs=minimum_count,
                                         min_characters=minimum_length) if container and not restricted else []
            if paragraphs:
                result.update(status="full", paragraphs=paragraphs, summary_only=False,
                              content_origin="public_article",
                              message="已读取来源公开正文，保留原文链接。")
        except Exception as error:
            result["status"] = "error"
            result["message"] = _error_message(error) + "；保留来源摘要与原文链接。"
    elif not summary:
        result["message"] = "来源公开列表未提供摘要；请打开原文查看。"
    return result
