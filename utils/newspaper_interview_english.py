"""Bounded readers for public English interviews, with verified full text.

Only official feeds, fixed section pages and their explicitly linked articles
are requested. A teaser, video page or ordinary essay never becomes a full
interview merely because its publisher is registered as an interview source.
"""

from collections import Counter, deque
from html import escape
from itertools import zip_longest
import json
import re
import time
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup


CREATIVE = "media_creativeindependent_interviews"
INTERVIEW = "media_interviewmagazine_interviews"
QUANTA = "media_quanta_interviews"
LEX = "media_lexfridman_interviews"
SOURCE_IDS = frozenset({CREATIVE, INTERVIEW, QUANTA, LEX})
INTERVIEW_FILM = "https://www.interviewmagazine.com/film"
EXTRA_FEED_URLS = frozenset({INTERVIEW_FILM})

MAX_ARTICLE_REQUESTS = 12
MAX_CANDIDATES = 48
MAX_SOURCE_SECONDS = 25
MAX_PAGE_BYTES = 2_000_000
LEX_MAX_PARAGRAPHS = 800
LEX_MAX_SEGMENTS = 2400
LEX_MAX_HTML_CHARACTERS = 1_200_000

_HOSTS = {
    CREATIVE: "thecreativeindependent.com",
    INTERVIEW: "www.interviewmagazine.com",
    QUANTA: "www.quantamagazine.org",
    LEX: "lexfridman.com",
}
_PATHS = {
    CREATIVE: r"/people/[a-z0-9][a-z0-9-]*/",
    INTERVIEW: r"/(?:culture|film|music|art|fashion|literature)/[a-z0-9][a-z0-9-]*/?",
    QUANTA: r"/[a-z0-9][a-z0-9-]*-\d{8}/",
    LEX: r"/[a-z0-9][a-z0-9-]*-transcript/?",
}
_ATOM = "{http://www.w3.org/2005/Atom}"


def allows_article_url(source, url):
    """Allow exact publisher origins and article paths, never media or APIs."""
    source_id = getattr(source, "id", "")
    if source_id not in SOURCE_IDS or not isinstance(url, str):
        return False
    if re.search(r"[\x00-\x20\\]", url):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return (parts.scheme == "https" and parts.netloc == _HOSTS[source_id]
            and not parts.query and not parts.fragment
            and bool(re.fullmatch(_PATHS[source_id], parts.path)))


def _soup(content):
    if not isinstance(content, (bytes, str)) or len(content) > MAX_PAGE_BYTES:
        raise ValueError("公开访谈页面超出读取范围")
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    return BeautifulSoup(text, "html.parser")


def _xml(content):
    from utils import newspaper_sources as media

    return ET.fromstring(content, parser=ET.XMLParser(target=media._SafeTreeBuilder()))


def _article_url(value, source):
    from utils import newspaper_sources as media

    url = media._safe_url(urljoin(source.url, value or ""), source)
    return url if allows_article_url(source, url) else ""


def _publication(soup):
    """Read publication metadata; dateModified and generic dates are excluded."""
    node = soup.select_one('meta[property="article:published_time"], meta[itemprop="datePublished"]')
    if node and node.get("content"):
        return node["content"]
    for script in soup.select('script[type="application/ld+json"]')[:12]:
        try:
            value = json.loads(script.get_text())
        except (TypeError, ValueError):
            continue
        pending = deque(value if isinstance(value, list) else [value])
        inspected = 0
        while pending and inspected < 100:
            item = pending.popleft()
            inspected += 1
            if not isinstance(item, dict):
                continue
            graph = item.get("@graph")
            if isinstance(graph, list):
                pending.extend(graph[:100])
            kinds = item.get("@type", [])
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if (isinstance(kinds, list) and any(kind in {"Article", "NewsArticle", "BlogPosting"}
                                              for kind in kinds if isinstance(kind, str))
                    and isinstance(item.get("datePublished"), str)):
                return item["datePublished"]
    for node in soup.select('time[pubdate][datetime], time[itemprop="datePublished"][datetime], time.entry-date[datetime]'):
        if "updated" not in node.get("class", []):
            return node["datetime"]
    return ""


def _description(soup, fallback=""):
    node = soup.select_one('meta[property="og:description"], meta[name="description"]')
    return node.get("content", "") if node else fallback


def _question_count(soup):
    questions = set()
    for node in soup.find_all(["h2", "h3", "h4", "p"]):
        text = node.get_text(" ", strip=True)
        if "?" not in text or len(text) > 800:
            continue
        if node.name == "p":
            bold = node.find(["strong", "b"])
            if not bold or text != bold.get_text(" ", strip=True):
                continue
        questions.add(text)
    return len(questions)


def _repeated_speakers(labels, *, host=None):
    counts = Counter(labels)
    if host and counts[host] < 2:
        return False
    return sum(count >= 2 for count in counts.values()) >= 2


def _interview_speakers(soup):
    labels = []
    for paragraph in soup.find_all("p"):
        text = paragraph.get_text(" ", strip=True)
        match = re.match(r"^([^:]{1,70}):\s*\S", text)
        if not match:
            continue
        label = match[1].strip()
        if (label.isupper() and any(char.isalpha() for char in label)
                and all(char.isalpha() or char in " .-'’&/()" for char in label)):
            labels.append(label)
    return labels


def _plain_body(soup, *, long=False):
    from utils import newspaper_sources as media

    for node in soup.select("script,style,iframe,form,button,noscript,aside,.caption,.attribution,.advertisement"):
        node.decompose()
    limits = {"max_html_characters": LEX_MAX_HTML_CHARACTERS,
              "max_paragraphs": LEX_MAX_PARAGRAPHS} if long else {}
    return media._body_paragraphs(str(soup), **limits)


def extract_article(content, source):
    """Return a complete, bounded question/answer body or no full-text claim."""
    from utils import newspaper_sources as media

    source_id = getattr(source, "id", "")
    if source_id not in SOURCE_IDS:
        return []
    soup = _soup(content)
    if source_id == CREATIVE:
        container = soup.select_one("#article__main__content .article-section__body")
        if not container or _question_count(container) < 2:
            return []
        return _plain_body(container)
    if source_id == INTERVIEW:
        container = soup.select_one("#post-body")
        if not container or not _repeated_speakers(_interview_speakers(container)):
            return []
        return _plain_body(container)
    if source_id == QUANTA:
        sections = soup.select("#postBody .post__content__section .post__content")
        if not sections:
            return []
        container = BeautifulSoup("".join(str(node) for node in sections), "html.parser")
        for node in container.select("aside,.caption,.attribution,.related,.related-posts"):
            node.decompose()
        text = container.get_text(" ", strip=True)
        if _question_count(container) < 2 or not re.search(r"\binterviews?\b|\bspoke (?:to|with)\b", text, re.I):
            return []
        return _plain_body(container)

    segments = soup.select(".entry-content .ts-segment")
    if not 4 <= len(segments) <= LEX_MAX_SEGMENTS:
        return []
    names, paragraphs, last_name = [], [], ""
    for segment in segments:
        name, text = segment.select_one(".ts-name"), segment.select_one(".ts-text")
        timestamp = segment.select_one(".ts-timestamp")
        if not name or not text or not name.get_text(strip=True) or not text.get_text(strip=True):
            return []
        label = name.get_text(" ", strip=True)
        paragraph = " ".join(part.get_text(" ", strip=True) for part in (name, timestamp, text) if part)
        if len(paragraph) > 6000:
            return []
        if label != last_name:
            names.append(label)
        # The publisher splits one answer into many timestamped spans. Join
        # adjacent spans, retaining every name, timestamp and word, not a slice.
        if paragraphs and label == last_name and len(paragraphs[-1]) + 1 + len(paragraph) <= 6000:
            paragraphs[-1] += " " + paragraph
        else:
            paragraphs.append(paragraph)
        last_name = label
    if not _repeated_speakers(names, host="Lex Fridman"):
        return []
    body = "".join("<p>" + escape(paragraph) + "</p>" for paragraph in paragraphs)
    return media._body_paragraphs(body, max_html_characters=LEX_MAX_HTML_CHARACTERS,
                                  max_paragraphs=LEX_MAX_PARAGRAPHS)


def _creative(content, source, now):
    from utils import newspaper_sources as media

    root = _xml(content)
    if root.tag != _ATOM + "feed":
        raise ValueError("The Creative Independent 公开订阅格式已变化")
    # Remove essays and teasers before the common Atom parser declares full text.
    incomplete = False
    for node in list(root.findall(_ATOM + "entry")):
        body = node.findtext(_ATOM + "content") or ""
        if len(body) > 120000:
            incomplete = True
            root.remove(node)
        elif not body or _question_count(BeautifulSoup(body, "html.parser")) < 2:
            root.remove(node)
    rows = media._parse_feed(ET.tostring(root, encoding="utf-8"), source, now)
    eligible = [row for row in rows if allows_article_url(source, row["url"])]
    verified = [row for row in eligible if row.get("available") and not row.get("summary_only")]
    incomplete = incomplete or len(verified) != len(eligible)
    note = "部分访谈正文未通过完整性或长度检查，已保留验证通过的访谈。" if incomplete else ""
    return verified, [], note, incomplete


def _rss_candidates(content, source, now):
    from utils import newspaper_sources as media

    root = _xml(content)
    if root.tag != "rss":
        raise ValueError("公开访谈订阅格式已变化")
    candidates, seen = [], set()
    for node in root.findall("./channel/item")[:300]:
        description = node.findtext("description") or ""
        urls = [node.findtext("link") or ""]
        if source.id == LEX:
            urls = []
            if "<" in description:
                html = BeautifulSoup(description, "html.parser")
                urls = [a.get("href", "") for a in html.select("a[href]")]
            urls.extend(re.findall(r"https://lexfridman\.com/[a-z0-9-]+-transcript/?", description))
        for value in urls:
            url = _article_url(value, source)
            if not url or url in seen:
                continue
            row = media._article(source, node.findtext("title"), url, node.findtext("pubDate"),
                                 description, now)
            if row:
                candidates.append(row)
                seen.add(url)
        if len(candidates) >= MAX_CANDIDATES:
            break
    return candidates[:MAX_CANDIDATES]


def _list_links(content, source):
    links = []
    for node in _soup(content).select("a[href]"):
        url = _article_url(node.get("href"), source)
        if url and url not in links:
            links.append(url)
            if len(links) >= MAX_CANDIDATES:
                break
    return links


def _read_candidates(candidates, source, now, controls, started):
    from utils import newspaper_sources as media

    articles, notes, fetched, failures = [], [], 0, 0
    for candidate in candidates:
        if fetched >= MAX_ARTICLE_REQUESTS or time.monotonic() - started >= MAX_SOURCE_SECONDS:
            notes.append("本次公开正文检查达到数量或时间上限，已保留验证通过的访谈。")
            break
        url = candidate["url"]
        if not allows_article_url(source, url):
            continue
        fetched += 1
        try:
            content, control = media._request(url, source, article=True)
            controls.append(control)
            soup = _soup(content)
            # Feed pubDate is a publication, not a page's last-modified date.
            raw_date = _publication(soup) or candidate.get("published_at", "")
            title_node = soup.select_one("h1.entry-title, article h1") or soup.select_one("h1")
            title = candidate.get("title") or (title_node.get_text(" ", strip=True) if title_node else "")
            row = media._article(source, title, url, raw_date,
                                 _description(soup, candidate.get("summary", "")), now)
            if not row:
                continue
            paragraphs = extract_article(content, source)
            if not paragraphs:
                expected_interview = source.id in {QUANTA, LEX}
                if source.id == INTERVIEW:
                    container = soup.select_one("#post-body")
                    expected_interview = bool(container and _repeated_speakers(_interview_speakers(container)))
                if expected_interview:
                    notes.append("部分访谈正文未通过完整性或长度检查，已保留验证通过的访谈。")
                continue
            row.update(feed_paragraphs=paragraphs, available=True, summary_only=False,
                       content_origin="public_article")
            articles.append(row)
        except Exception:
            failures += 1
            notes.append("部分公开页面暂时无法读取，已保留本次验证通过的访谈。")
    if not articles and failures:
        raise ValueError("公开访谈正文读取失败，本次未取得可验证的完整访谈")
    return articles, controls, " ".join(dict.fromkeys(notes)), bool(notes)


def load_source(content, source, now):
    """Return rows, extra cache headers, a note and incomplete-collection flag."""
    from utils import newspaper_sources as media

    if source.id not in SOURCE_IDS:
        raise ValueError("未登记的英文访谈来源")
    if source.id == CREATIVE:
        return _creative(content, source, now)
    started, controls, prefix_note = time.monotonic(), [], ""
    if source.id in {QUANTA, LEX}:
        candidates = _rss_candidates(content, source, now)
    else:
        groups = [_list_links(content, source)]
        if source.url != INTERVIEW_FILM:
            try:
                extra, control = media._request(INTERVIEW_FILM, source)
                controls.append(control)
                groups.append(_list_links(extra, source))
            except Exception:
                prefix_note = "补充栏目暂时无法读取，已保留主栏目发现的候选。"
        urls = []
        for group in zip_longest(*groups):
            for url in group:
                if url and url not in urls:
                    urls.append(url)
        if not urls:
            raise ValueError("Interview Magazine 公开列表未提供可验证的文章链接")
        candidates = [{"url": url} for url in urls[:MAX_CANDIDATES]]
    rows, controls, note, incomplete = _read_candidates(candidates, source, now, controls, started)
    return rows, controls, " ".join(value for value in (prefix_note, note) if value), incomplete or bool(prefix_note)
