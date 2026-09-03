"""跨文件聚类：识别同系列视频，以及按添加时间归集的兜底建议。

本模块只产出本地建议（category / suggested_path / reason），
不接触任何 115 写接口。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .classifier import (
    ANIME_EP_BRACKET_RE,
    FANSUB_RE,
    TV_CN_EP_RE,
    TV_CN_SE_RE,
    TV_SE_RE,
    VERSION_TOKENS,
    VIDEO_EXTS,
    YEAR_RE,
)

# 去掉集数、编号后用于聚类的独立数字，必须前后有分隔符，
# 避免误伤 "one2048" 这类字母数字混合词。
STANDALONE_NUM_RE = re.compile(
    r"(?i)(?:^|[\s._\-\[\]])(?:e|ep)?\d{1,4}(?:[\s._\-\[\]]|$)"
)

# 带边界的 E/EP 集数：前面必须是分隔符，后面不能紧跟数字，
# 否则 "one2048" 中的 "e204" 会被当成集数误删。
BOUNDED_EP_RE = re.compile(
    r"(?i)(?:^|[\s._\-\[\]])(?:e|ep)(\d{1,3})(?![0-9])"
)

EP_PATTERNS = (
    TV_SE_RE,
    TV_CN_SE_RE,
    TV_CN_EP_RE,
    ANIME_EP_BRACKET_RE,
    BOUNDED_EP_RE,
    STANDALONE_NUM_RE,
)

MIN_KEY_LEN = 3
# 只对中文或至少 3 个连续字母的键聚类，避免把纯数字或极短键凑成系列。
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
WORD_RE = re.compile(r"[A-Za-z]{3,}")

SERIES_CATEGORY = "系列"


@dataclass
class SeriesGroup:
    key: str
    display_name: str
    file_row_ids: list[int]
    same_parent: bool


def _strip_ext(name: str) -> str:
    return name.rsplit(".", 1)[0] if "." in name else name


def _clean(stem: str) -> str:
    stem = FANSUB_RE.sub(" ", stem)
    for pat in EP_PATTERNS:
        stem = pat.sub(" ", stem)
    stem = YEAR_RE.sub(" ", stem)
    for token in VERSION_TOKENS:
        stem = re.sub(re.escape(token), " ", stem, flags=re.I)
    stem = re.sub(r"[\[\]()（）]+", " ", stem)
    stem = re.sub(r"[._\-]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip()


def _clean_title_cased(name: str) -> str:
    stem = _strip_ext(name)
    cleaned = _clean(stem)
    if cleaned:
        return cleaned
    return stem.strip()


def series_key(name: str) -> str:
    return _clean(_strip_ext(name)).lower()


def _key_is_meaningful(key: str) -> bool:
    return len(key) >= MIN_KEY_LEN and bool(CJK_RE.search(key) or WORD_RE.search(key))


def cluster_series(rows: list[dict]) -> list[SeriesGroup]:
    """rows 需包含 id、name、full_path、extension。返回成员数 >= 2 的分组。"""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        if (row.get("extension") or "").lower() not in VIDEO_EXTS:
            continue
        key = series_key(row["name"])
        if not _key_is_meaningful(key):
            continue
        groups.setdefault(key, []).append(row)

    result = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        parents = {r["full_path"].rsplit("/", 1)[0] for r in members}
        result.append(
            SeriesGroup(
                key=key,
                display_name=_clean_title_cased(members[0]["name"]),
                file_row_ids=[r["id"] for r in members],
                same_parent=len(parents) == 1,
            )
        )
    return result


def _month_bucket(created_at: str | None) -> str:
    if not created_at:
        return ""
    # 115 Open API 的 created 是 Unix 秒级时间戳字符串。
    text = created_at.strip()
    if re.fullmatch(r"\d{9,12}", text):
        import datetime as _dt

        try:
            dt = _dt.datetime.fromtimestamp(int(text), tz=_dt.timezone.utc)
        except (ValueError, OSError, OverflowError):
            return ""
        return dt.strftime("%Y-%m")
    match = re.match(r"(\d{4})-(\d{2})", text)
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2)}"


def time_bucket(created_at: str | None) -> str:
    return _month_bucket(created_at)
