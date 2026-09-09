import copy
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from utils import mail_manual_review as review


BODY = "请学院在2026年9月20日17:00前提交申报表，发送教务处，采用邮件报送。"


def message(identifier="new-mail", body=BODY):
    return {"id": identifier, "subject": "教学项目申报", "received_at": "2026-09-09T09:00:00+08:00",
            "body_text": body, "summary": "待整理", "category": "待整理", "attachments": [],
            "attachment_reviews": [], "sender": "private@example.test", "secret": "never-share"}


def evidence(quote=BODY, source="body"):
    return [{"source": source, "quote": quote}]


def action():
    return {"title": "提交申报表", "requirement": "填写申报表后采用邮件报送教务处。",
            "owner": "学院", "recipient": "教务处", "submission_method": "邮件报送",
            "due_at": "2026-09-20T17:00:00+08:00", "due_text": "2026年9月20日17:00前", "due_basis": "body",
            "evidence": evidence()}


def response(identifier="new-mail"):
    return {"id": identifier, "category": "教学", "summary": "学院须在9月20日17:00前将申报表邮件报送教务处。",
            "evidence": evidence(), "actions": [action()]}


class MailManualReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dashboard = {"messages": [], "actions": []}
        self.batch = {"messages": [message()], "actions": [], "errors": []}

    def run_review(self, output=None):
        with patch.object(review, "_invoke", return_value=output if output is not None else [response()]) as invoke:
            result = review.review_batch(self.batch, self.dashboard, self.root)
        return result, invoke

    def assert_invalid(self, output):
        with self.assertRaises(review.ReviewError) as caught:
            self.run_review(output)
        self.assertEqual("REVIEW_OUTPUT_INVALID", caught.exception.code)

    def test_new_message_gets_grounded_summary_and_unconfirmed_stable_action(self):
        old_batch, old_dashboard = copy.deepcopy(self.batch), copy.deepcopy(self.dashboard)
        result, invoke = self.run_review()
        self.assertEqual(old_batch, self.batch)
        self.assertEqual(old_dashboard, self.dashboard)
        self.assertIsNot(result["messages"][0], self.batch["messages"][0])
        self.assertIn("申报表", result["messages"][0]["summary"])
        task = result["actions"][0]
        self.assertEqual("needs_confirmation", task["status"])
        self.assertEqual("2026-09-20T17:00:00+08:00", task["due_at"])
        self.assertIn("17:00", task["due_text"])
        self.assertIsNone(task["completed_at"])
        same = response()
        same["actions"][0]["title"] = "  提交申报表  "
        again, _ = self.run_review([same])
        self.assertEqual(task["id"], again["actions"][0]["id"])
        packed = invoke.call_args.args[0][0]
        self.assertEqual({"id", "title", "date", "body_text", "attachment_reviews"}, set(packed))
        self.assertNotIn("private@example.test", json.dumps(packed))
        self.assertNotIn("never-share", json.dumps(packed))

    def test_existing_mail_reuses_manual_summary_and_does_not_redefine_actions(self):
        existing = message()
        existing.update(summary="人工核实：需准备两份材料，并按学院流程审核后报送。", category="行政")
        prior_action = {"id": "old-action", "message_id": "new-mail", "title": "旧任务", "status": "done"}
        self.dashboard = {"messages": [existing], "actions": [prior_action]}
        self.batch["actions"] = [{**prior_action, "status": "pending", "title": "被更改的旧任务"}]
        before = copy.deepcopy(self.dashboard)
        with patch.object(review, "_invoke", side_effect=AssertionError("no AI for old messages")):
            result = review.review_batch(self.batch, self.dashboard, self.root)
        self.assertEqual(existing["summary"], result["messages"][0]["summary"])
        self.assertEqual("行政", result["messages"][0]["category"])
        self.assertEqual([], result["actions"])
        self.assertEqual(before, self.dashboard)

    def test_only_unseen_ids_are_sent_when_batch_contains_existing_mail(self):
        self.dashboard["messages"] = [message("old-mail")]
        self.batch["messages"].insert(0, message("old-mail", "do not transmit this old content"))
        result, invoke = self.run_review()
        self.assertEqual(["new-mail"], [item["id"] for item in invoke.call_args.args[0]])
        self.assertEqual(2, len(result["messages"]))

    def test_unread_attachment_content_is_not_sent_and_limit_is_added(self):
        self.batch["messages"][0]["attachments"] = [{"id": "a", "data": b"not-sent"}]
        self.batch["messages"][0]["attachment_reviews"] = [
            {"id": "a", "name": "扫描件.pdf", "status": "unavailable", "text": "UNREAD-INJECTION", "reason": "扫描件"}]
        result, invoke = self.run_review()
        self.assertIn("部分附件未取得可读取文字", result["messages"][0]["summary"])
        self.assertEqual("", invoke.call_args.args[0][0]["attachment_reviews"][0]["text"])
        self.assertNotIn("UNREAD-INJECTION", json.dumps(invoke.call_args.args[0]))

    def test_partial_attachment_and_body_truncation_are_explicit(self):
        self.batch["messages"][0]["body_text"] += "x" * review.MAX_BODY_CHARS
        self.batch["messages"][0]["attachment_reviews"] = [
            {"id": "a", "name": "材料.txt", "status": "partial", "text": "已读取内容", "truncated": True}]
        result, invoke = self.run_review()
        self.assertIn("正文超过本次读取上限", result["messages"][0]["summary"])
        self.assertIn("部分附件仅读取了部分文字", result["messages"][0]["summary"])
        self.assertEqual(review.MAX_BODY_CHARS, len(invoke.call_args.args[0][0]["body_text"]))

    def test_no_readable_text_uses_fixed_summary_without_actions(self):
        self.batch["messages"][0] = message(body="")
        value = response()
        value.update(summary="模型的任意陈述", evidence=[], actions=[])
        result, _ = self.run_review([value])
        self.assertEqual("正文与附件均无可读取文字，具体事项和要求需人工核实。", result["messages"][0]["summary"])

    def test_missing_or_fabricated_evidence_is_rejected(self):
        for field in ("summary", "action"):
            value = response()
            target = value if field == "summary" else value["actions"][0]
            target["evidence"] = evidence("来源中不存在这句话")
            with self.subTest(field=field):
                self.assert_invalid([value])

    def test_cannot_cite_unread_attachment(self):
        self.batch["messages"][0]["attachment_reviews"] = [
            {"id": "a", "name": "未读.pdf", "status": "unavailable", "text": BODY}]
        value = response()
        value["evidence"] = evidence(source="attachment:a")
        self.assert_invalid([value])

    def test_read_attachment_is_valid_source_for_requirements(self):
        self.batch["messages"][0]["body_text"] = "请查看附件。"
        self.batch["messages"][0]["attachment_reviews"] = [
            {"id": "a", "name": "通知.txt", "status": "read", "text": BODY}]
        value = response()
        value["evidence"] = evidence(source="attachment:a")
        value["actions"][0]["evidence"] = evidence(source="attachment:a")
        value["actions"][0]["due_basis"] = "attachment:a"
        result, _ = self.run_review([value])
        self.assertEqual("2026-09-20T17:00:00+08:00", result["actions"][0]["due_at"])

    def test_explicit_month_day_reuses_receive_year_with_confirmation_basis(self):
        body = "请于9月23日前提交材料。"
        self.batch["messages"][0]["body_text"] = body
        value = response()
        value["evidence"] = evidence(body)
        task = value["actions"][0]
        task.update(owner=None, recipient=None, submission_method=None, due_at="2026-09-23",
                    due_text="9月23日前", due_basis="body", evidence=evidence(body))
        result, _ = self.run_review([value])
        self.assertEqual("2026-09-23", result["actions"][0]["due_at"])
        self.assertEqual("body；原文日期 + 邮件接收年份；未明示年份待确认", result["actions"][0]["due_basis"])
        self.assertEqual("needs_confirmation", result["actions"][0]["status"])

    def test_explicit_month_day_and_clock_keep_precise_shanghai_time(self):
        body = "请于9月11日16:00前提交材料。"
        self.batch["messages"][0]["body_text"] = body
        value = response()
        value["evidence"] = evidence(body)
        value["actions"][0].update(owner=None, recipient=None, submission_method=None,
            due_at="2026-09-11T16:00:00+08:00", due_text="9月11日16:00前", due_basis="body", evidence=evidence(body))
        result, _ = self.run_review([value])
        self.assertEqual("2026-09-11T16:00:00+08:00", result["actions"][0]["due_at"])

    def test_cross_year_and_ambiguous_slash_dates_stay_null(self):
        for body, due_text in (("请于12/1前提交材料。", "12/1前"), ("请于1月5日前提交材料。", "1月5日前")):
            self.batch["messages"][0].update(body_text=body, received_at="2026-12-20T09:00:00+08:00")
            value = response()
            value["evidence"] = evidence(body)
            value["actions"][0].update(owner=None, recipient=None, submission_method=None,
                due_at=None, due_text=due_text, due_basis="body", evidence=evidence(body))
            result, _ = self.run_review([value])
            self.assertIsNone(result["actions"][0]["due_at"])

    def test_date_only_does_not_get_an_invented_clock(self):
        body = "请于2026年9月20日前提交材料。"
        self.batch["messages"][0]["body_text"] = body
        value = response()
        value["evidence"] = evidence(body)
        value["actions"][0].update(owner=None, recipient=None, submission_method=None,
            due_at="2026-09-20", due_text="2026年9月20日前", due_basis="body", evidence=evidence(body))
        result, _ = self.run_review([value])
        self.assertEqual("2026-09-20", result["actions"][0]["due_at"])
        value["actions"][0]["due_at"] = "2026-09-20T23:59:00+08:00"
        self.assert_invalid([value])

    def test_clock_time_and_unsupported_deadline_are_rejected(self):
        for deadline in ("2026-09-20T23:59:00+08:00", "2026-09-21", "2026-02-30", "2026-09-20"):
            value = response()
            value["actions"][0]["due_at"] = deadline
            with self.subTest(deadline=deadline):
                self.assert_invalid([value])

    def test_unknown_deadline_and_people_remain_null(self):
        value = response()
        value["actions"][0].update(owner=None, recipient=None, submission_method=None,
                                    due_at=None, due_text=None, due_basis=None)
        result, _ = self.run_review([value])
        self.assertIsNone(result["actions"][0]["due_at"])
        self.assertIsNone(result["actions"][0]["owner"])

    def test_unsupported_owner_or_extra_fields_or_duplicate_tasks_are_rejected(self):
        values = []
        owner = response()
        owner["actions"][0]["owner"] = "不存在的负责人"
        values.append(owner)
        extra = response()
        extra["actions"][0]["status"] = "done"
        values.append(extra)
        duplicate = response()
        duplicate["actions"].append(copy.deepcopy(duplicate["actions"][0]))
        values.append(duplicate)
        for value in values:
            self.assert_invalid([value])

    def test_same_title_with_distinct_material_requirements_has_distinct_ids(self):
        body = "请各单位提交竞赛报名表；入围后提交决赛展示材料。"
        self.batch["messages"][0]["body_text"] = body
        value = response()
        value["evidence"] = evidence(body)
        value["actions"] = []
        for requirement in ("请各单位提交竞赛报名表", "入围后提交决赛展示材料"):
            task = action()
            task.update(title="提交材料", requirement=requirement, owner=None, recipient=None,
                submission_method=None, due_at=None, due_text=None, due_basis=None, evidence=evidence(requirement))
            value["actions"].append(task)
        result, _ = self.run_review([value])
        self.assertEqual(2, len({item["id"] for item in result["actions"]}))

    def test_missing_extra_and_duplicate_message_outputs_are_rejected(self):
        for output in ([], [response("alien")], [response(), response()], [response(["invalid"])], [response(None)]):
            self.assert_invalid(output)

    def test_batch_caps_fail_before_any_model_call(self):
        self.batch["messages"] = [message(str(i)) for i in range(review.MAX_MESSAGES + 1)]
        with patch.object(review, "_invoke", side_effect=AssertionError("must not invoke")):
            with self.assertRaisesRegex(review.ReviewError, "REVIEW_FAILED"):
                review.review_batch(self.batch, self.dashboard, self.root)

    def test_command_disables_external_channels_without_bypass_or_model_override(self):
        with patch.object(review, "_mcp_names", return_value=["node_repl", "tyc-mcp"]):
            command = review._command("codex.exe", self.root / "schema.json", self.root / "work")
        self.assertIn("--ephemeral", command)
        self.assertEqual("read-only", command[command.index("--sandbox") + 1])
        for feature in ("shell_tool", "apps", "plugins", "hooks", "browser_use", "computer_use", "image_generation", "multi_agent", "code_mode_host"):
            self.assertIn(["--disable", feature], [command[i:i+2] for i in range(len(command))])
        self.assertIn('web_search="disabled"', command)
        self.assertIn('mcp_servers.node_repl.enabled=false', command)
        self.assertIn('mcp_servers.tyc-mcp.enabled=false', command)
        self.assertNotIn("--model", command)
        self.assertNotIn("--json", command)
        self.assertNotIn("--output-last-message", command)
        self.assertFalse(any("bypass" in item or item == "--approve-for-me" for item in command))
        self.assertEqual("-", command[-1])

    def test_two_hundred_messages_split_by_count_and_chunk_size(self):
        packed = [review._pack(message(str(i), "文" * review.MAX_BODY_CHARS))[0] for i in range(200)]
        chunks = list(review._chunks(packed))
        self.assertEqual(200, sum(len(chunk) for chunk in chunks))
        self.assertGreater(len(json.dumps(packed, ensure_ascii=False)), 180000)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), review.CHUNK_MESSAGES)
            self.assertLessEqual(sum(len(json.dumps(item, ensure_ascii=False)) for item in chunk), review.MAX_CHUNK_CHARS)
        self.assertGreaterEqual(review.TOTAL_TIMEOUT_SECONDS, 1200)

    def test_mcp_reader_only_returns_names_and_rejects_inline_maps(self):
        config = self.root / "config.toml"
        config.write_text('[mcp_servers.node_repl]\nsecret = "DO-NOT-RETURN"\n[mcp_servers."a-b".http_headers]\nAuthorization="DO-NOT-RETURN"\n', encoding="utf-8")
        with patch.dict(review.os.environ, {"CODEX_HOME": str(self.root)}):
            self.assertEqual(["a-b", "node_repl"], review._mcp_names())
            config.write_text('mcp_servers = {inline = {command="never-run"}}', encoding="utf-8")
            with self.assertRaisesRegex(review.ReviewError, "REVIEW_UNAVAILABLE"):
                review._mcp_names()

    def invoke_mock(self, side_effect):
        with patch.object(review, "_codex_executable", return_value="codex.exe"), \
             patch.object(review, "_mcp_names", return_value=[]), \
             patch.object(review.subprocess, "run", side_effect=side_effect) as run:
            packed, _ = review._pack(message())
            result = review._invoke([packed], self.root)
        return result, run

    def test_subprocess_uses_stdin_memory_and_only_writes_nonprivate_schema(self):
        def fake_run(command, **kwargs):
            work = Path(command[command.index("-C") + 1])
            schema = Path(command[command.index("--output-schema") + 1])
            self.assertEqual([], list(work.iterdir()))
            self.assertEqual({work.name, schema.name}, {p.name for p in work.parent.iterdir()})
            self.assertEqual(review.OUTPUT_SCHEMA, json.loads(schema.read_text(encoding="utf-8")))
            self.assertNotIn(BODY, " ".join(command))
            self.assertIn(BODY, kwargs["input"])
            self.assertIn("不可信邮件", kwargs["input"])
            self.assertTrue(kwargs["capture_output"])
            self.assertLessEqual(kwargs["timeout"], review.TIMEOUT_SECONDS)
            self.assertFalse(kwargs["check"])
            self.runtime = work.parent
            return SimpleNamespace(returncode=0, stdout=json.dumps({"messages": [response()]}), stderr="must-not-be-persisted")
        result, _ = self.invoke_mock(fake_run)
        self.assertEqual("new-mail", result[0]["id"])
        self.assertFalse(self.runtime.exists())

    def test_cli_failures_have_fixed_codes_without_raw_output(self):
        cases = [
            (subprocess.TimeoutExpired("cmd", 240, output="SECRET"), "REVIEW_TIMEOUT"),
            (OSError("SECRET"), "REVIEW_FAILED"),
            (SimpleNamespace(returncode=1, stdout="SECRET", stderr="SECRET"), "REVIEW_FAILED"),
            (SimpleNamespace(returncode=0, stdout="SECRET", stderr="SECRET"), "REVIEW_OUTPUT_INVALID"),
            (SimpleNamespace(returncode=0, stdout='{"messages":[],"messages":[]}', stderr=""), "REVIEW_OUTPUT_INVALID"),
        ]
        for result, expected in cases:
            with self.subTest(expected=expected):
                def fake_run(*args, **kwargs):
                    if isinstance(result, Exception):
                        raise result
                    return result
                with self.assertRaises(review.ReviewError) as caught:
                    self.invoke_mock(fake_run)
                self.assertEqual(expected, str(caught.exception))
                self.assertNotIn("SECRET", str(caught.exception))

    def test_failure_does_not_partially_mutate_original_batch(self):
        self.batch["messages"].append(message("second"))
        original = copy.deepcopy(self.batch)
        second = response("second")
        second["evidence"] = []
        self.assert_invalid([response(), second])
        self.assertEqual(original, self.batch)


if __name__ == "__main__":
    unittest.main()
