"""Bounded public text-interview adapters for three Chinese publishers.

Only publisher-listed article links are followed. Publication dates come from
explicit publication fields, never relative labels, URL IDs or update times.
The shared request helper remains responsible for network and cache boundaries.
"""

from datetime import datetime
from html import escape
import json
import re
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from utils.newspaper_interviews import SHANGHAI, has_interview_label, interview_cutoff


SOURCE_IDS = frozenset({"media_thepaper_interviews", "media_jiemian_interviews", "media_bjnews_interviews"})
_PAPER = "media_thepaper_interviews"
_JIEMIAN = "media_jiemian_interviews"
_BJNEWS = "media_bjnews_interviews"
_HISTORY = {
    _JIEMIAN: tuple(f"https://m.jiemian.com/lists/130_{page}.html" for page in range(2, 11)),
    _BJNEWS: tuple(f"https://www.bjnews.com.cn/culture/{page}.html" for page in range(2, 33)),
}
EXTRA_FEED_URLS = frozenset(url for pages in _HISTORY.values() for url in pages)
MAX_DETAIL_REQUESTS = 16
MAX_LOAD_SECONDS = 25
_ARTICLE_PATTERNS = {
    _PAPER: r"https://www\.thepaper\.cn/newsDetail_forward_\d{1,12}",
    _JIEMIAN: r"https://www\.jiemian\.com/article/\d{1,12}\.html",
    _BJNEWS: r"https://www\.bjnews\.com\.cn/detail/\d{1,20}\.html",
}
_QUESTION = {
    _PAPER: re.compile(r"^澎湃(?:新闻)?\s*[：:]"),
    _JIEMIAN: re.compile(r"^界面(?:新闻|文化|记者)?\s*[：:]"),
    _BJNEWS: re.compile(r"^新京报(?:[·・]?书评周刊)?\s*[：:]"),
}
_NON_TEXT_TITLE = re.compile(r"^(?:【|\[)?\s*(?:视频|直播|音频|播客)|(?:视频|音频)(?:专访|访谈|对话)|[|｜丨]\s*(?:视频|直播|播客)\s*$")
_REPRINT = re.compile(r"本文(?:转载自|转自|摘自|节选自)|原文(?:刊于|载于)|来源\s*[：:]\s*(?:新华社|中新网|中国新闻网|人民日报|央视新闻)")
_PREVIEW = re.compile(r"预告|报名|预约|招募|活动回顾|讲座回顾")


def _soup(content):
    return BeautifulSoup(content, "html.parser", **({"from_encoding": "utf-8"} if isinstance(content, bytes) else {}))


def _yes(value):
    return value is True or value == 1 or value == "1"


def _publication(value):
    """Normalize only a value already identified as a publication field."""
    if type(value) in (int, float) or (isinstance(value, str) and re.fullmatch(r"\d{10,13}", value)):
        try:
            stamp = float(value)
            return datetime.fromtimestamp(stamp / 1000 if stamp >= 100_000_000_000 else stamp, SHANGHAI).isoformat()
        except (ValueError, OverflowError, OSError):
            return ""
    if isinstance(value, str) and re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}(?:[ T]|$)", value.strip()):
        return value.strip().replace("/", "-")
    return ""


def allows_article_url(source, url):
    """Restrict article requests to the canonical public detail route."""
    from utils import newspaper_sources as media

    pattern = _ARTICLE_PATTERNS.get(getattr(source, "id", ""))
    return bool(pattern and isinstance(url, str) and re.fullmatch(pattern, url)
                and media._safe_url(url, source, canonical=False) == url)


def _article_url(value, source):
    from utils import newspaper_sources as media

    if not isinstance(value, str):
        return ""
    url = media._safe_url(urljoin(source.url, value), source)
    if not url:
        return ""
    parts = urlsplit(url)
    host = {"m.jiemian.com": "www.jiemian.com", "m.bjnews.com.cn": "www.bjnews.com.cn"}.get(parts.hostname, parts.hostname)
    canonical = urlunsplit(("https", host, parts.path, parts.query, ""))
    return canonical if allows_article_url(source, canonical) else ""


def _next_props(soup):
    node = soup.select_one("script#__NEXT_DATA__")
    try:
        value = json.loads(node.get_text()) if node else {}
        props = value.get("props", {}).get("pageProps", {})
        return props if isinstance(props, dict) else {}
    except (ValueError, TypeError, AttributeError):
        return {}


def _text_candidate(title, summary=""):
    if _NON_TEXT_TITLE.search(title) or _PREVIEW.search(title):
        return False
    if re.search(r"(?:本期|本系列|本次).{0,50}视频播客|(?:视频|音频)节目", summary[:300]):
        return False
    return has_interview_label(title) or bool(re.search(
        r"圆桌(?:访谈|对话)|我们(?:邀请|对话|采访)|接受.{0,25}专访|本[次文期].{0,30}(?:采访|访谈)", summary))


def _paper_rows(soup, source, now):
    from utils import newspaper_sources as media

    data = _next_props(soup).get("data")
    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
        raise ValueError("澎湃思想市场列表格式已变化")
    articles = []
    for item in data["list"]:
        if not isinstance(item, dict):
            continue
        title = media._plain(item.get("name"), 300)
        if (not _text_candidate(title) or not _yes(item.get("originalFlag"))
                or item.get("contType") not in (0, "0")
                or _yes(item.get("paywalled")) or _yes(item.get("isOutForward"))
                or _yes(item.get("isOutForword")) or item.get("podcastAudioUrl")
                or item.get("trackArticleType", "文章") != "文章"):
            continue
        identifier = str(item.get("contId", ""))
        if not re.fullmatch(r"\d{1,12}", identifier):
            continue
        url = _article_url(f"https://www.thepaper.cn/newsDetail_forward_{identifier}", source)
        published = _publication(item.get("publishTime")) or _publication(item.get("pubTimeLong"))
        row = media._article(source, title, url, published, item.get("summary", ""), now, local=True)
        if row:
            # The official list already identifies an original text interview.
            # Its complete public body is fetched through the reader on demand.
            row["summary_only"] = False
            articles.append(row)
    note = "当前覆盖澎湃公开列表可见的近期访谈，未作为半年完整归档。" if data.get("hasNext") else ""
    return articles, [], note, False


def _list_cards(soup, source):
    from utils import newspaper_sources as media

    cards = []
    if source.id == _JIEMIAN:
        nodes = soup.select(".news-list .news-view")
        for node in nodes:
            anchor = node.select_one("h3 a[href]")
            if anchor:
                title = media._plain(anchor.get_text(" ", strip=True), 300)
                summary_node = node.select_one(".news-excerpt, .news-summary")
                summary = summary_node.get_text(" ", strip=True) if summary_node else ""
                cards.append((title, _article_url(anchor.get("href"), source), summary))
    else:
        nodes = soup.select(".pin_demo")
        for node in nodes:
            heading = node.select_one(".pin_tit")
            anchor = heading.find_parent("a", href=True) if heading else None
            summary_node = node.select_one(".pin_tips")
            if anchor:
                cards.append((media._plain(heading.get_text(" ", strip=True), 300),
                              _article_url(anchor.get("href"), source),
                              summary_node.get_text(" ", strip=True) if summary_node else ""))
    if not nodes:
        raise ValueError("公开文化列表格式已变化")
    return [(title, url, summary) for title, url, summary in cards if url and _text_candidate(title, summary)]


def _detail_data(soup, source):
    from utils import newspaper_sources as media

    if source.id == _PAPER:
        item = _next_props(soup).get("detailData", {}).get("contentDetail", {})
        if (not isinstance(item, dict) or item.get("source") != "澎湃新闻"
                or not _yes(item.get("originalFlag")) or item.get("contType") not in (0, "0")
                or _yes(item.get("paywalled")) or item.get("podcastAudioUrl")
                or item.get("trackArticleType", "文章") != "文章"):
            return {}
        return {"title": media._plain(item.get("name"), 300), "body": item.get("content", ""),
                "published": _publication(item.get("pubTime")) or _publication(item.get("publishTime")),
                "summary": media._plain(item.get("summary"))}
    heading = soup.find("h1")
    title = heading.get_text(" ", strip=True) if heading else ""
    if source.id == _JIEMIAN:
        info = soup.select_one(".article-info")
        container = soup.select_one(".article-content")
        if not info or not re.search(r"来源\s*[：:]\s*界面新闻(?:\s|$)", info.get_text(" ", strip=True)):
            return {}
        timestamp = info.select_one("[data-article-publish-time]")
        published = _publication(timestamp.get("data-article-publish-time")) if timestamp else ""
        if not published:
            for metadata in soup.select(".article-info"):
                match = re.search(r"\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}(?::\d{2})?", metadata.get_text(" ", strip=True))
                if match:
                    published = _publication(match.group())
                    break
    else:
        container = soup.select_one("#contentStr .content-name") or soup.select_one("#contentStr")
        timestamp = soup.select_one(".employ-line .timer")
        published = _publication(timestamp.get_text(" ", strip=True)) if timestamp else ""
        info = soup.select_one(".employ-line")
        if info and _REPRINT.search(info.get_text(" ", strip=True)):
            return {}
    if not container:
        return {}
    summary = soup.select_one('meta[name="description"]') if source.id == _JIEMIAN else container.find("p")
    return {"title": title, "body": str(container), "published": published,
            "summary": media._plain(summary.get("content", "") if summary and summary.name == "meta"
                                     else summary.get_text(" ", strip=True) if summary else "")}


def _detail_paragraphs(data, source):
    from utils import newspaper_sources as media

    body, title = data.get("body"), data.get("title", "")
    if not isinstance(body, str) or not title or _NON_TEXT_TITLE.search(title) or _PREVIEW.search(title):
        return []
    paragraphs = media._body_paragraphs(body, min_paragraphs=4, min_characters=250)
    if (not paragraphs or _REPRINT.search(" ".join(paragraphs))
            or re.search(r"(?:本期|本系列|本次).{0,50}视频播客", " ".join(paragraphs[:3]))):
        return []
    # A genuine publisher-led exchange is stronger evidence than a name,
    # an article about an interview, a video teaser or a book excerpt.
    if sum(bool(_QUESTION[source.id].match(paragraph)) for paragraph in paragraphs) < 2:
        return []
    return paragraphs


def extract_article(content, source):
    """Return the actual complete question/answer body, or an empty result."""
    if getattr(source, "id", "") not in SOURCE_IDS:
        return []
    try:
        return _detail_paragraphs(_detail_data(_soup(content), source), source)
    except (ValueError, TypeError, AttributeError, KeyError):
        return []


def load_source(content, source, now):
    """Read real lists and bounded public detail pages without fabricating dates."""
    from utils import newspaper_sources as media

    if getattr(source, "id", "") not in SOURCE_IDS:
        raise ValueError("不支持的中文访谈来源")
    soup = _soup(content)
    if source.id == _PAPER:
        return _paper_rows(soup, source, now)
    started = time.monotonic()
    articles, controls, visited, notes = [], [], set(), []
    detail_requests, failures, incomplete = 0, 0, False
    pages = (source.url, *_HISTORY[source.id])
    for page_index, page_url in enumerate(pages):
        if page_index:
            links = {urljoin(pages[page_index - 1], node.get("href", "")) for node in soup.select("a[href]")}
            if page_url not in links or page_url not in EXTRA_FEED_URLS:
                break
            if time.monotonic() - started >= MAX_LOAD_SECONDS:
                incomplete = True
                notes.append("历史列表读取达到时间上限，已保留本次核实的访谈。")
                break
            try:
                content, control = media._request(page_url, source)
                controls.append(control)
                soup = _soup(content)
            except Exception:
                failures += 1
                notes.append("部分历史列表暂时无法读取，已保留本次核实的访谈。")
                break
        try:
            cards = _list_cards(soup, source)
        except ValueError:
            if not page_index:
                raise
            failures += 1
            notes.append("部分历史列表格式已变化，已保留本次核实的访谈。")
            break
        page_dates, limited = [], False
        for title, url, summary in cards:
            if url in visited:
                continue
            visited.add(url)
            if detail_requests >= MAX_DETAIL_REQUESTS or time.monotonic() - started >= MAX_LOAD_SECONDS:
                limited = True
                break
            detail_requests += 1
            try:
                detail, control = media._request(url, source, article=True)
                controls.append(control)
                data = _detail_data(_soup(detail), source)
                published, _ = media._date(data.get("published", ""), local=True)
                if published:
                    page_dates.append(published)
                paragraphs = _detail_paragraphs(data, source)
                if not paragraphs:
                    continue
                body = "".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
                row = media._article(source, data["title"], url, data["published"],
                                     data.get("summary") or summary, now, local=True, body=body)
                if row:
                    row["content_origin"] = "public_article"
                    articles.append(row)
            except Exception:
                failures += 1
        if limited:
            incomplete = True
            notes.append("本次候选正文核实达到数量或时间上限，已保留核实通过的访谈。")
            break
        if page_dates and max(page_dates) < interview_cutoff(now):
            break
    else:
        incomplete = True
        notes.append(f"本次最多检查 {len(pages)} 页，半年范围以实际取得的访谈为准。")
    if failures:
        if not articles:
            raise ValueError("候选访谈或历史列表暂未完成读取，请稍后重试")
        notes.append("部分候选暂未完成读取，未以摘要冒充完整文字访谈。")
    return articles, controls, "；".join(dict.fromkeys(notes)), incomplete or bool(failures)
