from __future__ import annotations

import re
from dataclasses import asdict, dataclass


VIDEO_EXTS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".ts",
    ".m2ts",
    ".webm",
    ".m4v",
    ".rmvb",
    ".mpg",
    ".mpeg",
    ".iso",
}
SUBTITLE_EXTS = {".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".wma"}

ANIME_HINTS = ("动漫", "动画", "番剧", "tv动画", "剧场版", "ova", "oad")
DOC_HINTS = ("纪录片", "documentary", "纪实")
VARIETY_HINTS = ("综艺", "晚会", "访谈", "真人秀")
MUSIC_HINTS = ("演唱会", "concert", "music video", " mv", "mv.", "live concert")
GENERIC_VIDEO_HINTS = ("录屏", "教程", "课件", "lecture", "vlog", "素材", "cam")
VERSION_TOKENS = (
    "2160p",
    "1080p",
    "720p",
    "480p",
    "4k",
    "bluray",
    "blu-ray",
    "web-dl",
    "webdl",
    "webrip",
    "remux",
    "hdr10",
    "hdr",
    "dolby",
    "atmos",
    "h265",
    "h264",
    "x265",
    "x264",
    "hevc",
    "avc",
    "dts",
    "aac",
    "truehd",
    "atmos",
    "国语",
    "粤语",
    "中字",
    "简繁",
    "双语",
)

TV_SE_RE = re.compile(r"(?i)s(\d{1,2})e(\d{1,3})")
TV_CN_SE_RE = re.compile(r"第\s*(\d{1,2})\s*季\s*第\s*(\d{1,3})\s*集")
TV_CN_EP_RE = re.compile(r"第\s*(\d{1,3})\s*[集期话]")
TV_EP_RE = re.compile(r"(?i)(?:e|ep)(\d{2,3})")
YEAR_RE = re.compile(r"(?:[\(\[（._\-\s]|^)((?:19|20)\d{2})(?:[\)\]）._\-\s]|$)")
FANSUB_RE = re.compile(r"^\[[^\]]+\]")
ANIME_EP_BRACKET_RE = re.compile(r"\[(\d{2,3})\]")


@dataclass(frozen=True)
class Classification:
    category: str
    suggested_name: str
    suggested_path: str
    confidence: str
    reason: str
    title: str = ""
    year: str = ""
    season: str = ""
    episode: str = ""
    version: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _ext(name: str) -> str:
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def _has_hint(text: str, hints: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(hint.lower() in lowered for hint in hints)


def _collect_version(name: str) -> str:
    lowered = name.lower()
    found = []
    for token in VERSION_TOKENS:
        if token in lowered and token not in found:
            found.append(token)
    return " ".join(found)


def _clean_title(name: str) -> str:
    stem = name.rsplit(".", 1)[0] if "." in name else name
    stem = FANSUB_RE.sub("", stem)
    stem = TV_SE_RE.sub(" ", stem)
    stem = TV_CN_SE_RE.sub(" ", stem)
    stem = TV_CN_EP_RE.sub(" ", stem)
    stem = ANIME_EP_BRACKET_RE.sub(" ", stem)
    stem = YEAR_RE.sub(" ", stem)
    for token in VERSION_TOKENS:
        stem = re.sub(re.escape(token), " ", stem, flags=re.I)
    stem = re.sub(r"[._\[\]\(\)（）\-]+", " ", stem)
    return re.sub(r"\s+", " ", stem).strip()


def _join_path(*parts: str) -> str:
    cleaned = [part.strip("/").strip() for part in parts if part and part.strip("/").strip()]
    return "/" + "/".join(cleaned)


def classify_item(
    name: str,
    full_path: str = "",
    is_directory: bool = False,
    extension: str = "",
) -> Classification:
    if is_directory:
        return Classification(
            category="其他",
            suggested_name=name,
            suggested_path=full_path or f"/{name}",
            confidence="low",
            reason="这是文件夹，当前只对文件生成移动建议。",
            title=name,
        )

    ext = (extension or _ext(name)).lower()
    if ext and not ext.startswith("."):
        ext = "." + ext
    haystack = f"{full_path} {name}"
    title = _clean_title(name) or name.rsplit(".", 1)[0]
    version = _collect_version(name)
    year_match = YEAR_RE.search(name) or YEAR_RE.search(full_path)
    year = year_match.group(1) if year_match else ""

    if ext in SUBTITLE_EXTS:
        return Classification(
            category="字幕",
            suggested_name=name,
            suggested_path=_join_path("字幕", name),
            confidence="high",
            reason="扩展名是字幕文件。",
            title=title,
            year=year,
            version=version,
        )
    if ext in ARCHIVE_EXTS:
        return Classification(
            category="压缩包",
            suggested_name=name,
            suggested_path=_join_path("压缩包", name),
            confidence="high",
            reason="扩展名是压缩包。",
            title=title,
            year=year,
        )
    if ext in IMAGE_EXTS:
        return Classification(
            category="图片",
            suggested_name=name,
            suggested_path=_join_path("图片", name),
            confidence="high",
            reason="扩展名是图片。",
            title=title,
        )
    if ext in AUDIO_EXTS:
        return Classification(
            category="其他",
            suggested_name=name,
            suggested_path=_join_path("音频", name),
            confidence="medium",
            reason="这是音频文件，当前不按影视剧分类。",
            title=title,
            year=year,
        )
    if ext and ext not in VIDEO_EXTS:
        return Classification(
            category="其他",
            suggested_name=name,
            suggested_path=_join_path("其他", name),
            confidence="medium",
            reason=f"扩展名 {ext} 不是当前规则处理的视频类型。",
            title=title,
        )

    if _has_hint(haystack, ANIME_HINTS) or FANSUB_RE.search(name):
        season, episode, confidence, reason = _tv_fields(name)
        if not episode:
            bracket_ep = ANIME_EP_BRACKET_RE.search(name)
            if bracket_ep:
                episode = bracket_ep.group(1).zfill(2)
                confidence = "medium"
                reason = "文件名带字幕组标签和集数，按动漫处理。"
            else:
                confidence = "medium"
                reason = "路径或文件名含动漫相关词，但集数不完整。"
        else:
            reason = "文件名同时符合动漫特征和剧集编号。"
            confidence = "high" if FANSUB_RE.search(name) or _has_hint(haystack, ANIME_HINTS) else confidence
        suggested = _anime_name(title, year, season, episode, ext)
        return Classification(
            category="动漫",
            suggested_name=suggested,
            suggested_path=_join_path("动漫", title, f"Season {season}" if season else "", suggested),
            confidence=confidence,
            reason=reason,
            title=title,
            year=year,
            season=season,
            episode=episode,
            version=version,
        )

    if _has_hint(haystack, DOC_HINTS):
        suggested = _movie_name(title, year, version, ext)
        return Classification(
            category="纪录片",
            suggested_name=suggested,
            suggested_path=_join_path("纪录片", year or "未知年份", suggested),
            confidence="medium",
            reason="文件名或路径含纪录片相关词。",
            title=title,
            year=year,
            version=version,
        )

    if _has_hint(haystack, VARIETY_HINTS) or TV_CN_EP_RE.search(name) and "期" in name:
        suggested = name
        return Classification(
            category="综艺",
            suggested_name=suggested,
            suggested_path=_join_path("综艺", title, suggested),
            confidence="medium",
            reason="文件名或路径含综艺相关词，或使用“第N期”编号。",
            title=title,
            year=year,
            version=version,
        )

    if _has_hint(haystack, MUSIC_HINTS):
        return Classification(
            category="音乐视频",
            suggested_name=name,
            suggested_path=_join_path("音乐视频", title, name),
            confidence="medium",
            reason="文件名或路径含演唱会/MV 相关词。",
            title=title,
            year=year,
        )

    season, episode, tv_confidence, tv_reason = _tv_fields(name)
    if season and episode:
        suggested = _tv_name(title, year, season, episode, ext)
        return Classification(
            category="电视剧",
            suggested_name=suggested,
            suggested_path=_join_path("电视剧", title, f"Season {season}", suggested),
            confidence=tv_confidence,
            reason=tv_reason,
            title=title,
            year=year,
            season=season,
            episode=episode,
            version=version,
        )

    if _has_hint(haystack, GENERIC_VIDEO_HINTS) and ext in VIDEO_EXTS:
        return Classification(
            category="普通视频",
            suggested_name=name,
            suggested_path=_join_path("普通视频", name),
            confidence="medium",
            reason="视频文件名更像录屏、教程或素材，而不是影视剧。",
            title=title,
        )

    if year and ext in VIDEO_EXTS:
        suggested = _movie_name(title, year, version, ext)
        return Classification(
            category="电影",
            suggested_name=suggested,
            suggested_path=_join_path("电影", year, suggested),
            confidence="medium" if version else "low",
            reason="视频文件名含年份，按电影候选处理，不确定则请人工核对。",
            title=title,
            year=year,
            version=version,
        )

    if ext in VIDEO_EXTS:
        return Classification(
            category="待识别",
            suggested_name=name,
            suggested_path=_join_path("待识别", name),
            confidence="low",
            reason="这是视频，但文件名没有足够的电影/剧集/动漫特征，不强行分类。",
            title=title,
            year=year,
            version=version,
        )

    return Classification(
        category="待识别",
        suggested_name=name,
        suggested_path=_join_path("待识别", name),
        confidence="low",
        reason="没有足够信息判断类型。",
        title=title,
    )


def _tv_fields(name: str) -> tuple[str, str, str, str]:
    match = TV_SE_RE.search(name) or TV_CN_SE_RE.search(name)
    if match:
        season = match.group(1).zfill(2)
        episode = match.group(2).zfill(2)
        return season, episode, "high", "文件名含季和集编号。"
    ep_match = TV_CN_EP_RE.search(name) or TV_EP_RE.search(name)
    if ep_match:
        episode = ep_match.group(1).zfill(2)
        return "", episode, "low", "只看到集数，没有明确季信息，置信度低。"
    return "", "", "low", "没有识别到季集编号。"


def _movie_name(title: str, year: str, version: str, ext: str) -> str:
    parts = [title]
    if year:
        parts.append(f"({year})")
    if version:
        parts.append(version)
    return " ".join(parts).strip() + ext


def _tv_name(title: str, year: str, season: str, episode: str, ext: str) -> str:
    year_bit = f" ({year})" if year else ""
    return f"{title}{year_bit} - S{season}E{episode}{ext}"


def _anime_name(title: str, year: str, season: str, episode: str, ext: str) -> str:
    year_bit = f" ({year})" if year else ""
    if season and episode:
        return f"{title}{year_bit} - S{season}E{episode}{ext}"
    if episode:
        return f"{title}{year_bit} - E{episode}{ext}"
    return f"{title}{year_bit}{ext}"
