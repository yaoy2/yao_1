"""Deterministic recall of verified video records when embeddings are unavailable."""
import re


def video_url(record):
    bvid = str(record.get("bvid", ""))
    return f"https://www.bilibili.com/video/{bvid}" if re.fullmatch(r"BV[A-Za-z0-9]{10}", bvid) else ""


def format_watch_item(item):
    score = "评价未生成" if item.get("evaluation_status") == "failed" else f"{item.get('score', '?')}分"
    line = (f"  [{item.get('time', '?').split(' ', 1)[-1]}] 「{str(item.get('title', '?'))[:160]}」"
            f"{score} {item.get('mood', '?')} {str(item.get('review', ''))[:160]}")
    link = video_url(item)
    return line + (f"\n    {link}" if link else "")


def search_records(cache, watch_log, keyword, limit=5):
    """Search public watched content only; never search account/chat records."""
    if not isinstance(cache, dict):
        return []
    watch_by_id = {item.get("bvid"): item for item in watch_log if isinstance(item, dict)}
    terms = str(keyword).casefold().split()
    matches = []
    for bvid, value in cache.items():
        if not isinstance(value, dict) or value.get("content_analyzed") is not True:
            continue
        item = {**watch_by_id.get(bvid, {}), **value, "bvid": bvid}
        if not video_url(item):
            continue
        text = " ".join(str(item.get(key, "")) for key in
                        ("bvid", "title", "owner_name", "up_name", "analysis", "summary", "review"))
        if not all(term in text.casefold() for term in terms):
            continue
        matches.append(item)
    matches.sort(key=lambda item: str(item.get("time", "")), reverse=True)
    return [format_watch_item(item) +
            f"\n    内容依据：{item.get('analysis_basis', '已分析内容')}；"
            f"摘要：{str(item.get('analysis') or item.get('summary') or '')[:650]}"
            for item in matches[:max(0, min(limit, 10))]]


def search_watched_videos(plugin, keyword, limit=5):
    # Imported only in the installed plugin so pure formatting stays testable.
    from .config import VIDEO_MEMORY_FILE, WATCH_LOG_FILE
    return search_records(plugin._load_json(VIDEO_MEMORY_FILE, {}),
                          plugin._load_json(WATCH_LOG_FILE, []), keyword, limit)
