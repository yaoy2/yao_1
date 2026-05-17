# -*- coding: utf-8 -*-
"""
wechat_core.py
微信公众号文章归档核心逻辑。
供 wechat_app.py 调用。
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from slugify import slugify


TARGET_DIRS = {
    "raw": r"E:\GoogleDrive\Obsidian Vault\00\LLM_WIKI\raw",
    "course": r"E:\GoogleDrive\Obsidian Vault (1)\ChatGPT\50_教学_课题",
    "competition": r"E:\GoogleDrive\Obsidian Vault (1)\ChatGPT\40_学生_竞赛",
}

TYPE_ALIASES = {
    "academy": "academy",
    "学院": "academy",
    "健康学院": "academy",
    "归档学院": "academy",

    "raw": "raw",
    "归档raw": "raw",

    "course": "course",
    "课题": "course",
    "教学": "course",
    "教学课题": "course",

    "competition": "competition",
    "竞赛": "competition",
    "比赛": "competition",
    "学生竞赛": "competition",
}

ARCHIVE_TYPE_LABELS = {
    "raw": "raw 原始留存",
    "academy": "学院资料",
    "course": "教学课题",
    "competition": "学生竞赛",
}

ROUTE_DEFINITIONS = {
    "link_raw": {
        "title": "路线 A：归档 raw（公众号链接）",
        "streamlit_supported": True,
        "description": "Playwright 抓取公众号文章，转 Markdown 后保存到 Obsidian raw 目录。",
    },
    "link_course": {
        "title": "路线 B：归档课题（公众号链接）",
        "streamlit_supported": True,
        "description": "Playwright 抓取公众号文章，保存到课题目录；IMA 上传部分交给 WorkBuddy。",
    },
    "link_competition": {
        "title": "路线 B：归档竞赛（公众号链接）",
        "streamlit_supported": True,
        "description": "Playwright 抓取公众号文章，保存到竞赛目录；IMA 上传部分交给 WorkBuddy。",
    },
    "file_academy": {
        "title": "路线 C：归档学院（本地文件）",
        "streamlit_supported": False,
        "description": "本路线需要 IMA 上传到健康学院-2026，当前 Python 窗口只做识别与提示。",
    },
    "file_course": {
        "title": "路线 D：归档课题（本地文件）",
        "streamlit_supported": True,
        "description": "复制本地文件到课题 GoogleDrive 目录；IMA 上传部分交给 WorkBuddy。",
    },
    "file_competition": {
        "title": "路线 D：归档竞赛（本地文件）",
        "streamlit_supported": True,
        "description": "复制本地文件到竞赛 GoogleDrive 目录；IMA 上传部分交给 WorkBuddy。",
    },
    "unknown": {
        "title": "尚未识别路线",
        "streamlit_supported": False,
        "description": "请提供公众号链接或本地文件路径，并写明 raw / 学院 / 课题 / 竞赛。",
    },
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
)

WINDOWS_ILLEGAL_CHARS = r'<>:"/\|?*'
BLOCK_TAGS = {"p", "div", "section", "article", "blockquote", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas"}


def now_date() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def clean_filename(name: str, max_len: int = 120) -> str:
    name = (name or "未命名文章").strip()
    for ch in WINDOWS_ILLEGAL_CHARS:
        name = name.replace(ch, " ")
    name = re.sub(r"\s+", " ", name).strip()
    name = slugify(name, allow_unicode=True, separator="_")
    if not name:
        name = "未命名文章"
    return name[:max_len].strip("_")


def unique_file_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    idx = 1
    while True:
        candidate = parent / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def yaml_quote(value: Optional[str]) -> str:
    if value is None:
        return '""'
    value = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()
    return f'"{value}"'


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return text.strip()


def extract_urls(text: str) -> List[str]:
    if not text:
        return []
    candidates = re.findall(r"https?://mp\.weixin\.qq\.com/[^\s\"'<>，。；、]+", text)
    # 去掉常见右侧标点
    cleaned = []
    seen = set()
    for u in candidates:
        u = u.strip().rstrip(").,，。；;]")
        if u and u not in seen:
            seen.add(u)
            cleaned.append(u)
    return cleaned


def extract_local_paths(text: str) -> List[str]:
    if not text:
        return []

    quoted = re.findall(r'"([A-Za-z]:\\[^"]+)"', text)
    extensions = r"pdf|docx?|xlsx?|pptx?|png|jpe?g|gif|webp|txt|md|csv"
    unquoted = re.findall(rf"([A-Za-z]:\\[^\r\n\"<>|]+\.(?:{extensions}))", text, flags=re.IGNORECASE)

    paths: List[str] = []
    seen = set()
    for raw in quoted + unquoted:
        path = raw.strip().rstrip("，。；;)")
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def detect_archive_type(text: str, fallback: Optional[str] = None) -> Optional[str]:
    text = (text or "").lower()
    for key, val in TYPE_ALIASES.items():
        if key.lower() in text:
            return val
    return fallback


def classify_archive_request(text: str, fallback: Optional[str] = "course") -> Dict[str, object]:
    urls = extract_urls(text)
    local_paths = extract_local_paths(text)
    archive_type = detect_archive_type(text, fallback=fallback)

    if urls:
        input_kind = "link"
    elif local_paths:
        input_kind = "file"
    else:
        input_kind = "unknown"

    route_id = "unknown"
    if input_kind == "link" and archive_type in {"raw", "course", "competition"}:
        route_id = f"link_{archive_type}"
    elif input_kind == "file" and archive_type in {"academy", "course", "competition"}:
        route_id = f"file_{archive_type}"

    route_def = ROUTE_DEFINITIONS.get(route_id, ROUTE_DEFINITIONS["unknown"])
    return {
        "route_id": route_id,
        "input_kind": input_kind,
        "archive_type": archive_type,
        "archive_label": ARCHIVE_TYPE_LABELS.get(archive_type or "", "未识别"),
        "urls": urls,
        "local_paths": local_paths,
        "title": route_def["title"],
        "description": route_def["description"],
        "streamlit_supported": route_def["streamlit_supported"],
    }


def archive_local_files(paths: List[str], archive_type: str, progress_callback=None) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []
    if archive_type not in {"course", "competition"}:
        return [
            {
                "ok": False,
                "path": path,
                "message": f"{ARCHIVE_TYPE_LABELS.get(archive_type, archive_type)} 本地文件归档需要 WorkBuddy/IMA 执行。",
            }
            for path in paths
        ]

    target_root = Path(TARGET_DIRS[archive_type])
    ensure_dir(target_root)

    for idx, raw_path in enumerate(paths, start=1):
        source = Path(raw_path)
        result = {"ok": False, "source": raw_path, "path": "", "message": ""}
        if progress_callback:
            progress_callback(f"[{idx}/{len(paths)}] 正在复制：{raw_path}")

        if not source.exists() or not source.is_file():
            result["message"] = f"文件不存在或不是文件：{raw_path}"
            results.append(result)
            if progress_callback:
                progress_callback(f"✗ {result['message']}")
            continue

        try:
            target = unique_file_path(target_root / source.name)
            shutil.copy2(source, target)
            result.update({"ok": True, "path": str(target), "message": f"OK | {source} -> {target}"})
            if progress_callback:
                progress_callback(f"✓ 已复制：{target}")
        except Exception as e:
            result["message"] = f"{type(e).__name__}: {e}"
            if progress_callback:
                progress_callback(f"✗ 复制失败：{result['message']}")

        results.append(result)

    return results


def extract_meta(page, url: str) -> Dict[str, str]:
    html = page.content()
    soup = BeautifulSoup(html, "lxml")

    def text_one(selector: str) -> str:
        node = soup.select_one(selector)
        return normalize_text(node.get_text(" ", strip=True)) if node else ""

    title = text_one("h1.rich_media_title") or text_one("#activity-name") or page.title()
    account = text_one("#js_name") or text_one(".rich_media_meta_text")
    author = text_one("#js_author") or ""

    published = ""
    meta_time = soup.select_one('meta[property="article:published_time"], meta[name="publish_time"]')
    if meta_time and meta_time.get("content"):
        published = normalize_text(meta_time.get("content", ""))[:10]

    if not published:
        text = soup.get_text("\n", strip=True)
        m = re.search(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})", text)
        if m:
            y, mo, d = m.groups()
            published = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"

    return {
        "title": title or "未命名文章",
        "account": account or "",
        "author": author or "",
        "published": published or "",
        "source": url,
        "archived": now_date(),
    }


def get_img_url(tag: Tag) -> str:
    for key in ["data-src", "data-backsrc", "src"]:
        val = tag.get(key)
        if val:
            return val.strip()
    return ""


def guess_ext_from_url_or_type(url: str, content_type: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    wx_fmt = ""
    if "wx_fmt" in qs and qs["wx_fmt"]:
        wx_fmt = qs["wx_fmt"][0].lower()

    mapping = {
        "jpeg": ".jpg",
        "jpg": ".jpg",
        "png": ".png",
        "gif": ".gif",
        "webp": ".webp",
        "bmp": ".bmp",
    }
    if wx_fmt in mapping:
        return mapping[wx_fmt]

    content_type = (content_type or "").lower()
    if "png" in content_type:
        return ".png"
    if "gif" in content_type:
        return ".gif"
    if "webp" in content_type:
        return ".webp"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"

    suffix = Path(parsed.path).suffix.lower()
    if suffix in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
        return ".jpg" if suffix == ".jpeg" else suffix

    return ".jpg"


class MarkdownBuilder:
    def __init__(self, article_dir_name: str, assets_dir: Path, timeout: int = 30):
        self.article_dir_name = article_dir_name
        self.assets_dir = assets_dir
        self.timeout = timeout
        self.lines: List[str] = []
        self.image_index = 1
        self.image_cache: Dict[str, str] = {}
        self.image_success = 0
        self.image_failed = 0

    def append_blank(self) -> None:
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def append_raw(self, text: str) -> None:
        self.lines.append(text)

    def download_image(self, url: str, alt: str = "图片") -> str:
        if not url:
            return ""

        if url in self.image_cache:
            return f"![{alt}]({self.image_cache[url]})"

        ensure_dir(self.assets_dir)

        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://mp.weixin.qq.com/",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            ext = guess_ext_from_url_or_type(url, content_type)

            filename = f"img_{self.image_index:03d}{ext}"
            self.image_index += 1

            save_path = self.assets_dir / filename
            save_path.write_bytes(response.content)

            rel_path = f"assets/{self.article_dir_name}/{filename}".replace("\\", "/")
            self.image_cache[url] = rel_path
            self.image_success += 1
            return f"![{alt}]({rel_path})"

        except Exception as e:
            self.image_failed += 1
            return f"<!-- 图片下载失败: {url} | {type(e).__name__}: {e} -->"

    def walk(self, node) -> None:
        if isinstance(node, NavigableString):
            text = normalize_text(str(node))
            if text:
                self.lines.append(text)
            return

        if not isinstance(node, Tag):
            return

        tag = node.name.lower() if node.name else ""

        if tag in SKIP_TAGS:
            return

        class_str = " ".join(node.get("class", [])) if node.get("class") else ""
        if any(key in class_str for key in ["video", "audio", "mp_common_widget", "js_editor_card"]):
            self.append_blank()
            self.append_raw("<!-- 微信特殊组件，请查看原文 -->")
            self.append_blank()
            return

        if tag == "br":
            self.append_blank()
            return

        if tag == "img":
            img_url = get_img_url(node)
            alt = normalize_text(node.get("alt", "")) or "图片"
            md_img = self.download_image(img_url, alt=alt)
            if md_img:
                self.append_blank()
                self.append_raw(md_img)
                self.append_blank()
            return

        if tag == "a":
            href = node.get("href", "").strip()
            text = normalize_text(node.get_text(" ", strip=True))
            if href and text:
                self.lines.append(f"[{text}]({href})")
            elif text:
                self.lines.append(text)
            return

        is_block = tag in BLOCK_TAGS
        if is_block:
            self.append_blank()

        for child in node.children:
            self.walk(child)

        if is_block:
            self.append_blank()

    def to_markdown(self) -> str:
        out: List[str] = []
        prev_blank = False
        buffer_inline: List[str] = []

        def flush_inline():
            nonlocal buffer_inline
            if buffer_inline:
                joined = "".join(buffer_inline).strip()
                if joined:
                    out.append(joined)
                buffer_inline = []

        for line in self.lines:
            if line == "":
                flush_inline()
                if not prev_blank:
                    out.append("")
                prev_blank = True
            elif line.startswith("![") or line.startswith("<!--"):
                flush_inline()
                if out and out[-1] != "":
                    out.append("")
                out.append(line)
                out.append("")
                prev_blank = True
            else:
                buffer_inline.append(line)
                prev_blank = False

        flush_inline()

        md = "\n".join(out)
        md = re.sub(r"\n{3,}", "\n\n", md)
        return md.strip()


def build_markdown(meta: Dict[str, str], body_md: str) -> str:
    title = meta["title"]
    account = meta.get("account", "")
    author = meta.get("author", "")
    source = meta.get("source", "")
    published = meta.get("published", "")
    archived = meta.get("archived", now_date())

    if not body_md.strip():
        body_md = "本文内容为空或主要为图片，请查看原文。"

    front = [
        "---",
        f"title: {yaml_quote(title)}",
        f"account: {yaml_quote(account)}",
        f"author: {yaml_quote(author)}",
        f"source: {yaml_quote(source)}",
        f"published: {yaml_quote(published)}",
        f"archived: {yaml_quote(archived)}",
        "---",
        "",
        f"# {title}",
        "",
        f"> 原文链接：[查看原文]({source})  ",
        f"> 公众号：{account or '未知'} | 发布时间：{published or '未知'}",
        "",
        body_md,
        "",
    ]
    return "\n".join(front)


def save_log(log_dir: Path, name: str, message: str) -> None:
    ensure_dir(log_dir)
    path = log_dir / f"{name}_{now_date()}.log"
    with path.open("a", encoding="utf-8") as f:
        f.write(message.rstrip() + "\n")


def archive_one(page, url: str, archive_type: str, timeout: int = 30, dry_run: bool = False) -> Dict[str, object]:
    target_root = Path(TARGET_DIRS[archive_type])
    log_dir = Path.cwd() / "logs"

    result = {
        "ok": False,
        "url": url,
        "title": "",
        "path": "",
        "images_ok": 0,
        "images_failed": 0,
        "message": "",
    }

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        page.wait_for_selector("#js_content", timeout=timeout * 1000)
        page.wait_for_timeout(1500)

        try:
            page.evaluate("""
                async () => {
                    for (let y = 0; y < document.body.scrollHeight; y += 600) {
                        window.scrollTo(0, y);
                        await new Promise(r => setTimeout(r, 80));
                    }
                    window.scrollTo(0, 0);
                }
            """)
        except Exception:
            pass

        html = page.content()
        soup = BeautifulSoup(html, "lxml")
        content = soup.select_one("#js_content")

        meta = extract_meta(page, url)
        result["title"] = meta["title"]

        title_clean = clean_filename(meta["title"])
        account_clean = clean_filename(meta.get("account", ""))
        date_part = meta.get("published") or meta.get("archived") or now_date()

        filename_base = clean_filename(f"{date_part}_{account_clean}_{title_clean}") if account_clean else clean_filename(f"{date_part}_{title_clean}")
        article_dir_name = filename_base
        assets_dir = target_root / "assets" / article_dir_name
        md_path = unique_file_path(target_root / f"{filename_base}.md")

        if dry_run:
            msg = f"DRY-RUN | {url} | {meta['title']} | {meta.get('account','')} | {meta.get('published','')}"
            save_log(log_dir, "success", msg)
            result.update({"ok": True, "message": msg})
            return result

        builder = MarkdownBuilder(article_dir_name=article_dir_name, assets_dir=assets_dir, timeout=timeout)

        if content:
            for child in content.children:
                builder.walk(child)

        body_md = builder.to_markdown()
        md = build_markdown(meta, body_md)

        ensure_dir(target_root)
        md_path.write_text(md, encoding="utf-8")

        ok_msg = (
            f"OK | {url} | {md_path} | "
            f"images_ok={builder.image_success} | images_failed={builder.image_failed}"
        )
        save_log(log_dir, "success", ok_msg)
        result.update({
            "ok": True,
            "path": str(md_path),
            "images_ok": builder.image_success,
            "images_failed": builder.image_failed,
            "message": ok_msg,
        })
        return result

    except PlaywrightTimeoutError as e:
        msg = f"TIMEOUT | {url} | 等待页面或 #js_content 超时：{e}"
        save_log(log_dir, "failed", msg)
        result["message"] = msg
        return result
    except Exception as e:
        msg = f"FAILED | {url} | {type(e).__name__}: {e}"
        save_log(log_dir, "failed", msg)
        result["message"] = msg
        return result


def archive_urls(urls: List[str], archive_type: str, headless: bool = True, interval: float = 2.0, timeout: int = 30, progress_callback=None) -> List[Dict[str, object]]:
    results: List[Dict[str, object]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=headless)
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 1600})
        page = context.new_page()

        for idx, url in enumerate(urls, start=1):
            if progress_callback:
                progress_callback(f"[{idx}/{len(urls)}] 正在处理：{url}")
            result = archive_one(page, url, archive_type=archive_type, timeout=timeout)
            results.append(result)
            if progress_callback:
                if result["ok"]:
                    progress_callback(f"✓ 成功：{result.get('title','')} | 图片 {result.get('images_ok',0)} 张 | {result.get('path','')}")
                else:
                    progress_callback(f"✗ 失败：{result.get('message','')}")
            if idx < len(urls):
                time.sleep(interval)

        context.close()
        browser.close()

    return results
