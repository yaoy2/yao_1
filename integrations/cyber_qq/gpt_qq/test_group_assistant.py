import copy
from datetime import datetime
from pathlib import Path
import tempfile
import threading
import unittest

from integrations.cyber_qq.gpt_qq.configure_assistant import group_profile
from integrations.cyber_qq.gpt_qq.group_assistant.engine import (
    ENABLE_COMMANDS, PLUGIN_NAME, TZ, GroupStore, Window, command_text,
    message_text, query_window,
)
from integrations.cyber_qq.gpt_qq.prepare import initial_config


class GroupStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(suffix="-可删")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "records.sqlite3"
        self.store = GroupStore(self.path)
        self.window = Window(0, 2000, "test")

    def record(self, group="10000001", mid="1", stamp=101, **kwargs):
        return self.store.record(group, mid, stamp, "12345678", "成员", "讨论内容", **kwargs)

    def test_opt_in_stop_resume_and_persistence(self):
        self.assertFalse(self.record())
        self.assertTrue(self.store.set_enabled("10000001", True, 100))
        self.assertFalse(self.store.set_enabled("10000001", True, 101))
        self.assertTrue(self.record())
        self.assertFalse(self.record(mid="old", stamp=99))
        self.store.set_enabled("10000001", False, 105)
        self.assertFalse(self.record(mid="stopped", stamp=106))
        self.store.set_enabled("10000001", True, 110)
        self.assertFalse(self.record(mid="delayed", stamp=109))
        self.assertTrue(self.record(mid="2", stamp=110))
        snapshot = GroupStore(self.path).snapshot("10000001", self.window)
        self.assertEqual(snapshot["included_count"], 2)
        self.assertEqual(snapshot["recording_periods"], [
            {"started_at": 100, "stopped_at": 105}, {"started_at": 110, "stopped_at": None}])

    def test_group_isolation_duplicate_and_request_exclusion(self):
        for group in ("10000001", "10000002"):
            self.store.set_enabled(group, True, 100)
            self.assertTrue(self.record(group=group))
        self.assertFalse(self.record())
        self.assertTrue(self.record(mid="request", is_request=True))
        snapshot = self.store.snapshot("10000001", self.window)
        self.assertEqual(snapshot["matching_count"], 1)
        self.assertEqual([x["source_id"] for x in snapshot["messages"]], ["#1"])
        self.assertEqual(self.store.snapshot("10000003", self.window)["included_count"], 0)

    def test_latest_bounded_inputs_in_chronological_order(self):
        self.store.set_enabled("10000001", True, 100)
        for number in range(1, 5):
            self.record(mid=str(number), stamp=100 + number)
        snapshot = self.store.snapshot("10000001", Window(0, 2000, "test", 2))
        self.assertTrue(snapshot["partial"])
        self.assertEqual(snapshot["matching_count"], 4)
        self.assertEqual([x["source_id"] for x in snapshot["messages"]], ["#3", "#4"])

    def test_long_message_reports_truncation_without_losing_original(self):
        self.store.set_enabled("10000001", True, 100)
        self.store.record("10000001", "long", 101, "12345678", "成员", "长" * 10000)
        snapshot = self.store.snapshot("10000001", self.window, max_chars=1200)
        self.assertTrue(snapshot["partial"])
        self.assertLess(len(snapshot["messages"][0]["text"]), 1200)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT length(content) FROM messages").fetchone()[0], 10000)

    def test_analysis_sources_and_send_receipt_are_stored(self):
        self.store.set_enabled("10000001", True, 100)
        self.record()
        snapshot = self.store.snapshot("10000001", self.window)
        self.store.save_analysis("10000001", "10000001:req", "整理", snapshot, "结果")
        self.assertTrue(self.store.already_handled("10000001:req"))
        self.assertFalse(self.store.already_handled("10000002:req"))
        self.store.mark_sent("10000001:req")
        with self.store.connect() as db:
            row = db.execute("SELECT source_ids,sent FROM analyses").fetchone()
            self.assertEqual(tuple(row), ('["#1"]', 1))


class InputTests(unittest.TestCase):
    def test_exact_enable_command(self):
        for text in ("小G 开始记录", "小Ｇ，开始记录", "/乖小g: 开始记录"):
            query, addressed = command_text(text)
            self.assertTrue(addressed)
            self.assertIn(query, ENABLE_COMMANDS)
        self.assertNotIn(command_text("请解释“开始记录”")[0], ENABLE_COMMANDS)
        self.assertFalse(command_text("成员说小G 开始记录")[1])

    def test_media_markers_do_not_archive_urls(self):
        output = message_text([
            {"type": "text", "data": {"text": "请参考"}},
            {"type": "image", "data": {"url": "https://example.invalid/token-secret"}},
            {"type": "file", "data": {"name": "材料.pdf", "url": "private-url"}},
            {"type": "reply", "data": {"id": "42"}},
        ])
        self.assertIn("材料.pdf", output)
        self.assertIn("引用 #42", output)
        self.assertIn("正文未读取", output)
        self.assertNotIn("url", output)
        self.assertNotIn("token-secret", output)

    def test_taipei_dates_limits_and_invalid_ranges(self):
        now = datetime(2026, 11, 1, 1, 30, tzinfo=TZ)
        yesterday = query_window("整理昨天", now)
        self.assertEqual(datetime.fromtimestamp(yesterday.start, TZ).strftime("%F"), "2026-10-31")
        dates = query_window("2026-10-28 至 2026-10-30", now)
        self.assertEqual(dates.end - dates.start, 3 * 86400)
        self.assertEqual(query_window("最近99999条", now).limit, 600)
        with self.assertRaises(ValueError):
            query_window("最近91天", now)
        with self.assertRaises(ValueError):
            query_window("2026-11-02 至 2026-11-01", now)

    def test_group_profile_keeps_private_config_unchanged(self):
        base = initial_config("12345678", "test-key", "test-password", "test-bridge")
        original = copy.deepcopy(base)
        group = group_profile(base)
        self.assertEqual(base, original)
        self.assertFalse(group["provider_settings"]["enable"])
        self.assertEqual(group["plugin_set"], [PLUGIN_NAME])
        self.assertTrue(group["disable_builtin_commands"])
        self.assertFalse(group["platform_settings"]["enable_id_white_list"])
        self.assertEqual(base["platform_settings"]["id_whitelist"], ["gpt-qq:FriendMessage:12345678"])

    def test_chinese_dates_do_not_silently_fall_back_to_today(self):
        now = datetime(2026, 11, 1, 17, 0, tzinfo=TZ)
        for query, expected in (
            ("你看一下我10月24日发在群里的跟论文有关的内容", "2026-10-24"),
            ("10月24号的记录", "2026-10-24"),
            ("2025年10月24日的记录", "2025-10-24"),
            ("去年10月24日的记录", "2025-10-24"),
            ("前年的记录：前年10月24日", "2024-10-24"),
        ):
            with self.subTest(query=query):
                window = query_window(query, now)
                self.assertEqual(window.label, expected)
                self.assertEqual(window.end - window.start, 86400)
        self.assertEqual(query_window("2025年10月24日到10月26日", now).label,
                         "2025-10-24 至 2025-10-26")
        self.assertEqual(query_window("去年12月31日至今年1月2日", now).label,
                         "2025-12-31 至 2026-01-02")
        self.assertEqual(query_window("2026-10-24到10月26日", now).end
                         - query_window("2026-10-24到10月26日", now).start, 3 * 86400)
        with self.assertRaisesRegex(ValueError, "日期无效"):
            query_window("10月32日", now)

    def test_config_dictionary_with_runtime_lock(self):
        class RuntimeConfig(dict):
            pass
        base = RuntimeConfig(initial_config("12345678", "test-key", "test-password", "test-bridge"))
        base.lock = threading.Lock()
        self.assertEqual(group_profile(base)["plugin_set"], [PLUGIN_NAME])


if __name__ == "__main__":
    unittest.main()
