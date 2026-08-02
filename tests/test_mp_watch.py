# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mp_watch.config import load_config
from mp_watch.feed import FeedItem, parse_json_feed, parse_rss_xml
from mp_watch.normalize import is_wechat_article_url, normalize_wechat_url, pick_article_url
from mp_watch.runner import collect_new_items, run_watch
from mp_watch.state import load_state, save_state, upsert_item


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Demo</title>
    <item>
      <title>第一篇</title>
      <link>https://mp.weixin.qq.com/s/AbCdEfGhIjKlMnOp</link>
      <pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>第二篇</title>
      <description>正文里夹链接 https://mp.weixin.qq.com/s/XyZ1234567890abc 结尾</description>
      <pubDate>2026-06-02T08:00:00+08:00</pubDate>
    </item>
  </channel>
</rss>
"""


class NormalizeTest(unittest.TestCase):
    def test_short_link(self):
        u = "https://mp.weixin.qq.com/s/AbCdEfGhIjKlMnOp?scene=0#rd"
        self.assertEqual(normalize_wechat_url(u), "https://mp.weixin.qq.com/s/AbCdEfGhIjKlMnOp")

    def test_biz_query_link(self):
        u = "https://mp.weixin.qq.com/s?__biz=MzA1&mid=2247&idx=1&sn=deadbeef&chksm=xxx&scene=1"
        out = normalize_wechat_url(u)
        self.assertIn("__biz=MzA1", out)
        self.assertIn("mid=2247", out)
        self.assertIn("sn=deadbeef", out)
        self.assertNotIn("chksm", out)

    def test_pick_from_text(self):
        text = "请看 https://mp.weixin.qq.com/s/HelloWorld_12 原文"
        self.assertTrue(is_wechat_article_url(pick_article_url(text)))


class FeedParseTest(unittest.TestCase):
    def test_parse_rss(self):
        items = parse_rss_xml(SAMPLE_RSS, "演示号")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "第一篇")
        self.assertEqual(items[0].url, "https://mp.weixin.qq.com/s/AbCdEfGhIjKlMnOp")
        self.assertEqual(items[1].url, "https://mp.weixin.qq.com/s/XyZ1234567890abc")
        self.assertEqual(items[0].published, "2026-06-01")

    def test_parse_json(self):
        payload = json.dumps(
            {
                "items": [
                    {
                        "title": "JSON文",
                        "url": "https://mp.weixin.qq.com/s/JsonArticle001",
                        "published": "2026-07-01",
                    }
                ]
            },
            ensure_ascii=False,
        )
        items = parse_json_feed(payload, "JSON源")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://mp.weixin.qq.com/s/JsonArticle001")


class RunnerTest(unittest.TestCase):
    def test_collect_and_archive_with_mocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_path = root / "cfg.json"
            state_path = root / "state.json"
            log_dir = root / "logs"
            cfg = {
                "poll_hours": 2,
                "archive_type": "raw",
                "headless": True,
                "max_new_per_run": 10,
                "retry_failed": True,
                "max_fail_count": 5,
                "request_timeout": 5,
                "archive_interval": 0,
                "state_path": str(state_path),
                "log_dir": str(log_dir),
                "sources": [
                    {
                        "name": "测试号",
                        "kind": "rss",
                        "enabled": True,
                        "feed_url": "http://example.invalid/feed.xml",
                        "archive_type": "raw",
                    }
                ],
            }
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

            feed_items = [
                FeedItem(
                    title="新文",
                    url="https://mp.weixin.qq.com/s/NewArticleKey01",
                    published="2026-08-01",
                    source_name="测试号",
                    raw={},
                )
            ]

            def fake_fetch(**kwargs):
                return feed_items

            def fake_archive(urls, archive_type, headless=True, interval=2.0, timeout=30, progress_callback=None):
                self.assertEqual(urls, ["https://mp.weixin.qq.com/s/NewArticleKey01"])
                self.assertEqual(archive_type, "raw")
                if progress_callback:
                    progress_callback("mock archive")
                return [
                    {
                        "ok": True,
                        "url": urls[0],
                        "title": "新文",
                        "path": str(root / "out.md"),
                        "message": "OK",
                    }
                ]

            summary = run_watch(
                config_path=cfg_path,
                dry_run=False,
                archive_fn=fake_archive,
                fetch_fn=fake_fetch,
            )
            self.assertEqual(summary["discovered"], 1)
            self.assertEqual(summary["archived"], 1)
            self.assertEqual(summary["failed"], 0)

            state = load_state(state_path)
            key = "https://mp.weixin.qq.com/s/NewArticleKey01"
            self.assertEqual(state["items"][key]["status"], "archived")

            # 第二轮应去重，不再归档
            summary2 = run_watch(
                config_path=cfg_path,
                dry_run=False,
                archive_fn=fake_archive,
                fetch_fn=fake_fetch,
            )
            self.assertEqual(summary2["discovered"], 0)
            self.assertEqual(summary2["archived"], 0)

    def test_retry_failed(self):
        state = {"version": 1, "items": {}, "last_run": {}}
        key = "https://mp.weixin.qq.com/s/FailRetryKey01"
        upsert_item(state, key, url=key, status="failed", fail_count=1, title="旧")
        cfg = {
            "retry_failed": True,
            "max_fail_count": 5,
            "max_new_per_run": 10,
            "request_timeout": 5,
            "archive_type": "raw",
            "sources": [
                {
                    "name": "号",
                    "kind": "rss",
                    "enabled": True,
                    "feed_url": "http://x",
                    "archive_type": "raw",
                }
            ],
        }

        def fake_fetch(**kwargs):
            return [
                FeedItem(
                    title="再试",
                    url=key,
                    published="",
                    source_name="号",
                    raw={},
                )
            ]

        items, errors = collect_new_items(cfg, state, fetch_fn=fake_fetch)
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 1)

    def test_disabled_sources_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg_path = root / "cfg.json"
            state_path = root / "state.json"
            cfg = {
                "poll_hours": 2,
                "archive_type": "raw",
                "headless": True,
                "max_new_per_run": 10,
                "retry_failed": True,
                "max_fail_count": 5,
                "request_timeout": 5,
                "archive_interval": 0,
                "state_path": str(state_path),
                "log_dir": str(root / "logs"),
                "sources": [
                    {
                        "name": "A",
                        "kind": "rss",
                        "enabled": False,
                        "feed_url": "http://127.0.0.1/a",
                    }
                ],
            }
            cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
            summary = run_watch(config_path=cfg_path, dry_run=True)
            self.assertFalse(summary["ok"])
            self.assertIn("没有启用的 sources", summary["message"])


class ConfigPathTest(unittest.TestCase):
    def test_repo_config_loads(self):
        # 仓库内默认配置应可加载（源默认 disabled）
        from mp_watch.paths import DEFAULT_CONFIG_PATH

        if not DEFAULT_CONFIG_PATH.exists():
            self.skipTest("默认配置不存在")
        cfg = load_config(DEFAULT_CONFIG_PATH)
        self.assertEqual(cfg["poll_hours"], 2)
        self.assertEqual(len(cfg["sources"]), 3)
        names = {s["name"] for s in cfg["sources"]}
        self.assertIn("数字生命卡兹克", names)
        self.assertTrue(str(cfg["state_path"]).replace("/", "\\").endswith("data\\mp_watch_state.json") or "mp_watch_state.json" in cfg["state_path"])
        # 确认状态路径在仓库树下（E 盘项目），不是用户 C:\\Users
        self.assertNotIn("C:\\Users", cfg["state_path"])
        self.assertNotIn("C:/Users", cfg["state_path"])

    def test_apply_target_dirs(self):
        from mp_watch.runner import apply_target_dirs
        import wechat_core

        old = wechat_core.TARGET_DIRS.get("raw")
        try:
            apply_target_dirs({"raw": r"D:\tmp\mp_watch_raw_test"})
            self.assertEqual(wechat_core.TARGET_DIRS["raw"], r"D:\tmp\mp_watch_raw_test")
        finally:
            if old is not None:
                wechat_core.TARGET_DIRS["raw"] = old


if __name__ == "__main__":
    unittest.main()
