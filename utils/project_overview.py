"""Public project descriptions and release notes, without loading business data."""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path

from utils.ui_theme import _streamlit_page_href


PROJECT_OVERVIEW_VERSION = 3
STATUS_LABELS = {"current": "当前入口", "paused": "已暂停", "archived": "已归档"}
SECTION_LABELS = {"行政": "行政", "教学": "教学", "个人": "个人", "archived": "已归档"}
UPDATES_PATH = Path(__file__).resolve().parents[1] / "config" / "public_project_updates.json"


def project_status(tool: dict) -> str:
    if tool.get("blocked"):
        return "archived"
    return "paused" if tool.get("paused") else "current"


def filter_projects(tools, query="", section="all", status="all") -> list[dict]:
    terms = query.casefold().split()
    result = []
    for tool in tools:
        state = project_status(tool)
        if section != "all" and tool.get("section") != section:
            continue
        if status != "all" and state != status:
            continue
        searchable = " ".join(
            str(tool.get(key, "")) for key in ("code", "title", "desc", "tag", "section")
        ) + " " + STATUS_LABELS[state] + (" 需密码" if tool.get("locked") else "")
        if all(term in searchable.casefold() for term in terms):
            result.append(tool)
    return sorted(result, key=lambda tool: (project_status(tool) == "archived", -int(tool["code"][1:])))


def build_project_rows(tools) -> str:
    rows = []
    for tool in tools:
        state = project_status(tool)
        # Relative paths preserve the hosting prefix, including Cloud's /~/+/ frame.
        href = escape(_streamlit_page_href(tool["page"]).lstrip("/"), quote=True)
        locked = '<span class="overview-badge">🔒 需密码</span>' if tool.get("locked") else ""
        section = SECTION_LABELS.get(tool.get("section"), "")
        action = "查看说明" if state != "current" else "进入项目"
        rows.append(
            '<article class="overview-row">'
            '<div class="overview-name">'
            f'<span class="overview-code">{escape(tool["code"])}</span>'
            f'<a href="{href}" target="_self">{escape(tool["title"])}</a>'
            f'<span class="overview-badge overview-{state}">{STATUS_LABELS[state]}</span>{locked}'
            f'<small>{escape(section)} · {escape(tool.get("tag", ""))}</small>'
            '</div>'
            f'<p>{escape(tool.get("desc", ""))}</p>'
            f'<a class="overview-open" href="{href}" target="_self">{action} →</a>'
            '</article>'
        )
    return '<div class="overview-list">' + "".join(rows) + '</div>'


def load_public_updates() -> list[dict]:
    updates = json.loads(UPDATES_PATH.read_text(encoding="utf-8"))
    return sorted(updates, key=lambda item: item["date"], reverse=True)


def build_update_rows(updates) -> str:
    rows = []
    for item in updates:
        commit = item.get("commit", "")
        source = (
            f'<a href="https://github.com/yaoy2/yao_1/commit/{commit}" target="_blank" '
            'rel="noopener noreferrer">查看变更 ↗</a>'
            if re.fullmatch(r"[0-9a-f]{7,40}", commit) else ""
        )
        rows.append(
            '<article class="overview-update">'
            f'<time>{escape(item["date"])}</time>'
            '<div>'
            f'<strong>{escape(item["title"])}</strong>'
            f'<p>{escape(item["summary"])}</p>'
            f'</div>{source}</article>'
        )
    return '<div class="overview-list">' + "".join(rows) + '</div>'
