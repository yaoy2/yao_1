"""Offline checks: no model calls, listening sockets, credentials or model CLIs.

Cancellation regressions only launch this test's own short-lived Python child.
"""
from __future__ import annotations

from copy import deepcopy
from email.message import Message
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import adapters
import gemini_bridge
import server as room


def request(**changes):
    value = {
        "request_id": str(uuid.uuid4()),
        "prompt": "怎样比较这三种方案？",
        "participants": ["codex", "grok", "gemini"],
        "histories": {provider: [] for provider in ("codex", "grok", "gemini")},
    }
    value.update(changes)
    return value


def conversation(prompt):
    """Read the serialized conversation without coupling tests to prompt wording."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(prompt):
        if char != "[":
            continue
        try:
            value, _ = decoder.raw_decode(prompt[index:])
        except ValueError:
            continue
        if isinstance(value, list) and all(isinstance(message, dict) and
                                          "role" in message and "text" in message for message in value):
            return value
    raise AssertionError("Prompt must contain a JSON conversation")


def gemini_init(**changes):
    info = {"tools": ["run_command", "read_file", "write_to_file"],
            "model": "gemini-3.1-pro-high", "agent": "room-text-only",
            "permission_mode": "request-review"}
    info.update(changes)
    return {"event": "init", "init": info}


class RequestTests(unittest.TestCase):
    def test_valid_request_keeps_each_history_separate_and_copies_messages(self):
        histories = {provider: [{"role": "user", "text": f"给 {provider} 的旧问题"},
                                {"role": "assistant", "text": f"{provider} 的旧答案"}]
                     for provider in ("codex", "grok", "gemini")}
        data = request(histories=histories)
        before = deepcopy(data)
        rid, prompt, participants, cleaned = room.validate_request(data)
        self.assertEqual(rid, data["request_id"])
        self.assertEqual(prompt, data["prompt"])
        self.assertEqual(participants, data["participants"])
        self.assertEqual(cleaned, histories)
        for provider in participants:
            self.assertIsNot(cleaned[provider], histories[provider])
            self.assertIsNot(cleaned[provider][0], histories[provider][0])
        self.assertEqual(data, before)

    def test_new_conversation_accepts_empty_histories(self):
        data = request()
        self.assertEqual(room.validate_request(data)[3], data["histories"])

    def test_rejects_invalid_controls(self):
        cases = [
            {"request_id": "not-an-id"}, {"request_id": None},
            {"participants": []}, {"participants": ["codex", "codex"]},
            {"participants": ["unknown"]}, {"participants": [{"codex": True}]},
            {"participants": "codex"}, {"participants": ["claude"]},
            {"prompt": ""}, {"prompt": " \n "}, {"prompt": None},
            {"prompt": []}, {"prompt": 12},
        ]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                room.validate_request(request(**change))

    def test_rejects_malformed_histories_and_message_roles(self):
        for histories in (None, [], "history", {"unknown": []}, {"codex": None}):
            with self.subTest(histories=histories), self.assertRaises(ValueError):
                room.validate_request(request(histories=histories))
        cases = [["text"], [{"role": "system", "text": "x"}],
                 [{"role": "tool", "text": "x"}], [{"text": "missing role"}],
                 [{"role": "user", "text": "  "}], [{"role": "user", "text": None}],
                 [{"role": "assistant", "text": 1}]]
        for messages in cases:
            with self.subTest(messages=messages), self.assertRaises(ValueError):
                room.validate_request(request(histories={"codex": messages}))

    def test_context_and_message_count_boundaries(self):
        msg = {"role": "user", "text": "字" * (room.MAX_CONTEXT - 1)}
        histories = {provider: [dict(msg)] for provider in ("codex", "grok", "gemini")}
        validated = room.validate_request(request(prompt="问", histories=histories))
        self.assertEqual(validated[3], histories, "The context cap applies independently to each lane")
        with self.assertRaises(ValueError):
            room.validate_request(request(prompt="问", histories={"codex": [dict(msg, text=msg["text"] + "字")]}))
        self.assertEqual(room.validate_request(request(prompt="字" * room.MAX_CONTEXT))[1], "字" * room.MAX_CONTEXT)
        with self.assertRaises(ValueError):
            room.validate_request(request(prompt="字" * (room.MAX_CONTEXT + 1)))
        tiny = dict(msg, text="字")
        self.assertEqual(len(room.validate_request(request(histories={"codex": [tiny] * 200}))[3]["codex"]), 200)
        with self.assertRaises(ValueError):
            room.validate_request(request(histories={"codex": [tiny] * 201}))


class ComparisonTests(unittest.TestCase):
    def test_three_lanes_run_concurrently_with_own_history_and_same_latest_prompt(self):
        providers = ["codex", "grok", "gemini"]
        prompt = "同一个新问题：第一行\n第二行与 @引用"
        histories = {provider: [{"role": "user", "text": f"{provider} 的旧问题"},
                                {"role": "assistant", "text": f"{provider} 独有旧答案"}]
                     for provider in providers}
        before = deepcopy(histories)
        barrier, lock = threading.Barrier(3, timeout=3), threading.Lock()
        calls, events, threads = {}, [], set()

        def runner(provider, prepared, emit, cancel):
            with lock:
                calls[provider] = conversation(prepared)
                threads.add(threading.get_ident())
            barrier.wait()  # A sequential implementation cannot pass this barrier.
            emit({"type": "delta", "text": f"{provider} 部分回答"})
            return f"{provider} 完整回答"

        room.compare(prompt, providers, histories, events.append, threading.Event(), runner=runner)
        self.assertEqual(set(calls), set(providers))
        self.assertEqual(len(threads), 3)
        self.assertEqual(histories, before)
        self.assertFalse(any(event["type"] == "error" for event in events))
        for provider in providers:
            self.assertEqual(calls[provider], before[provider] + [{"role": "user", "text": prompt}])
            lane_events = [event for event in events if event.get("provider") == provider]
            self.assertEqual([event["type"] for event in lane_events], ["start", "delta", "message"])
            self.assertEqual(lane_events[-1]["text"], f"{provider} 完整回答")

    def test_only_selected_lanes_are_called(self):
        calls = []

        def runner(provider, prepared, emit, cancel):
            calls.append((provider, conversation(prepared)))
            return "仅这一栏回答"

        room.compare("单独提问", ["grok"], {"codex": [{"role": "assistant", "text": "其他栏秘密"}],
                     "grok": []}, lambda _: None, threading.Event(), runner=runner)
        self.assertEqual(calls, [("grok", [{"role": "user", "text": "单独提问"}])])

    def test_failed_lane_does_not_stop_successful_lanes_or_cross_answers(self):
        providers, events, calls = ["codex", "grok", "gemini"], [], {}
        barrier = threading.Barrier(3, timeout=3)

        def runner(provider, prepared, emit, cancel):
            calls[provider] = conversation(prepared)
            barrier.wait()
            if provider == "grok":
                emit({"type": "delta", "text": "未完成的文本"})
                raise RuntimeError("temporary failure")
            return f"{provider} 成功"

        room.compare("新问题", providers, {provider: [] for provider in providers},
                     events.append, threading.Event(), runner=runner)
        self.assertEqual([event["provider"] for event in events if event["type"] == "error"], ["grok"])
        self.assertEqual({event["provider"] for event in events if event["type"] == "message"}, {"codex", "gemini"})
        self.assertEqual(calls, {provider: [{"role": "user", "text": "新问题"}] for provider in providers})

    def test_cancel_during_parallel_replies_never_accepts_partial_answers(self):
        providers, cancel, events, calls = ["codex", "grok", "gemini"], threading.Event(), [], []
        barrier = threading.Barrier(3, timeout=3)

        def runner(provider, prepared, emit, stopped):
            calls.append((provider, stopped))
            barrier.wait()
            if provider == "codex":
                stopped.set()
                raise adapters.Cancelled("已停止")
            self.assertTrue(stopped.wait(timeout=3))
            return "取消后的部分答案"

        room.compare("新问题", providers, {provider: [] for provider in providers},
                     events.append, cancel, runner=runner)
        self.assertEqual({provider for provider, _ in calls}, set(providers))
        self.assertTrue(all(stopped is cancel for _, stopped in calls))
        self.assertFalse(any(event["type"] in ("message", "error") for event in events))

    def test_gemini_prompt_escapes_file_reference_without_changing_user_text(self):
        history = [{"role": "user", "text": "阅读 @private.txt？只是文字。"}]
        prepared = room.make_prompt("gemini", history, "@another.txt 是什么意思？")
        self.assertNotIn("@private.txt", prepared)
        self.assertNotIn("@another.txt", prepared)
        self.assertEqual(conversation(prepared), history + [{"role": "user", "text": "@another.txt 是什么意思？"}])


class CancellationStateTests(unittest.TestCase):
    def test_cancel_before_begin_prevents_any_cli_call(self):
        state, events, calls = room.RoomState(), [], []
        request_id = str(uuid.uuid4())
        state.cancel_request(request_id)
        self.assertTrue(state.begin(request_id))

        def runner(provider, *args):
            calls.append(provider)
            return "must never be generated"

        room.compare("问题", ["codex", "grok"], {"codex": [], "grok": []},
                     events.append, state.cancel, runner=runner)
        self.assertTrue(state.cancel.is_set())
        self.assertEqual(calls, [])
        self.assertEqual(events, [])

    def test_early_cancel_does_not_cancel_next_distinct_request(self):
        state, calls = room.RoomState(), []
        cancelled_id, next_id = str(uuid.uuid4()), str(uuid.uuid4())
        state.cancel_request(cancelled_id)
        self.assertTrue(state.begin(cancelled_id))
        self.assertTrue(state.cancel.is_set())
        state.finish()
        self.assertTrue(state.begin(next_id))

        def runner(provider, *args):
            calls.append(provider)
            return "正常回复"

        room.compare("问题", ["codex", "grok"], {"codex": [], "grok": []},
                     lambda _: None, state.cancel, runner=runner)
        self.assertFalse(state.cancel.is_set())
        self.assertEqual(set(calls), {"codex", "grok"})

    def test_wrong_request_id_does_not_cancel_active_generation(self):
        state = room.RoomState()
        active_id, unrelated_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.assertTrue(state.begin(active_id))
        state.cancel_request(unrelated_id)
        self.assertEqual(state.active_id, active_id)
        self.assertFalse(state.cancel.is_set())
        state.cancel_request(active_id)
        self.assertTrue(state.cancel.is_set())

    def test_early_cancellation_expires_after_sixty_seconds(self):
        state, request_id = room.RoomState(), str(uuid.uuid4())
        with patch.object(room.time, "monotonic", return_value=100.0):
            state.cancel_request(request_id)
        with patch.object(room.time, "monotonic", return_value=161.0):
            self.assertTrue(state.begin(request_id))
        self.assertFalse(state.cancel.is_set())


class EventTests(unittest.TestCase):
    def test_gemini_only_accepts_public_assistant_text(self):
        for step in ({"step_type": "user_input", "text_delta": "private prompt"},
                     {"step_type": "thought", "text_delta": "private thought"},
                     {"step_type": "thinking", "text_delta": "private reasoning"},
                     {"step_type": "checkpoint", "text_delta": "private checkpoint"},
                     {"step_type": "agent_response", "text_delta": {"private": True}}):
            with self.subTest(step=step):
                self.assertEqual(adapters.parse_event("gemini", {"event": "step_update", "step_update": step}), [])
        for state in ("ACTIVE", "DONE"):
            with self.subTest(state=state):
                self.assertEqual(adapters.parse_event("gemini", {"event": "step_update", "step_update": {
                    "step_type": "agent_response", "state": state, "text_delta": "一部分"}}), [("delta", "一部分")])

    def test_gemini_init_accepts_build_catalog_with_strict_agent_and_permissions(self):
        for model in ("gemini-3.1-pro-high", "gemini-3.8-flash-high"):
            for catalog in ([], ["run_command", "read_file"] + [f"catalog_tool_{i}" for i in range(58)]):
                with self.subTest(model=model, tools=len(catalog)):
                    self.assertEqual(adapters.parse_event("gemini", gemini_init(
                        model=model, tools=catalog)), [("ready", "")])

    def test_gemini_init_rejects_missing_or_malformed_configuration(self):
        valid = gemini_init()["init"]
        invalid = [None, {}, [], "init"]
        invalid.extend({key: value for key, value in valid.items() if key != missing}
                       for missing in ("tools", "model", "agent", "permission_mode"))
        for key, values in {
            "model": ("claude", "Gemini Pro", "not-gemini-3.1-pro-high", "", None, ["gemini-3.1-pro-high"], 42),
            "agent": ("default", "room-text-only-other", "ROOM-TEXT-ONLY", "", None, ["room-text-only"]),
            "permission_mode": ("always-proceed", "", None, ["request-review"]),
            "tools": (None, {}, "[]", [None], ["read_file", {"name": "run_command"}]),
        }.items():
            invalid.extend(dict(valid, **{key: value}) for value in values)
        for initialization in invalid:
            with self.subTest(initialization=initialization):
                parsed = adapters.parse_event("gemini", {"event": "init", "init": initialization})
                self.assertTrue(any(kind == "error" for kind, _ in parsed))
                self.assertFalse(any(kind in ("ready", "delta", "final", "complete") for kind, _ in parsed))

    def test_gemini_tool_steps_are_errors_without_exposing_tool_contents(self):
        for state in ("ACTIVE", "DONE"):
            with self.subTest(state=state):
                parsed = adapters.parse_event("gemini", {"event": "step_update", "step_update": {
                    "step_type": "tool", "state": state, "tool_name": "read_file",
                    "text_delta": "private tool text", "tool_info": {
                        "name": "read_file", "parameters": {"path": "private path"},
                        "output": "private output"}}})
                self.assertTrue(any(kind == "error" for kind, _ in parsed))
                self.assertFalse(any(kind in ("ready", "delta", "final", "complete") for kind, _ in parsed))
                self.assertFalse(any("private" in text for _, text in parsed))

    def test_gemini_result_success_and_errors_are_unambiguous(self):
        self.assertEqual(adapters.parse_event("gemini", {"event": "result", "result": {
            "status": "SUCCESS", "response": "完整答案"}}), [("final", "完整答案"), ("complete", "")])
        for result in ({"status": "ERROR", "error": "quota exceeded"},
                       {"status": "SUCCESS", "response": "not accepted", "error": "contradictory error"},
                       {"error": "failed"}, {"status": "UNKNOWN"}, {"status": "success"},
                       {"status": "CANCELLED"}, {"status": "MAX_TURNS"}):
            with self.subTest(result=result):
                parsed = adapters.parse_event("gemini", {"event": "result", "result": result})
                self.assertTrue(any(kind == "error" for kind, _ in parsed))
                self.assertFalse(any(kind in ("final", "complete") for kind, _ in parsed))

    def test_codex_only_public_answer_and_real_completion(self):
        for item in [{"type": "reasoning", "text": "private thought"},
                     {"type": "command_execution", "aggregated_output": "private file"},
                     {"type": "mcp_tool_call", "result": "private tool result"}]:
            self.assertEqual(adapters.parse_event("codex", {"type": "item.completed", "item": item}), [])
        self.assertEqual(adapters.parse_event("codex", {"type": "item.completed", "item":
                         {"type": "agent_message", "text": "public"}}), [("final", "public")])
        self.assertEqual(adapters.parse_event("codex", {"type": "turn.completed"}), [("complete", "")])
        self.assertEqual(adapters.parse_event("codex", {"type": "turn.failed", "error":
                         {"message": "failed"}}), [("error", "failed")])

    def test_anthropic_style_stream_omits_thought_and_tool_content(self):
        for provider in ("claude", "grok"):
            for delta in [{"type": "thinking_delta", "thinking": "private"},
                          {"type": "input_json_delta", "partial_json": "secret tool args"}]:
                with self.subTest(provider=provider, delta=delta):
                    event = {"type": "stream_event", "event": {"type": "content_block_delta", "delta": delta}}
                    self.assertEqual(adapters.parse_event(provider, event), [])
            event = {"type": "assistant", "message": {"content": [
                {"type": "thinking", "thinking": "private"},
                {"type": "tool_use", "name": "Read", "input": {"path": "secret"}},
                {"type": "text", "text": "public"}]}}
            self.assertEqual(adapters.parse_event(provider, event), [("final", "public")])
            self.assertEqual(adapters.parse_event(provider, {"type": "user", "message": {
                "content": [{"type": "tool_result", "content": "secret file"}]}}), [])

    def test_message_stop_is_not_final_process_completion(self):
        for provider in ("claude", "grok"):
            with self.subTest(provider=provider):
                self.assertNotIn(("complete", ""), adapters.parse_event(provider, {"type": "message_stop"}))

    def test_success_result_and_all_error_result_subtypes(self):
        for provider in ("claude", "grok"):
            with self.subTest(provider=provider):
                self.assertEqual(adapters.parse_event(provider, {"type": "result", "subtype": "success",
                                 "result": "answer"}), [("final", "answer"), ("complete", "")])
            for subtype in ("error_max_turns", "error_during_execution", "error_max_budget_usd",
                            "error_max_structured_output_retries"):
                with self.subTest(provider=provider, subtype=subtype):
                    parsed = adapters.parse_event(provider, {"type": "result", "subtype": subtype,
                                                            "result": "not complete"})
                    self.assertTrue(any(k == "error" for k, _ in parsed))
                    self.assertFalse(any(k == "complete" for k, _ in parsed))


class FakeProcess:
    def __init__(self, events, code=0, error=""):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))
        self.stderr = io.StringIO(error)
        self.returncode = code
        self.killed = False

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True


class RunnerTests(unittest.TestCase):
    def assert_large_input_can_stop_before_child_reads_stdin(self, *, timeout):
        """Use a real OS pipe boundary; the harmless child deliberately never reads."""
        children, workspaces, errors = [], [], []
        started, cancel = threading.Event(), threading.Event()
        original_popen = adapters.subprocess.Popen

        def launch(*args, **kwargs):
            child = original_popen(*args, **kwargs)
            children.append(child)
            workspaces.append(Path(kwargs["cwd"]))
            started.set()
            return child

        def run():
            try:
                adapters.run_cli("codex", "字" * 60_000, lambda _: None, cancel,
                                 timeout=0.1 if timeout else 10)
            except Exception as error:
                errors.append(error)

        command = ([sys.executable, "-c", "import time; time.sleep(10)"], "字" * 60_000, None)
        with patch.object(adapters, "command", return_value=command), \
             patch.object(adapters.subprocess, "Popen", side_effect=launch):
            task = threading.Thread(target=run, daemon=True)
            try:
                task.start()
                self.assertTrue(started.wait(timeout=5), "The harmless test child must start")
                if not timeout:
                    cancel.set()
                task.join(timeout=2)
                self.assertFalse(task.is_alive(), "Large stdin must not block cancellation or the deadline")
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], RuntimeError if timeout else adapters.Cancelled)
                self.assertTrue(all(child.poll() is not None for child in children),
                                "Stopping must reap every child created by this test")
                self.assertTrue(all(not workspace.exists() for workspace in workspaces),
                                "The temporary prompt and request directory must be removed")
            finally:
                cancel.set()
                for child in children:
                    if child.poll() is None:
                        child.kill()
                        child.wait(timeout=5)
                task.join(timeout=5)

    def test_large_input_remains_cancellable_when_child_never_reads_stdin(self):
        self.assert_large_input_can_stop_before_child_reads_stdin(timeout=False)

    def test_large_input_deadline_applies_when_child_never_reads_stdin(self):
        self.assert_large_input_can_stop_before_child_reads_stdin(timeout=True)

    def invoke(self, provider, events, code=0):
        process, emitted = FakeProcess(events, code), []
        with patch.object(adapters, "command", return_value=(["fake.exe"], "prompt", None)), \
             patch.object(adapters.subprocess, "Popen", return_value=process) as popen:
            result = adapters.run_cli(provider, "prompt", emitted.append, threading.Event())
            self.assertFalse(popen.call_args.kwargs.get("shell", False))
            return result, emitted

    def test_codex_completion_required_even_when_exit_is_zero(self):
        message = {"type": "item.completed", "item": {"type": "agent_message", "text": "answer"}}
        with self.assertRaisesRegex(RuntimeError, "完成"):
            self.invoke("codex", [message])
        answer, _ = self.invoke("codex", [message, {"type": "turn.completed"}])
        self.assertEqual(answer, "answer")

    def test_gemini_success_requires_completion_and_preserves_streamed_text(self):
        initialization = gemini_init()
        message = {"event": "step_update", "step_update": {
            "step_type": "agent_response", "state": "ACTIVE", "text_delta": "Gemini 答案"}}
        with self.assertRaisesRegex(RuntimeError, "完成"):
            self.invoke("gemini", [initialization, message])
        answer, emitted = self.invoke("gemini", [initialization, message, {
            "event": "result", "result": {"status": "SUCCESS", "response": "Gemini 答案"}}])
        self.assertEqual(answer, "Gemini 答案")
        self.assertEqual(emitted, [{"type": "delta", "text": "Gemini 答案"}])
        with self.assertRaisesRegex(RuntimeError, "quota"):
            self.invoke("gemini", [initialization, message, {
                "event": "result", "result": {"status": "ERROR", "error": "quota exceeded"}}])

    def test_gemini_final_answer_replaces_partial_stream(self):
        answer, emitted = self.invoke("gemini", [
            gemini_init(),
            {"event": "step_update", "step_update": {"step_type": "agent_response", "text_delta": "部分"}},
            {"event": "result", "result": {"status": "SUCCESS", "response": "完整回答"}},
        ])
        self.assertEqual(answer, "完整回答")
        self.assertEqual(emitted, [{"type": "delta", "text": "部分"}])

    def test_gemini_missing_or_unsafe_init_stops_before_any_answer_is_accepted(self):
        tail = [{"event": "step_update", "step_update": {
                    "step_type": "agent_response", "text_delta": "must never be emitted"}},
                {"event": "result", "result": {"status": "SUCCESS", "response": "must never be accepted"}}]
        invalid_starts = [[], [gemini_init(model="claude")], [gemini_init(agent="default")],
                          [gemini_init(agent=None)], [gemini_init(permission_mode="always-proceed")],
                          [gemini_init(permission_mode=None)], [gemini_init(tools=[None])]]
        for initial in invalid_starts:
            with self.subTest(initial=initial):
                process, emitted = FakeProcess(initial + tail, code=None), []

                def kill():
                    process.killed = True
                    process.returncode = -9

                process.kill = kill
                with patch.object(adapters, "command", return_value=(["fake.exe"], "prompt", None)), \
                     patch.object(adapters.subprocess, "Popen", return_value=process):
                    with self.assertRaises(RuntimeError):
                        adapters.run_cli("gemini", "prompt", emitted.append, threading.Event())
                self.assertTrue(process.killed, "Unsafe initialization must stop this request's child")
                self.assertEqual(process.returncode, -9)
                self.assertEqual(emitted, [], "Do not publish text from an unverified model or tool configuration")

    def test_gemini_unexpected_tool_step_stops_the_child_and_rejects_later_success(self):
        for state in ("ACTIVE", "DONE"):
            with self.subTest(state=state):
                events = [gemini_init(), {"event": "step_update", "step_update": {
                              "step_type": "tool", "state": state, "tool_name": "read_file",
                              "tool_info": {"output": "private output"}}},
                          {"event": "step_update", "step_update": {
                              "step_type": "agent_response", "text_delta": "must never be emitted"}},
                          {"event": "result", "result": {"status": "SUCCESS", "response": "not accepted"}}]
                process, emitted = FakeProcess(events, code=None), []

                def kill():
                    process.killed = True
                    process.returncode = -9

                process.kill = kill
                with patch.object(adapters, "command", return_value=(["fake.exe"], "prompt", None)), \
                     patch.object(adapters.subprocess, "Popen", return_value=process):
                    with self.assertRaises(RuntimeError) as caught:
                        adapters.run_cli("gemini", "prompt", emitted.append, threading.Event())
                self.assertNotIn("private output", str(caught.exception))
                self.assertTrue(process.killed)
                self.assertEqual(process.returncode, -9)
                self.assertEqual(emitted, [])

    def test_final_result_overrides_partial_stream_without_duplicate_text(self):
        events = [
            {"type": "stream_event", "event": {"type": "content_block_delta", "delta":
                                               {"type": "text_delta", "text": "部分"}}},
            {"type": "result", "subtype": "success", "result": "完整回答"},
        ]
        for provider in ("claude", "grok"):
            with self.subTest(provider=provider):
                answer, emitted = self.invoke(provider, events)
                self.assertEqual(answer, "完整回答")
                self.assertEqual(emitted, [{"type": "delta", "text": "部分"}])

    def test_zero_exit_does_not_hide_error_and_nonzero_does_not_accept_answer(self):
        with self.assertRaisesRegex(RuntimeError, "quota"):
            self.invoke("claude", [{"type": "result", "is_error": True, "result": "quota"}])
        with self.assertRaises(RuntimeError):
            self.invoke("grok", [{"type": "result", "result": "answer"}], code=1)


class CommandTests(unittest.TestCase):
    def test_codex_falls_back_to_latest_standard_install_when_path_is_stale(self):
        with tempfile.TemporaryDirectory(prefix="room-codex-path-") as temporary:
            root = Path(temporary)
            older = root / "OpenAI/Codex/bin/old/codex.exe"
            newer = root / "OpenAI/Codex/bin/new/codex.exe"
            for path in (older, newer):
                path.parent.mkdir(parents=True)
                path.touch()
            os.utime(older, (1_000, 1_000))
            os.utime(newer, (2_000, 2_000))
            with patch.dict(os.environ, {"LOCALAPPDATA": str(root)}, clear=True), \
                 patch.object(adapters.shutil, "which", return_value=None), \
                 patch.object(Path, "home", return_value=root / "home"):
                self.assertEqual(adapters.executable("codex"), str(newer))

    def test_grok_falls_back_to_standard_user_install_when_path_is_stale(self):
        with tempfile.TemporaryDirectory(prefix="room-grok-path-") as temporary:
            root = Path(temporary)
            native = root / "home/.grok/bin/grok.exe"
            native.parent.mkdir(parents=True)
            native.touch()
            with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "local")}, clear=True), \
                 patch.object(adapters.shutil, "which", return_value=None), \
                 patch.object(Path, "home", return_value=root / "home"):
                self.assertEqual(adapters.executable("grok"), str(native))

    def test_missing_executables_do_not_fall_back_to_host_installations(self):
        with tempfile.TemporaryDirectory(prefix="room-missing-path-") as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "local")}, clear=True), \
                 patch.object(adapters.shutil, "which", return_value=None), \
                 patch.object(Path, "home", return_value=root / "home"):
                for provider in ("codex", "grok"):
                    with self.subTest(provider=provider):
                        self.assertIsNone(adapters.executable(provider))
                        result = adapters.provider_status(provider)
                        self.assertFalse(result["available"])
                        self.assertEqual(result["detail"], "未找到命令行工具")

    def test_native_path_entry_takes_priority_over_fallbacks(self):
        with tempfile.TemporaryDirectory(prefix="room-native-path-") as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {"LOCALAPPDATA": str(root / "local")}, clear=True), \
                 patch.object(Path, "home", return_value=root / "home"):
                for provider in ("codex", "grok"):
                    native = str(root / "selected" / f"{provider}.exe")
                    with self.subTest(provider=provider), patch.object(adapters.shutil, "which", return_value=native):
                        self.assertEqual(adapters.executable(provider), native)

    def test_official_claude_environment_is_a_child_copy(self):
        environ = {"PATH": "original", "ANTHROPIC_AUTH_TOKEN": "do-not-display",
                   "ANTHROPIC_BASE_URL": "https://api.moonshot.cn/anthropic",
                   "anthropic_model": "third-party-model", "KEEP_ME": "yes"}
        with patch.dict(os.environ, environ, clear=True):
            before = dict(os.environ)
            child = adapters.official_claude_env()
            self.assertEqual(dict(os.environ), before)
            self.assertFalse(any(k.upper().startswith("ANTHROPIC_") for k in child))
            self.assertEqual(child["KEEP_ME"], "yes")

    def test_prompt_is_never_interpolated_into_command(self):
        prompt = 'Sir: $(unexpected); & echo "secret"\n--dangerously-skip-permissions'
        with tempfile.TemporaryDirectory(prefix="room-test-") as cwd, \
             patch.object(adapters, "executable", side_effect=lambda p: f"C:/fake/{p}.exe"), \
             patch.object(adapters, "codex_model_args", return_value=[]):
            for provider in ("codex", "claude", "grok"):
                with self.subTest(provider=provider):
                    args, stdin, _ = adapters.command(provider, prompt, cwd)
                    self.assertIsInstance(args, list)
                    self.assertFalse(any(prompt in arg for arg in args))
                    self.assertNotIn("--dangerously-skip-permissions", args)
                    if provider == "grok":
                        self.assertIsNone(stdin)
                        self.assertEqual(Path(args[args.index("--prompt-file") + 1]).read_text(encoding="utf-8"), prompt)
                    else:
                        self.assertEqual(stdin, prompt)
                    if provider == "claude":
                        self.assertEqual(args[args.index("--tools") + 1], "")
                        self.assertIn("--safe-mode", args)
                    if provider == "grok":
                        self.assertEqual(args[args.index("--deny") + 1], "*")
                        self.assertEqual(args[args.index("--permission-mode") + 1], "dontAsk")

    def test_model_list_alone_does_not_prove_login(self):
        cases = [("Available models: grok-4.7", False),
                 ("You are not authenticated.\nAvailable models: grok-4.7", False),
                 ("You are logged in with grok.com.\nAvailable models: grok-4.7", True)]
        for stdout, available in cases:
            with self.subTest(stdout=stdout), patch.object(adapters, "executable", return_value="fake.exe"), \
                 patch.object(adapters.subprocess, "run", return_value=SimpleNamespace(
                     stdout=stdout, stderr="", returncode=0)):
                self.assertIs(adapters.provider_status("grok")["available"], available)


class GeminiBridgeTests(unittest.TestCase):
    def test_runtime_and_profile_root_do_not_depend_on_virtualized_localappdata(self):
        with tempfile.TemporaryDirectory(prefix="room-stable-root-") as temporary:
            root = Path(temporary)
            user_home = root / "user-home"
            for local in (str(root / "normal-local"), str(root / "MSIXAppData/local"), "", None):
                inherited = {} if local is None else {"LOCALAPPDATA": local}
                with self.subTest(localappdata=local), patch.dict(os.environ, inherited, clear=True), \
                     patch.object(Path, "home", return_value=user_home):
                    self.assertEqual(gemini_bridge._app_dir(), user_home / ".ai-discussion-room")
                    self.assertEqual(gemini_bridge._profile(), user_home / ".ai-discussion-room/antigravity-profile")

    def test_native_runtime_works_without_node_or_path_lookup(self):
        with tempfile.TemporaryDirectory(prefix="room-agy-runtime-") as temporary:
            app = Path(temporary) / ".ai-discussion-room"
            binary = app / "antigravity/agy.exe"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"test binary placeholder")
            with patch.dict(os.environ, {"PATH": ""}, clear=True), \
                 patch.object(gemini_bridge, "_app_dir", return_value=app), \
                 patch.object(gemini_bridge.subprocess, "run", side_effect=AssertionError("Discovery must not execute CLI")):
                self.assertEqual(gemini_bridge._runtime(), binary)

    def test_runtime_diagnostics_preserve_missing_file_errors_without_reading_credentials(self):
        with tempfile.TemporaryDirectory(prefix="room-agy-diagnostics-") as temporary:
            app = Path(temporary) / ".ai-discussion-room"
            with patch.object(gemini_bridge, "_app_dir", return_value=app), \
                 patch.object(Path, "read_text", side_effect=AssertionError("Diagnostics must not read file contents")), \
                 patch.object(gemini_bridge.subprocess, "run", side_effect=AssertionError("Diagnostics must not execute CLI")):
                with self.assertRaisesRegex(RuntimeError, "无法访问专用 Antigravity CLI") as caught:
                    gemini_bridge._runtime()
                self.assertIn("FileNotFoundError", str(caught.exception))
                self.assertIn("WinError=", str(caught.exception))
                diagnostics = gemini_bridge.runtime_diagnostics()
            self.assertEqual(diagnostics["runtime_root"], str(app))
            self.assertEqual(diagnostics["profile"], str(app / "antigravity-profile"))
            binary_probe = diagnostics["cli_path_checks"][0]
            self.assertEqual(binary_probe["path"], str(app / "antigravity/agy.exe"))
            self.assertEqual(binary_probe["error"]["type"], "FileNotFoundError")
            self.assertNotIn("node_candidates", diagnostics)

    def test_runtime_rejects_a_directory_named_like_the_binary(self):
        with tempfile.TemporaryDirectory(prefix="room-agy-directory-") as temporary:
            app = Path(temporary)
            (app / "antigravity/agy.exe").mkdir(parents=True)
            with patch.object(gemini_bridge, "_app_dir", return_value=app):
                with self.assertRaisesRegex(RuntimeError, "不是普通文件"):
                    gemini_bridge._runtime()

    def test_model_ids_come_from_stdout_and_explicit_login_failures_are_rejected(self):
        cases = [
            ("gemini-3.1-pro-high\tGemini 3.1 Pro (High)\ngemini-3.8-flash-high\tGemini 3.8 Flash (High)\ngemini-3.1-pro-high\tGemini 3.1 Pro (High)\nclaude-model\tClaude\n", "Fetching available models...", 0,
             ["gemini-3.1-pro-high", "gemini-3.8-flash-high"]),
            ("\x1b[32mgemini-3.1-pro-high\x1b[0m\tGemini 3.1 Pro (High)", "", 0, ["gemini-3.1-pro-high"]),
            ("Available models: Claude", "", 0, None),
            ("gemini-3.1-pro-high", "", 0, None),
            ("gemini-3.1-pro-high\tGemini 3.1 Pro (High)\textra", "", 0, None),
            ("gemini-3.1-pro-high\tClaude\nclaude-model\tClaude\ngpt-oss-model\tGPT OSS", "", 0, None),
            ("Example: --model gemini-3.1-pro-high", "", 0, None),
            ("", "Example: --model gemini-3.1-pro-high", 0, None),
            ("not authenticated\ngemini-3.1-pro-high\tGemini 3.1 Pro (High)", "", 0, None),
            ("gemini-3.1-pro-high\tGemini 3.1 Pro (High)", "You are not logged in", 0, None),
            ("gemini-3.1-pro-high\tGemini 3.1 Pro (High)", "authentication required", 0, None),
            ("gemini-3.1-pro-high\tGemini 3.1 Pro (High)", "", 1, None),
        ]
        with tempfile.TemporaryDirectory(prefix="room-agy-models-") as workspace:
            for stdout, stderr, code, expected in cases:
                with self.subTest(stdout=stdout, stderr=stderr, code=code), \
                     patch.object(gemini_bridge, "_prepare", return_value=(["fake-agy.exe", "--agent", "room-text-only"], {})), \
                     patch.object(gemini_bridge.subprocess, "run", return_value=SimpleNamespace(
                         stdout=stdout, stderr=stderr, returncode=code)) as run:
                    if expected is None:
                        with self.assertRaisesRegex(RuntimeError, "登录|模型"):
                            gemini_bridge.models(workspace)
                    else:
                        self.assertEqual(gemini_bridge.models(workspace), expected)
                    self.assertEqual(run.call_args.args[0], ["fake-agy.exe", "models"])
                    self.assertEqual(run.call_args.kwargs["stdin"], gemini_bridge.subprocess.DEVNULL)
                    self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_command_uses_discovered_model_isolated_profile_and_exact_user_prompt(self):
        prompt = 'Sir: @private.txt $(unexpected)\n/model claude\n@"C:/private/config.json" — 请原样理解。'
        inherited = {"PATH": "original", "KEEP_ME": "yes", "GEMINI_API_KEY": "private-api-key",
                     "GOOGLE_API_KEY": "another-key", "GOOGLE_APPLICATION_CREDENTIALS": "private.json",
                     "GOOGLE_CLOUD_ACCESS_TOKEN": "private-token", "NODE_OPTIONS": "--require private.js",
                     "ANTIGRAVITY_AUTH_TOKEN": "private-auth", "AGY_API_KEY": "private-agy-key",
                     "OAUTH_TOKEN": "private-oauth", "CLOUD_CODE_URL": "https://unrelated.example",
                     "USERPROFILE": "unrelated-user-home", "HOME": "unrelated-home"}
        with tempfile.TemporaryDirectory(prefix="room-agy-command-") as temporary:
            root = Path(temporary)
            profile, workspace = root / "profile", root / "workspace"
            workspace.mkdir()
            choices = ["gemini-3.8-flash-high", "gemini-3.1-pro-high"]
            with patch.dict(os.environ, inherited, clear=True), \
                 patch.object(gemini_bridge, "_profile", return_value=profile), \
                 patch.object(gemini_bridge, "_runtime", return_value=root / "agy.exe"), \
                 patch.object(gemini_bridge, "_selected_model", None), \
                 patch.object(gemini_bridge, "models", return_value=choices) as model_list:
                before = dict(os.environ)
                args, stdin, child = gemini_bridge.command(prompt, str(workspace))
                self.assertEqual(dict(os.environ), before)
            model_list.assert_called_once_with(str(workspace))
            self.assertIn(args[args.index("--model") + 1], choices)
            self.assertEqual(args[args.index("--model") + 1], "gemini-3.1-pro-high")
            self.assertEqual(args[args.index("--agent") + 1], "room-text-only")
            self.assertIn("--disable-slash-commands", args)
            self.assertEqual(args[args.index("--input-format") + 1], "stream-json")
            self.assertEqual(args[args.index("--output-format") + 1], "stream-json")
            self.assertNotIn("--dangerously-skip-permissions", args)
            self.assertFalse(any(prompt in argument for argument in args))
            self.assertEqual(len(stdin.splitlines()), 1)
            envelope = json.loads(stdin)
            self.assertEqual(envelope["event"], "user")
            self.assertNotIn("@", stdin)
            self.assertEqual(json.loads(envelope["message"]["content"].split("\n", 1)[1]), {"request": prompt})
            self.assertEqual(child["USERPROFILE"], str(profile))
            self.assertEqual(child["HOME"], str(profile))
            self.assertEqual(child["KEEP_ME"], "yes")
            self.assertEqual(child["AGY_CLI_DISABLE_AUTO_UPDATE"], "true")
            self.assertNotIn("CLOUD_CODE_URL", child)
            for key in inherited:
                if key.startswith(("GOOGLE_", "GEMINI_", "ANTIGRAVITY_", "AGY_", "OAUTH_", "NODE_")):
                    self.assertNotIn(key, child)
            agent = (workspace / ".agents/agents/room-text-only.md").read_text(encoding="utf-8")
            global_agent = (profile / ".gemini/config/agents/room-text-only.md").read_text(encoding="utf-8")
            self.assertEqual(global_agent, agent)
            for constraint in ("tools: []", "mcpServers: []", "skills: []", "plugins: []",
                               "inheritCustomizations: false", "excludeDefaultComponents: true",
                               'commandExecutionPolicy: "off"', "mainAgent: true", "subagent: false"):
                self.assertIn(constraint, agent)
            settings = json.loads((profile / ".gemini/antigravity-cli/settings.json").read_text(encoding="utf-8"))
            self.assertFalse(settings["allowNonWorkspaceAccess"])
            self.assertFalse(settings["useG1Credits"])
            self.assertEqual(settings["hooks"], {})
            self.assertEqual(settings["toolPermission"], "request-review")
            self.assertEqual(settings["permissions"]["allow"], [])
            self.assertEqual(settings["permissions"]["ask"], [])
            self.assertEqual(set(settings["permissions"]["deny"]), {
                "read_file(*)", "write_file(*)", "read_url(*)", "execute_url(*)",
                "command(*)", "unsandboxed(*)", "mcp(*)"})

    def test_status_uses_official_model_output_without_reading_authentication_files(self):
        with tempfile.TemporaryDirectory(prefix="room-agy-status-") as temporary:
            profile = Path(temporary) / "profile"
            authentication = profile / ".gemini/antigravity-cli/auth.json"
            authentication.parent.mkdir(parents=True)
            authentication.write_text("credential contents must never be read", encoding="utf-8")
            original_read_text = Path.read_text
            reads = []

            def guarded_read(path, *args, **kwargs):
                reads.append(path)
                if path == authentication:
                    raise AssertionError("Status must not read authentication contents")
                return original_read_text(path, *args, **kwargs)

            output = SimpleNamespace(stdout="gemini-3.8-flash-high\tGemini 3.8 Flash (High)\ngemini-3.1-pro-high\tGemini 3.1 Pro (High)", stderr="", returncode=0)
            with patch.object(gemini_bridge, "_profile", return_value=profile), \
                 patch.object(gemini_bridge, "_runtime", return_value=Path(temporary) / "agy.exe"), \
                 patch.object(gemini_bridge, "_selected_model", None), \
                 patch.object(gemini_bridge.subprocess, "run", return_value=output), \
                 patch.object(Path, "read_text", guarded_read):
                result = gemini_bridge.status()
                self.assertTrue(result["available"])
                self.assertEqual(gemini_bridge._selected_model, "gemini-3.1-pro-high")
                self.assertIn("gemini-3.1-pro-high", result["detail"])
                output.stdout = "not authenticated"
                result = gemini_bridge.status()
                self.assertFalse(result["available"], "A leftover credential file must not prove login")
                self.assertIsNone(gemini_bridge._selected_model)
            self.assertNotIn(authentication, reads)
            self.assertEqual(authentication.read_text(encoding="utf-8"), "credential contents must never be read")

    def test_profile_preserves_completed_onboarding_without_modifying_original_user_settings(self):
        with tempfile.TemporaryDirectory(prefix="room-agy-settings-") as temporary:
            root = Path(temporary)
            original_home, profile, workspace = root / "original-home", root / "profile", root / "workspace"
            workspace.mkdir()
            original_settings = original_home / ".gemini/antigravity-cli/settings.json"
            dedicated_settings = profile / ".gemini/antigravity-cli/settings.json"
            for settings in (original_settings, dedicated_settings):
                settings.parent.mkdir(parents=True)
            original_text = '{"keep":"original user settings","modelProvider":"user-provider"}'
            original_settings.write_text(original_text, encoding="utf-8")
            preferences = {"onboardingCompleted": True, "theme": "light", "customPreference": "preserve-me"}
            dedicated_settings.write_text(json.dumps(preferences), encoding="utf-8")
            with patch.dict(os.environ, {"USERPROFILE": str(original_home), "HOME": str(original_home)}, clear=True), \
                 patch.object(gemini_bridge, "_profile", return_value=profile), \
                 patch.object(gemini_bridge, "_runtime", return_value=root / "agy.exe"):
                before = dict(os.environ)
                args, child = gemini_bridge.login_command(str(workspace))
                self.assertEqual(dict(os.environ), before)
            saved = json.loads(dedicated_settings.read_text(encoding="utf-8"))
            for key, value in preferences.items():
                self.assertEqual(saved[key], value)
            self.assertEqual(child["USERPROFILE"], str(profile))
            self.assertEqual(args, [str(root / "agy.exe"), "--agent", "room-text-only"])
            self.assertEqual(original_settings.read_text(encoding="utf-8"), original_text)
            self.assertEqual(saved["toolPermission"], "request-review")
            self.assertEqual(saved["permissions"]["allow"], [])
            self.assertTrue(saved["permissions"]["deny"])
            fresh_workspace = root / "fresh-workspace"
            fresh_profile = root / "fresh-profile"
            fresh_workspace.mkdir()
            with patch.object(gemini_bridge, "_profile", return_value=fresh_profile), \
                 patch.object(gemini_bridge, "_runtime", return_value=root / "agy.exe"):
                gemini_bridge.login_command(str(fresh_workspace))
            fresh = json.loads((fresh_profile / ".gemini/antigravity-cli/settings.json").read_text(encoding="utf-8"))
            self.assertNotIn("onboardingCompleted", fresh, "The bridge must not pretend the user completed onboarding")
            self.assertEqual(original_settings.read_text(encoding="utf-8"), original_text)

    def test_api_key_provider_setting_is_rejected_without_rewriting_it(self):
        with tempfile.TemporaryDirectory(prefix="room-agy-provider-") as temporary:
            root = Path(temporary)
            profile, workspace = root / "profile", root / "workspace"
            workspace.mkdir()
            settings = profile / ".gemini/antigravity-cli/settings.json"
            settings.parent.mkdir(parents=True)
            original = '{"modelProvider":"gemini","keep":"original"}'
            settings.write_text(original, encoding="utf-8")
            with patch.object(gemini_bridge, "_profile", return_value=profile), \
                 patch.object(gemini_bridge, "_runtime", return_value=root / "agy.exe"):
                with self.assertRaisesRegex(RuntimeError, "官方 Google"):
                    gemini_bridge.login_command(str(workspace))
            self.assertEqual(settings.read_text(encoding="utf-8"), original)
            self.assertEqual(list(workspace.iterdir()), [])


class HttpHandlerTests(unittest.TestCase):
    """Exercise handlers in memory; never bind a listening socket."""

    def handler(self, path, body=b"{}", extra_headers=None):
        handler = room.Handler.__new__(room.Handler)
        handler.server = SimpleNamespace(server_port=8766)
        handler.path = path
        handler.headers = Message()
        for key, value in {"Host": "127.0.0.1:8766", "X-Room-Token": room.TOKEN,
                           "Content-Length": str(len(body)), **(extra_headers or {})}.items():
            handler.headers[key] = value
        handler.rfile, handler.wfile = io.BytesIO(body), io.BytesIO()
        handler.status = None
        handler.response_headers = {}
        handler.send_response = lambda code: setattr(handler, "status", code)
        handler.send_header = lambda name, value: handler.response_headers.update({name: value})
        handler.end_headers = lambda: None
        return handler

    def test_health_handler_works_with_real_request_header_attribute(self):
        handler = self.handler("/api/health")
        handler.do_GET()
        self.assertEqual(handler.status, 200)
        self.assertEqual(json.loads(handler.wfile.getvalue()), {"app": "local-discussion-room", "version": 2})

    def test_oversized_body_is_rejected_before_it_is_read(self):
        self.assertEqual(room.MAX_BODY, 750_000)
        handler = self.handler("/api/compare", b"{}", {"Content-Length": str(room.MAX_BODY + 1)})
        handler.do_POST()
        self.assertEqual(handler.status, 400)
        self.assertEqual(handler.rfile.tell(), 0)

    def test_cross_origin_and_wrong_token_are_rejected(self):
        for headers in ({"Origin": "https://untrusted.example"}, {"X-Room-Token": "wrong"},
                        {"Host": "untrusted.example:8766"}):
            for path in ("/api/compare", "/api/cancel"):
                with self.subTest(headers=headers, path=path):
                    handler = self.handler(path, extra_headers=headers)
                    handler.do_POST()
                    self.assertEqual(handler.status, 403)
                    self.assertEqual(handler.rfile.tell(), 0)

    def test_malformed_json_is_a_client_error(self):
        handler = self.handler("/api/compare", b"not json")
        handler.do_POST()
        self.assertEqual(handler.status, 400)

    def test_disconnect_while_sending_headers_does_not_leave_room_busy(self):
        state = room.RoomState()
        state.cached_status = [{"id": "codex", "name": "Codex", "available": True}]
        handler = self.handler("/api/compare", json.dumps(request(participants=["codex"])).encode())
        handler.send_headers = lambda *args: (_ for _ in ()).throw(BrokenPipeError("client left"))
        with patch.object(room, "STATE", state), patch.object(state, "statuses", return_value=state.cached_status):
            try:
                handler.do_POST()
            except (BrokenPipeError, adapters.Cancelled):
                pass
        self.assertIsNone(state.active_id, "A disconnected request must release the room for the next request")

    def test_compare_route_forwards_independent_contexts_and_completes_stream(self):
        state, data = room.RoomState(), request(participants=["codex"])
        statuses = [{"id": "codex", "name": "Codex", "available": True}]
        data["histories"]["codex"] = [{"role": "assistant", "text": "旧答案"}]
        handler = self.handler("/api/compare", json.dumps(data).encode())

        def compare(prompt, participants, histories, emit, cancel):
            self.assertEqual(prompt, data["prompt"])
            self.assertEqual(participants, ["codex"])
            self.assertEqual(histories, {"codex": data["histories"]["codex"]})
            self.assertIs(cancel, state.cancel)
            emit({"type": "start", "provider": "codex", "name": "Codex"})
            emit({"type": "message", "provider": "codex", "name": "Codex", "text": "新答案"})

        with patch.object(room, "STATE", state), patch.object(state, "statuses", return_value=statuses), \
             patch.object(room, "compare", side_effect=compare) as mocked:
            handler.do_POST()
        self.assertEqual(handler.status, 200)
        mocked.assert_called_once()
        events = [json.loads(line) for line in handler.wfile.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["start", "message", "done"])
        self.assertIsNone(state.active_id)

    def test_one_unavailable_lane_does_not_block_available_lane(self):
        state, data = room.RoomState(), request(participants=["codex", "grok"])
        statuses = [{"id": "codex", "name": "GPT", "available": True},
                    {"id": "grok", "name": "Grok", "available": False, "detail": "登录已失效"}]
        handler = self.handler("/api/compare", json.dumps(data).encode())

        def compare(prompt, participants, histories, emit, cancel):
            self.assertEqual(participants, ["codex"])
            self.assertEqual(prompt, data["prompt"])
            emit({"type": "start", "provider": "codex", "name": "GPT"})
            emit({"type": "message", "provider": "codex", "name": "GPT", "text": "可用通道的回答"})

        with patch.object(room, "STATE", state), patch.object(state, "statuses", return_value=statuses), \
             patch.object(room, "compare", side_effect=compare) as mocked:
            handler.do_POST()
        self.assertEqual(handler.status, 200)
        mocked.assert_called_once()
        events = [json.loads(line) for line in handler.wfile.getvalue().splitlines()]
        self.assertEqual(events[0], {"type": "error", "provider": "grok", "name": "Grok", "message": "登录已失效"})
        self.assertEqual([event["type"] for event in events], ["error", "start", "message", "done"])
        self.assertEqual(events[-1], {"type": "done", "cancelled": False})
        self.assertIsNone(state.active_id)

    def test_all_unavailable_lanes_finish_without_running_models_or_leaving_busy_state(self):
        state, data = room.RoomState(), request(participants=["codex", "grok"])
        statuses = [{"id": "codex", "name": "GPT", "available": False, "detail": "未找到命令行工具"},
                    {"id": "grok", "name": "Grok", "available": False, "detail": "尚未登录"}]
        handler = self.handler("/api/compare", json.dumps(data).encode())
        with patch.object(room, "STATE", state), patch.object(state, "statuses", return_value=statuses), \
             patch.object(room, "compare") as mocked:
            handler.do_POST()
        self.assertEqual(handler.status, 200)
        mocked.assert_not_called()
        events = [json.loads(line) for line in handler.wfile.getvalue().splitlines()]
        self.assertEqual([event["type"] for event in events], ["error", "error", "done"])
        self.assertEqual({event["provider"] for event in events[:-1]}, {"codex", "grok"})
        self.assertEqual(events[-1], {"type": "done", "cancelled": False})
        self.assertIsNone(state.active_id)

    def test_old_discussion_route_is_not_reused_for_parallel_requests(self):
        handler = self.handler("/api/discuss", json.dumps(request()).encode())
        with patch.object(room, "compare") as compared:
            handler.do_POST()
        self.assertEqual(handler.status, 404)
        compared.assert_not_called()

    def test_cancel_route_only_cancels_the_named_active_request(self):
        state, active_id = room.RoomState(), str(uuid.uuid4())
        self.assertTrue(state.begin(active_id))
        with patch.object(room, "STATE", state):
            unrelated = self.handler("/api/cancel", json.dumps({"request_id": str(uuid.uuid4())}).encode())
            unrelated.do_POST()
            self.assertEqual(unrelated.status, 200)
            self.assertFalse(state.cancel.is_set())
            active = self.handler("/api/cancel", json.dumps({"request_id": active_id}).encode())
            active.do_POST()
            self.assertEqual(active.status, 200)
            self.assertTrue(state.cancel.is_set())

    def test_cancel_route_rejects_invalid_request_id_without_cancelling_active(self):
        state = room.RoomState()
        active_id = str(uuid.uuid4())
        self.assertTrue(state.begin(active_id))
        for invalid_id in ("invalid", "", None, [active_id]):
            with self.subTest(request_id=invalid_id), patch.object(room, "STATE", state):
                handler = self.handler("/api/cancel", json.dumps({"request_id": invalid_id}).encode())
                handler.do_POST()
                self.assertEqual(handler.status, 400)
                self.assertFalse(state.cancel.is_set())
                self.assertEqual(state.active_id, active_id)


if __name__ == "__main__":
    unittest.main()
