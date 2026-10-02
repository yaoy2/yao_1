import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import unittest


_PATH = Path(__file__).resolve().parents[1] / "dingtalk_daily" / "core.py"
_SPEC = importlib.util.spec_from_file_location("daily_report_core", _PATH)
core = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(core)


DAY = "2026-10-02"
RUN_AT = datetime.fromisoformat(f"{DAY}T22:00:00+08:00")
CONFIG = {"priority_contact": "重点同事", "self_group": "指定工作群", "self_names": ["本机用户"]}


def message(identifier="m1", *, stamp=f"{DAY}T09:00:00+08:00", sender="其他同事", own=False, text="已收到资料", kind="text", source="可见记录 1"):
    return {"id": identifier, "timestamp": stamp, "sender": sender, "is_self": own, "text": text, "kind": kind, "source": source}


def conversation(identifier, title, kind="direct", messages=None, complete=True, issues=None):
    return {"id": identifier, "title": title, "kind": kind, "complete": complete, "issues": issues or [], "messages": messages or []}


def capture(priority=None, group=None, others=None, **overrides):
    result = {
        "date": DAY, "cutoff": RUN_AT.isoformat(), "discovery_complete": True, "issues": [],
        "conversations": [conversation("priority", "重点同事", messages=priority), conversation("group", "指定工作群", "group", group)] + (others or []),
    }
    result.update(overrides)
    return result


def section(report, key):
    return next(item for item in report["sections"] if item["key"] == key)


def messages(report, key):
    return [item for row in section(report, key)["conversations"] for item in row["messages"]]


class DailyCoreTests(unittest.TestCase):
    def build(self, data=None, config=None, run_at=RUN_AT):
        return core.build_report(data if data is not None else capture(), config if config is not None else CONFIG, run_at)

    def test_three_scopes_and_no_out_of_scope_payload_is_returned(self):
        data = capture(
            [message("p1"), message("p2", sender="本机用户", own=True, text="我的回复")],
            [message("g1", text="其他群成员内容不得保存"), message("g2", sender="本机用户", own=True, text="群内本人发言")],
            [conversation("other", "普通同事", messages=[message("o1"), message("o2", sender="本机用户", own=True)]),
             conversation("old", "旧日联系人不得保存", messages=[message("old1", stamp="2026-10-01T23:59:59+08:00", text="旧日正文不得保存")]),
             conversation("foreign", "无关群不得保存", "group", [message("foreign1", text="无关群正文不得保存")], issues=["无关群诊断不得保存"])],
        )
        report, markdown = self.build(data)
        self.assertEqual("complete", report["status"])
        self.assertEqual(5, report["counts"]["messages"])
        self.assertEqual(["p1", "p2"], [item["id"] for item in messages(report, "priority_contact")])
        self.assertEqual(["g2"], [item["id"] for item in messages(report, "self_group")])
        self.assertEqual(["普通同事"], [row["title"] for row in section(report, "other_direct")["conversations"]])
        serialized = json.dumps(report, ensure_ascii=False) + markdown
        self.assertNotIn("不得保存", serialized)
        self.assertEqual(3, markdown.count("\n## "))

    def test_exact_date_and_cutoff_are_inclusive_in_shanghai_timezone(self):
        evidence = [
            message("before", stamp="2026-10-01T15:59:59+00:00"),
            message("start", stamp="2026-10-01T16:00:00+00:00"),
            message("last", stamp="2026-10-02T14:00:00+00:00"),
            message("later", stamp="2026-10-02T14:00:00.000001+00:00"),
            message("tomorrow", stamp="2026-10-03T00:00:00+08:00"),
        ]
        report, _ = self.build(capture(priority=evidence))
        self.assertEqual(["start", "last"], [item["id"] for item in messages(report, "priority_contact")])
        self.assertTrue(all(item["timestamp"].startswith(DAY) for item in messages(report, "priority_contact")))
        self.assertTrue(all(item["timestamp"].endswith("+08:00") for item in messages(report, "priority_contact")))

    def test_capture_cannot_advance_cutoff_beyond_fixed_run_start(self):
        report, _ = self.build(capture(priority=[message("start", stamp=RUN_AT.isoformat()), message("late", stamp=f"{DAY}T22:00:01+08:00")], cutoff=f"{DAY}T23:00:00+08:00"))
        self.assertEqual(RUN_AT.isoformat(), report["cutoff"])
        self.assertEqual(["start"], [item["id"] for item in messages(report, "priority_contact")])
        self.assertEqual("partial", report["status"])

    def test_prior_day_report_is_bounded_to_selected_calendar_day(self):
        data = capture(priority=[message("last", stamp=f"{DAY}T23:59:59.999999+08:00"), message("next", stamp="2026-10-03T00:00:00+08:00")], cutoff="2026-10-03T10:00:00+08:00")
        report, _ = self.build(data, run_at=datetime.fromisoformat("2026-10-03T10:00:00+08:00"))
        self.assertEqual(["last"], [item["id"] for item in messages(report, "priority_contact")])
        self.assertEqual(f"{DAY}T23:59:59.999999+08:00", report["cutoff"])

    def test_future_date_does_not_include_messages(self):
        report, _ = self.build(capture(priority=[message()], date="2026-10-03", cutoff="2026-10-03T22:00:00+08:00"))
        self.assertEqual("partial", report["status"])
        self.assertEqual(0, report["counts"]["messages"])
        self.assertIsNone(report["cutoff"])

    def test_ambiguous_or_invalid_message_times_are_excluded(self):
        invalid = [None, "", "09:00", f"{DAY}T09:00:00", "2026-02-30T09:00:00+08:00", "昨天 09:00", RUN_AT]
        evidence = [message(str(index), stamp=value, text="不可靠日期正文不得保存") for index, value in enumerate(invalid)]
        report, markdown = self.build(capture(priority=evidence + [message("valid")]))
        self.assertEqual("partial", report["status"])
        self.assertEqual(["valid"], [item["id"] for item in messages(report, "priority_contact")])
        self.assertNotIn("不可靠日期正文不得保存", json.dumps(report, ensure_ascii=False) + markdown)

    def test_invalid_capture_window_returns_partial_empty_report(self):
        for patch in ({"date": "20261002"}, {"date": "2026-02-30"}, {"date": None}, {"cutoff": "2026-10-02T22:00:00"}, {"cutoff": None}, {"cutoff": "2026-10-01T22:00:00+08:00"}):
            with self.subTest(patch=patch):
                report, markdown = self.build(capture(priority=[message()], **patch))
                self.assertEqual("partial", report["status"])
                self.assertEqual(0, report["counts"]["messages"])
                self.assertIn("未纳入消息", markdown)

    def test_group_identity_uses_exact_names_and_rejects_conflicts(self):
        evidence = [
            message("explicit", sender="本机用户", own=True),
            message("name", sender="本机用户", own=None),
            message("blank_self", sender="", own=True),
            message("peer", sender="其他同事", own=False),
            message("peer_name", sender="其他同事", own=None),
            message("substring", sender="本机用户的同事", own=None),
            message("true_conflict", sender="其他同事", own=True, text="身份冲突正文不得保存"),
            message("false_conflict", sender="本机用户", own=False, text="身份冲突正文不得保存"),
            message("unknown", sender="", own=None, text="身份未知正文不得保存"),
        ]
        report, markdown = self.build(capture(group=evidence))
        self.assertEqual(["explicit", "name", "blank_self"], [item["id"] for item in messages(report, "self_group")])
        self.assertEqual("partial", report["status"])
        self.assertIn("本人（界面标记）", markdown)
        self.assertNotIn("不得保存", json.dumps(report, ensure_ascii=False) + markdown)

    def test_group_with_no_self_names_requires_explicit_true_boolean(self):
        config = {**CONFIG, "self_names": []}
        evidence = [message("yes", sender="", own=True), message("unknown", sender="其他同事", own=None), message("truthy", sender="", own=1)]
        report, _ = self.build(capture(group=evidence), config=config)
        self.assertEqual(["yes"], [item["id"] for item in messages(report, "self_group")])
        self.assertEqual("partial", report["status"])

    def test_other_group_members_unknown_dates_do_not_affect_own_message_completeness(self):
        report, _ = self.build(capture(group=[message("peer", stamp=None, own=False)]))
        self.assertEqual("complete", report["status"])
        self.assertEqual("empty", section(report, "self_group")["status"])

    def test_direct_unknown_sender_is_retained_without_invented_identity(self):
        report, markdown = self.build(capture(priority=[message(sender="", own=None)]))
        self.assertEqual("", messages(report, "priority_contact")[0]["sender"])
        self.assertIn("发送人未识别", markdown)
        self.assertEqual("partial", report["status"])

    def test_direct_conflicting_identity_is_excluded_too(self):
        report, _ = self.build(capture(priority=[message(sender="其他同事", own=True)]))
        self.assertEqual([], messages(report, "priority_contact"))
        self.assertEqual("partial", report["status"])

    def test_same_id_deduplicates_but_same_text_and_time_different_ids_do_not(self):
        original = message("one")
        duplicate = {**original, "source": "第二次观察"}
        report, _ = self.build(capture(priority=[original, duplicate, message("two")]))
        self.assertEqual(["one", "two"], [item["id"] for item in messages(report, "priority_contact")])
        self.assertEqual("complete", report["status"])

    def test_duplicate_id_conflicts_are_excluded_not_arbitrarily_selected(self):
        report, markdown = self.build(capture(priority=[message("one", text="冲突版本一不得保存"), message("one", text="冲突版本二不得保存"), message("two")]))
        self.assertEqual(["two"], [item["id"] for item in messages(report, "priority_contact")])
        self.assertEqual("partial", report["status"])
        self.assertNotIn("不得保存", json.dumps(report, ensure_ascii=False) + markdown)

    def test_message_ids_are_only_unique_within_a_conversation(self):
        report, _ = self.build(capture(priority=[message("same")], others=[conversation("other", "普通同事", messages=[message("same")])]))
        self.assertEqual(2, report["counts"]["messages"])

    def test_missing_message_ids_never_use_text_time_heuristic_deduplication(self):
        report, _ = self.build(capture(priority=[message(""), message("")]))
        self.assertEqual(2, report["counts"]["messages"])
        self.assertEqual("partial", report["status"])

    def test_repeated_capture_of_same_conversation_merges_by_id(self):
        data = capture(priority=[message("one")], others=[conversation("priority", "重点同事", messages=[message("one"), message("two")])])
        report, _ = self.build(data)
        self.assertEqual(["one", "two"], [item["id"] for item in messages(report, "priority_contact")])
        self.assertEqual([], section(report, "other_direct")["conversations"])

    def test_same_title_with_different_conversation_ids_is_ambiguous(self):
        report, _ = self.build(capture(priority=[message()], others=[conversation("another", "重点同事", messages=[message("two")])]))
        self.assertEqual("partial", report["status"])
        self.assertEqual([], messages(report, "priority_contact"))
        self.assertEqual([], section(report, "other_direct")["conversations"])

    def test_conflicting_conversation_id_is_excluded(self):
        report, _ = self.build(capture(priority=[message()], others=[conversation("priority", "另一个名称", messages=[message("two")])]))
        self.assertEqual("partial", report["status"])
        self.assertEqual(0, report["counts"]["messages"])

    def test_complete_empty_is_distinct_from_missing_or_incomplete_target(self):
        report, markdown = self.build()
        self.assertEqual("complete", report["status"])
        self.assertEqual("empty", section(report, "priority_contact")["status"])
        self.assertIn("已核对，范围内无符合条件的消息", markdown)
        data = capture()
        data["conversations"] = [data["conversations"][1]]
        missing, missing_md = self.build(data)
        self.assertEqual("partial", section(missing, "priority_contact")["status"])
        self.assertIn("不能确认当天无消息", missing_md)
        data = capture()
        data["conversations"][0]["complete"] = False
        incomplete, _ = self.build(data)
        self.assertEqual("partial", section(incomplete, "priority_contact")["status"])

    def test_other_incomplete_unproven_today_chat_is_not_saved(self):
        data = capture(others=[conversation("other", "日期未确认联系人不得保存", messages=[message(stamp=None, text="日期未确认正文不得保存")], complete=False, issues=["日期未确认诊断不得保存"])])
        report, markdown = self.build(data)
        self.assertEqual("partial", section(report, "other_direct")["status"])
        self.assertEqual([], section(report, "other_direct")["conversations"])
        self.assertNotIn("不得保存", json.dumps(report, ensure_ascii=False) + markdown)

    def test_incomplete_discovery_never_claims_no_other_conversations(self):
        report, markdown = self.build(capture(discovery_complete=False))
        self.assertEqual("partial", report["status"])
        self.assertEqual("partial", section(report, "other_direct")["status"])
        self.assertIn("可能遗漏", markdown)

    def test_unknown_conversation_type_is_not_assumed_to_be_direct(self):
        report, markdown = self.build(capture(others=[conversation("unknown", "类型未明会话不得保存", "unknown", [message(text="类型未明正文不得保存")])]))
        self.assertEqual("partial", report["status"])
        self.assertEqual(0, report["counts"]["messages"])
        self.assertEqual("partial", section(report, "other_direct")["status"])
        self.assertNotIn("不得保存", json.dumps(report, ensure_ascii=False) + markdown)

    def test_attachment_and_image_visible_text_are_preserved_with_limits(self):
        report, markdown = self.build(capture(priority=[message("file", kind="attachment", text="资料文件.docx"), message("image", kind="image", text="")]))
        self.assertEqual(2, report["counts"]["messages"])
        self.assertEqual("partial", report["status"])
        self.assertIn("资料文件.docx", messages(report, "priority_contact")[0]["text"])
        self.assertIn("内容未完整解析", markdown)

    def test_follow_up_clues_quote_full_messages_without_inferring_completion(self):
        content = "材料已提交，请确认。\n第二行保留完整原文。" + "完整内容" * 100
        report, markdown = self.build(capture(priority=[message(text=content)]))
        clue = section(report, "priority_contact")["conversations"][0]["follow_up_clues"][0]
        self.assertEqual(content, clue["text"])
        self.assertEqual(1, clue["message_index"])
        self.assertNotIn("completed", clue)
        self.assertIn("不代表任务尚未完成", markdown)
        self.assertEqual(2, markdown.count("完整内容" * 100))

    def test_dynamic_markdown_and_html_are_never_report_structure_or_images(self):
        hostile = "### 假标题\n<script>alert(1)</script>\n![图](https://example.invalid/pixel)\n[链接](javascript:bad)"
        config = {**CONFIG, "priority_contact": "重点<script>同事"}
        data = capture()
        data["conversations"][0]["title"] = config["priority_contact"]
        data["conversations"][0]["messages"] = [message(text=hostile, source="<b>原始来源</b>")]
        report, markdown = self.build(data, config=config)
        self.assertEqual(hostile, messages(report, "priority_contact")[0]["text"])
        self.assertNotIn("<script>", markdown)
        self.assertNotIn("\n### 假标题", markdown)
        self.assertNotIn("![图]", markdown)
        self.assertIn("&lt;script&gt;", markdown)
        self.assertIn(r"> \#\#\# 假标题", markdown)

    def test_input_capture_is_not_mutated_and_output_ignores_extra_fields(self):
        data = capture(priority=[{**message(), "raw_previous_day": "额外原始内容不得保存"}])
        before = copy.deepcopy(data)
        report, markdown = self.build(data)
        self.assertEqual(before, data)
        self.assertNotIn("不得保存", json.dumps(report, ensure_ascii=False) + markdown)

    def test_messages_are_sorted_chronologically_without_merging_equal_times(self):
        report, _ = self.build(capture(priority=[message("late", stamp=f"{DAY}T10:00:00+08:00"), message("early"), message("equal")]))
        self.assertEqual(["early", "equal", "late"], [item["id"] for item in messages(report, "priority_contact")])

    def test_config_and_naive_run_start_are_rejected(self):
        invalid_configs = [{}, {**CONFIG, "self_names": "本机用户"}, {**CONFIG, "priority_contact": ""}, {**CONFIG, "self_names": [None]}]
        for config in invalid_configs:
            with self.subTest(config=config), self.assertRaises(ValueError):
                self.build(config=config)
        with self.assertRaises(ValueError):
            self.build(run_at=RUN_AT.replace(tzinfo=None))

    def test_run_start_in_other_timezone_is_normalized(self):
        report, _ = self.build(run_at=RUN_AT.astimezone(timezone.utc))
        self.assertEqual(RUN_AT.isoformat(), report["run_at"])


if __name__ == "__main__":
    unittest.main()
