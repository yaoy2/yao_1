# -*- coding: utf-8 -*-
"""一轮监控：拉发现源 → 去重 → 调用 wechat_core 归档。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from .config import enabled_sources, load_config
from .feed import FeedItem, fetch_feed
from .logging_util import log_line
from .normalize import normalize_wechat_url
from .paths import DEFAULT_CONFIG_PATH, REPO_ROOT
from .state import get_item, load_state, save_state, upsert_item, utc_now_iso

ArchiveFn = Callable[..., List[Dict[str, object]]]


def _ensure_repo_on_syspath() -> None:
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def apply_target_dirs(target_dirs: Dict[str, str]) -> None:
    """按本机配置覆盖 wechat_core 归档根目录（D/L 路径可不同）。"""
    if not target_dirs:
        return
    _ensure_repo_on_syspath()
    import wechat_core  # noqa: WPS433

    for key, path in target_dirs.items():
        if key and path:
            wechat_core.TARGET_DIRS[str(key)] = str(path)


def default_archive_fn() -> ArchiveFn:
    _ensure_repo_on_syspath()
    from wechat_core import archive_urls  # noqa: WPS433

    return archive_urls


def collect_new_items(
    cfg: Dict[str, Any],
    state: Dict[str, Any],
    fetch_fn=fetch_feed,
) -> tuple[List[FeedItem], List[str]]:
    """返回待归档条目与采集错误信息。"""
    errors: List[str] = []
    discovered: List[FeedItem] = []
    seen_keys = set()
    retry_failed = bool(cfg.get("retry_failed", True))
    max_fail = int(cfg.get("max_fail_count", 5))
    timeout = int(cfg.get("request_timeout", 30))

    for src in enabled_sources(cfg):
        name = src["name"]
        try:
            items = fetch_fn(
                feed_url=src["feed_url"],
                source_name=name,
                kind=src.get("kind", "rss"),
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001 — 单源失败不影响其他源
            errors.append(f"源「{name}」拉取失败：{type(exc).__name__}: {exc}")
            continue

        for item in items:
            key = normalize_wechat_url(item.url)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            item.url = key

            existing = get_item(state, key)
            if existing is None:
                upsert_item(
                    state,
                    key,
                    url=key,
                    title=item.title,
                    source_name=name,
                    status="seen",
                )
                discovered.append(item)
                continue

            status = existing.get("status")
            fail_count = int(existing.get("fail_count") or 0)
            if status == "archived":
                continue
            if status == "failed" and retry_failed and fail_count < max_fail:
                upsert_item(state, key, title=item.title or existing.get("title"), source_name=name)
                discovered.append(item)
                continue
            if status in {"seen", "pending"}:
                discovered.append(item)

    max_new = int(cfg.get("max_new_per_run", 10))
    if max_new > 0 and len(discovered) > max_new:
        discovered = discovered[:max_new]
    return discovered, errors


def archive_items(
    items: Sequence[FeedItem],
    cfg: Dict[str, Any],
    state: Dict[str, Any],
    archive_fn: ArchiveFn,
    progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, int]:
    counts = {"archived": 0, "failed": 0, "skipped": 0}
    if not items:
        return counts

    # 按源的 archive_type 分组；第一版同一 run 用全局 archive_type，源级可覆盖
    by_type: Dict[str, List[FeedItem]] = {}
    source_type = {s["name"]: s.get("archive_type") or cfg["archive_type"] for s in cfg.get("sources", [])}
    for item in items:
        atype = source_type.get(item.source_name) or cfg.get("archive_type") or "raw"
        by_type.setdefault(str(atype), []).append(item)

    headless = bool(cfg.get("headless", True))
    interval = float(cfg.get("archive_interval", 2.0))
    timeout = int(cfg.get("request_timeout", 30))

    for archive_type, group in by_type.items():
        urls = [it.url for it in group]
        title_map = {it.url: it for it in group}
        if progress:
            progress(f"开始归档 {len(urls)} 篇（类型={archive_type}）")
        results = archive_fn(
            urls,
            archive_type=archive_type,
            headless=headless,
            interval=interval,
            timeout=timeout,
            progress_callback=progress,
        )
        for result in results:
            url = normalize_wechat_url(str(result.get("url") or ""))
            item = title_map.get(url)
            title = (item.title if item else "") or str(result.get("title") or "")
            if result.get("ok"):
                upsert_item(
                    state,
                    url,
                    url=url,
                    title=title,
                    status="archived",
                    path=str(result.get("path") or ""),
                    last_error="",
                    archived_at=utc_now_iso(),
                )
                counts["archived"] += 1
            else:
                existing = get_item(state, url) or {}
                fail_count = int(existing.get("fail_count") or 0) + 1
                upsert_item(
                    state,
                    url,
                    url=url,
                    title=title,
                    status="failed",
                    fail_count=fail_count,
                    last_error=str(result.get("message") or "unknown error"),
                )
                counts["failed"] += 1
    return counts


def run_watch(
    config_path: Optional[Path] = None,
    *,
    dry_run: bool = False,
    archive_fn: Optional[ArchiveFn] = None,
    fetch_fn=fetch_feed,
    progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """执行一轮监控。返回摘要字典。"""
    cfg = load_config(config_path or DEFAULT_CONFIG_PATH)
    state_path = Path(cfg["state_path"])
    log_dir = Path(cfg["log_dir"])
    state = load_state(state_path)

    def _p(msg: str) -> None:
        log_line(log_dir, msg)
        if progress:
            progress(msg)

    sources = enabled_sources(cfg)
    if not sources:
        summary = {
            "ok": False,
            "message": "没有启用的 sources。请编辑 config/mp_watch_sources.json，填写 feed_url 并设 enabled=true。",
            "discovered": 0,
            "archived": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
        }
        _p(summary["message"])
        state["last_run"] = {
            "at": utc_now_iso(),
            "discovered": 0,
            "archived": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [summary["message"]],
        }
        save_state(state_path, state)
        return summary

    _p(f"mp_watch 开始 | 源={len(sources)} | dry_run={dry_run} | config={cfg.get('_config_path')}")
    discovered, errors = collect_new_items(cfg, state, fetch_fn=fetch_fn)
    _p(f"发现待处理 {len(discovered)} 篇；采集错误 {len(errors)} 条")
    for err in errors:
        _p(err)

    counts = {"archived": 0, "failed": 0, "skipped": 0}
    if dry_run:
        for item in discovered:
            upsert_item(
                state,
                item.url,
                url=item.url,
                title=item.title,
                source_name=item.source_name,
                status="seen",
            )
            _p(f"[dry-run] 将归档：{item.source_name} | {item.title} | {item.url}")
        counts["skipped"] = len(discovered)
    elif discovered:
        apply_target_dirs(cfg.get("target_dirs") or {})
        fn = archive_fn or default_archive_fn()
        counts = archive_items(discovered, cfg, state, archive_fn=fn, progress=_p)
    else:
        _p("无新文章需要归档")

    summary = {
        "ok": len(errors) == 0 or counts["archived"] > 0,
        "message": "完成",
        "discovered": len(discovered),
        "archived": counts["archived"],
        "failed": counts["failed"],
        "skipped": counts["skipped"],
        "errors": errors,
        "state_path": str(state_path),
        "log_dir": str(log_dir),
    }
    state["last_run"] = {
        "at": utc_now_iso(),
        "discovered": summary["discovered"],
        "archived": summary["archived"],
        "failed": summary["failed"],
        "skipped": summary["skipped"],
        "errors": errors,
    }
    save_state(state_path, state)
    _p(
        "mp_watch 结束 | "
        f"discovered={summary['discovered']} archived={summary['archived']} "
        f"failed={summary['failed']} skipped={summary['skipped']}"
    )
    return summary
