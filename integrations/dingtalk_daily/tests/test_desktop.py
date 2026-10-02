"""No live desktop access: evidence parsing and bounded UIA-reader simulations."""

from datetime import date, datetime, timedelta, timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dingtalk_daily.desktop import DesktopError, DingTalkDesktop, merge_ordered_pages, parse_ui_time


ZONE = timezone(timedelta(hours=8))
CUTOFF = datetime(2026, 10, 2, 22, 0, tzinfo=ZONE)


def message(identifier, clock="今天 12:30", text="工作内容", **extra):
    return {"_rid": identifier, "_time": clock, "_separator": False, "sender": "本人", "is_self": True, "text": text, "kind": "text", **extra}


def conversation(title, kind="direct", activity="今天 09:10"):
    return {"_rid": title, "title": title, "kind": kind, "activity": activity}


class TimeEvidenceTests(unittest.TestCase):
    def test_bare_clock_needs_date_evidence(self):
        self.assertIsNone(parse_ui_time("09:12", CUTOFF).timestamp)
        self.assertEqual(parse_ui_time("09:12", CUTOFF, date(2026, 10, 1)).timestamp.date(), date(2026, 10, 1))
        self.assertEqual(parse_ui_time("09:12", CUTOFF, allow_today_clock=True).timestamp.date(), CUTOFF.date())

    def test_explicit_dates_and_relatives(self):
        for label in ("今天 09:12", "2026年10月2日 09:12", "2026-10-02 星期五 09:12", "Today 09:12"):
            with self.subTest(label=label):
                result = parse_ui_time(label, CUTOFF)
                self.assertEqual(result.timestamp, CUTOFF.replace(hour=9, minute=12))
                self.assertTrue(result.explicit_date)
        self.assertEqual(parse_ui_time("昨天", CUTOFF).day, date(2026, 10, 1))
        self.assertIsNone(parse_ui_time("今天", CUTOFF).timestamp)

    def test_period_markers_and_ambiguous_noon(self):
        self.assertEqual(parse_ui_time("今天 上午12:05", CUTOFF).timestamp.hour, 0)
        self.assertEqual(parse_ui_time("今天 下午1:05", CUTOFF).timestamp.hour, 13)
        self.assertEqual(parse_ui_time("今天 中午1:05", CUTOFF).timestamp.hour, 13)
        self.assertEqual(parse_ui_time("今天 12:05 PM", CUTOFF).timestamp.hour, 12)
        self.assertIsNone(parse_ui_time("今天 中午3:05", CUTOFF).timestamp)

    def test_invalid_noise_and_yearless_dates_rejected(self):
        for label in ("昨天讨论了09:12的安排", "2026-02-30 09:12", "10-02 09:12", "周五", "今天 25:30", "今天 12:99"):
            with self.subTest(label=label):
                self.assertIsNone(parse_ui_time(label, CUTOFF).timestamp)

    def test_iso_timezones_and_naive_cutoff(self):
        self.assertEqual(parse_ui_time("2026-10-02T01:00:00Z", CUTOFF).timestamp.hour, 9)
        with self.assertRaises(ValueError):
            parse_ui_time("今天 09:12", CUTOFF.replace(tzinfo=None))


class MergeTests(unittest.TestCase):
    def test_ordered_overlap_preserves_identical_message_instances(self):
        a, b, c = (message(identifier) for identifier in ("a", "b", "c"))
        merged, issue = merge_ordered_pages([b, c], [a, b], prepend=True, key=DingTalkDesktop._page_key)
        self.assertIsNone(issue)
        self.assertEqual([item["_rid"] for item in merged], ["a", "b", "c"])

    def test_forward_overlap(self):
        merged, issue = merge_ordered_pages([{"id": 1}, {"id": 2}], [{"id": 2}, {"id": 3}], prepend=False, key=lambda item: item["id"])
        self.assertEqual([item["id"] for item in merged], [1, 2, 3])
        self.assertIsNone(issue)

    def test_ambiguous_overlap_keeps_possible_copies(self):
        merged, issue = merge_ordered_pages([{"text": "一样"}] * 2, [{"text": "一样"}] * 2, prepend=True, key=lambda item: item["text"])
        self.assertEqual(len(merged), 4)
        self.assertIn("无法唯一对齐", issue)

    def test_gap_is_partial(self):
        merged, issue = merge_ordered_pages([{"id": 1}], [{"id": 3}], prepend=False, key=lambda item: item["id"])
        self.assertEqual(len(merged), 2)
        self.assertIn("没有可验证的重叠", issue)

    def test_missing_runtime_id_never_merges_identical_bodies(self):
        first = message("", text="A")
        repeated = message("", text="B")
        last = message("", text="C")
        merged, issue = merge_ordered_pages([first, repeated], [repeated.copy(), last], prepend=False, key=DingTalkDesktop._page_key)
        self.assertEqual([item["text"] for item in merged], ["A", "B", "B", "C"])
        self.assertIn("缺少 UIA RuntimeId", issue)


class ScanHarness(DingTalkDesktop):
    def __init__(self, pages, positions=None):
        super().__init__({"ui": {"max_pages": 20}})
        self.pages = pages
        self.positions = positions or [100 * index / max(1, len(pages) - 1) for index in range(len(pages))]
        self.index = 0
        self._cutoff = CUTOFF

    def _assert_control(self, _):
        pass

    def _move_scroll(self, _, *, edge=None, direction=0):
        self.index = (len(self.pages) - 1 if edge == 100 else 0) if edge is not None else min(len(self.pages) - 1, max(0, self.index + direction))

    def _scroll_state(self, _):
        return len(self.pages) > 1, self.positions[self.index]

    def read(self, _):
        return self.pages[self.index]


class PagingTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("dingtalk_daily.desktop.time.sleep", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_conversations_scan_past_old_pinned_rows_to_real_bottom(self):
        old = conversation("置顶旧会话", activity="昨天 12:00")
        first, last = conversation("单聊一"), conversation("免打扰单聊")
        reader = ScanHarness([[old, first], [first, last]])
        rows, complete, issues = reader._scan(None, reader.read)
        self.assertTrue(complete, issues)
        self.assertEqual([row["title"] for row in rows], ["置顶旧会话", "单聊一", "免打扰单聊"])

    def test_message_scan_prepends_until_explicit_prior_day(self):
        old, first, last = message("old", "昨天 20:00"), message("first"), message("last", "今天 13:00")
        reader = ScanHarness([[old, first], [first, last]])
        rows, complete, issues = reader._scan(None, reader.read, upwards=True, stop_on_older=True)
        self.assertTrue(complete, issues)
        self.assertEqual([row["_rid"] for row in rows], ["old", "first", "last"])

    def test_runtime_id_recycling_is_partial(self):
        first = message("recycled", text="第一条")
        last = message("recycled", text="另一条")
        reader = ScanHarness([[first], [last]])
        _, complete, issues = reader._scan(None, reader.read)
        self.assertFalse(complete)
        self.assertTrue(any("虚拟化复用" in item for item in issues))

    def test_identical_virtualized_viewports_never_claim_complete(self):
        row = message("recycled")
        reader = ScanHarness([[row], [row]])
        _, complete, issues = reader._scan(None, reader.read)
        self.assertFalse(complete)
        self.assertTrue(any("控件及内容完全相同" in item for item in issues))

    def test_missing_runtime_id_keeps_equal_pages_when_scroll_advances(self):
        row = message("")
        reader = ScanHarness([[row], [row.copy()]])
        rows, complete, issues = reader._scan(None, reader.read)
        self.assertEqual(len(rows), 2)
        self.assertFalse(complete)
        self.assertTrue(any("RuntimeId" in item for item in issues))

    def test_no_scroll_progress_and_page_limit_are_partial(self):
        reader = ScanHarness([[message("one")], [message("two")]], positions=[0, 50])
        _, complete, issues = reader._scan(None, reader.read)
        self.assertFalse(complete)
        self.assertTrue(any("连续滚动无进展" in item for item in issues))
        reader = ScanHarness([[message("one")], [message("two")]])
        reader._page_limit = 1
        _, complete, issues = reader._scan(None, reader.read)
        self.assertFalse(complete)
        self.assertTrue(any("翻页次数达到上限" in item for item in issues))


class MessageScopeTests(unittest.TestCase):
    def setUp(self):
        self.reader = DingTalkDesktop({"self_names": ["本人"]})

    def test_excludes_old_unknown_and_after_cutoff_bodies(self):
        entries = [message("old", "昨天 09:00", "旧消息秘密"), message("today", "今天 21:59", "今日正文"), message("late", "今天 22:01", "截止后秘密"), message("unknown", "无法判断", "未知日期秘密")]
        messages, issues = self.reader._resolve_messages(entries, "联系人", CUTOFF)
        self.assertEqual([item["text"] for item in messages], ["今日正文"])
        serialized = json.dumps({"messages": messages, "issues": issues}, ensure_ascii=False)
        for secret in ("旧消息秘密", "截止后秘密", "未知日期秘密"):
            self.assertNotIn(secret, serialized)

    def test_cutoff_uses_display_precision_interval(self):
        entries = [message("before", "今天 21:59:59"), message("minute", "今天 22:00"), message("second", "今天 22:00:00")]
        messages, issues = self.reader._resolve_messages(entries, "联系人", CUTOFF)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["timestamp"], (CUTOFF - timedelta(seconds=1)).isoformat())
        self.assertTrue(any("时间精度不足" in issue for issue in issues))
        uncertain, issues = self.reader._resolve_messages([message("fraction", "今天 22:00:00")], "联系人", CUTOFF.replace(microsecond=200000))
        self.assertFalse(uncertain)
        self.assertTrue(any("时间精度不足" in issue for issue in issues))

    def test_clock_rollback_does_not_silently_inherit_yesterday(self):
        entries = [message("yesterday", "昨天 23:59"), message("today", "09:00", "不能判明日期的消息"), message("later", "09:30")]
        messages, issues = self.reader._resolve_messages(entries, "联系人", CUTOFF)
        self.assertFalse(messages)
        self.assertTrue(any("完整时间倒退" in issue for issue in issues))
        self.assertTrue(any("无法确认日期或时间" in issue for issue in issues))

    def test_date_separator_context_and_repeated_text_instances(self):
        entries = [{"_separator": True, "_time": "今天"}, message("one", "10:00"), message("two", "10:00")]
        messages, issues = self.reader._resolve_messages(entries, "联系人", CUTOFF)
        self.assertFalse(issues)
        self.assertEqual(len(messages), 2)
        self.assertNotEqual(messages[0]["id"], messages[1]["id"])

    def test_missing_sender_and_unknown_type_are_partial(self):
        _, issues = self.reader._resolve_messages([message("one", sender="", is_self=None, kind="unknown")], "联系人", CUTOFF)
        self.assertTrue(any("归属无法确认" in issue for issue in issues))
        self.assertTrue(any("消息类型无法确认" in issue for issue in issues))


class CollectionHarness(DingTalkDesktop):
    def __init__(self, initial, final=None):
        super().__init__({"priority_contact": "指定联系人", "self_group": "指定群", "self_names": ["本人"], "calibration_ok": True, "ui": {"activity_time_only_is_today": True}})
        self.initial, self.final = initial, final if final is not None else initial
        self.discovery_calls = 0
        self.opened = []

    def doctor(self):
        return {"ready": True}

    def _one(self, _, role):
        return role

    def _open_conversation(self, title):
        self.opened.append(title)

    def _scan(self, _, reader, **kwargs):
        if reader.__name__ == "_conversation_page":
            self.discovery_calls += 1
            return self.initial if self.discovery_calls == 1 else self.final, True, []
        return [message("one")], True, []


class CollectionTests(unittest.TestCase):
    def test_only_targets_and_today_directs_open_even_when_activity_is_after_cutoff(self):
        rows = [conversation("指定联系人"), conversation("指定群", "group"), conversation("当天单聊", activity="22:05"), conversation("其他群", "group"), conversation("旧单聊", activity="昨天 12:00")]
        reader = CollectionHarness(rows)
        capture = reader.collect(CUTOFF)
        self.assertEqual(reader.opened, ["指定联系人", "指定群", "当天单聊"])
        self.assertTrue(capture["discovery_complete"])
        self.assertEqual(reader.discovery_calls, 2)

    def test_unknown_kind_and_ambiguous_titles_are_not_opened(self):
        rows = [conversation("指定联系人"), conversation("指定群", "group"), conversation("未分类", "unknown"), conversation("同名"), conversation("同名")]
        reader = CollectionHarness(rows)
        capture = reader.collect(CUTOFF)
        self.assertEqual(reader.opened, ["指定联系人", "指定群"])
        self.assertFalse(capture["discovery_complete"])

    def test_unknown_kind_never_promotes_named_target_to_direct_or_group(self):
        reader = CollectionHarness([conversation("指定联系人", "unknown"), conversation("指定群", "unknown")])
        capture = reader.collect(CUTOFF)
        self.assertEqual(reader.opened, [])
        self.assertFalse(capture["discovery_complete"])
        self.assertEqual(len(capture["conversations"]), 2)
        self.assertTrue(all(not item["complete"] for item in capture["conversations"]))

    def test_final_discovery_change_is_partial(self):
        initial = [conversation("指定联系人"), conversation("指定群", "group")]
        reader = CollectionHarness(initial, final=initial + [conversation("新出现的单聊")])
        result = reader.collect(CUTOFF)
        self.assertFalse(result["discovery_complete"])
        self.assertTrue(any("结束复查" in issue for issue in result["issues"]))

    def test_archive_scope_limit_is_never_complete(self):
        reader = CollectionHarness([conversation("指定联系人"), conversation("指定群", "group")])
        reader.ui["scope_limitations"] = ["归档范围不可见"]
        self.assertFalse(reader.collect(CUTOFF)["discovery_complete"])

    def test_today_activity_before_cutoff_requires_today_message_evidence(self):
        reader = CollectionHarness([conversation("指定联系人"), conversation("指定群", "group"), conversation("仅截止后有活动", activity="22:05")])
        original_scan = reader._scan
        reader._scan = lambda container, read, **kwargs: original_scan(container, read, **kwargs) if read.__name__ == "_conversation_page" else ([message("old", "昨天 21:00")], True, [])
        capture = reader.collect(CUTOFF)
        before = [item for item in capture["conversations"] if item["title"] in {"指定联系人", "指定群"}]
        self.assertTrue(all(not item["complete"] for item in before))
        self.assertTrue(all(any("不能判定今天零条" in issue for issue in item["issues"]) for item in before))
        after = next(item for item in capture["conversations"] if item["title"] == "仅截止后有活动")
        self.assertTrue(after["complete"])
        self.assertEqual(after["messages"], [])


class GuardTests(unittest.TestCase):
    def test_doctor_requires_disjoint_direct_and_group_evidence_before_ui_access(self):
        for direct, group in ((["单聊"], []), ([], ["群聊"]), (["聊天"], ["聊天"])):
            with self.subTest(direct=direct, group=group):
                ui = {key: {"control_type": "Pane"} for key in DingTalkDesktop._REQUIRED}
                ui.update(message_time={"control_type": "Text"}, conversation_kind={"control_type": "Text"},
                          conversation_list_scope_confirmed=True, message_order="oldest_first",
                          direct_labels=direct, group_labels=group)
                reader = DingTalkDesktop({"ui": ui})
                reader._connect = lambda: self.fail("Invalid type profile must not touch the desktop")
                with self.assertRaisesRegex(DesktopError, "类型标记"):
                    reader.doctor()

    def test_selector_rejects_indexes_and_unbounded_regex(self):
        for selector in ({"index": 3}, {"control_type": "Text", "title_re": ".*"}, {"path": [{"self": True}]}):
            with self.subTest(selector=selector), self.assertRaises(DesktopError):
                DingTalkDesktop._check_selector(selector)

    def test_scope_requires_actual_selected_state(self):
        reader = DingTalkDesktop({"ui": {"scope_expected": "全部", "scope_state": "selection"}})
        state = SimpleNamespace(CurrentIsSelected=False)
        reader._one = lambda *_: SimpleNamespace(is_visible=lambda: True, window_text=lambda: "全部", iface_selection_item=state)
        with self.assertRaises(DesktopError):
            reader._assert_scope()
        state.CurrentIsSelected = True
        reader._assert_scope()

    def test_switching_chat_during_message_page_discards_page(self):
        reader = DingTalkDesktop({})
        reader._expected_chat = "目标联系人"
        titles = iter(["目标联系人", "另一个联系人"])
        reader._assert_window = lambda: None
        reader._one = lambda *_: SimpleNamespace(window_text=lambda: next(titles))
        reader._visible_rows = lambda *_: []
        with self.assertRaisesRegex(DesktopError, "当前聊天发生变化"):
            reader._message_page(None)

    def test_non_windows_fails_without_importing_or_touching_uia(self):
        with patch("dingtalk_daily.desktop.sys.platform", "linux"), self.assertRaisesRegex(DesktopError, "仅支持 Windows"):
            DingTalkDesktop({}).inspect()


if __name__ == "__main__":
    unittest.main()
