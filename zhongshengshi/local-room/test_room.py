"""Offline checks: no model calls, listening sockets, credentials or real CLI runs."""
from __future__ import annotations

from email.message import Message
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import adapters
import server as room


def request(**changes):
    value = {
        "request_id": str(uuid.uuid4()),
        "participants": ["codex", "claude", "grok"],
        "rounds": 1,
        "mode": "discuss",
        "messages": [{"role": "user", "speaker": "Sir", "text": "怎样让讨论更有用？"}],
    }
    value.update(changes)
    return value


def shared_history(prompt):
    return json.loads(prompt.split("共享聊天记录：\n", 1)[1].rsplit("\n请直接给出", 1)[0])


class RequestTests(unittest.TestCase):
    def test_valid_request_keeps_all_history(self):
        data = request()
        data["messages"].append({"role": "assistant", "speaker": "Grok", "text": "已有观点"})
        rid, history, participants, rounds, mode = room.validate_request(data)
        self.assertEqual(rid, data["request_id"])
        self.assertEqual(history, data["messages"])
        self.assertIsNot(history[0], data["messages"][0])
        self.assertEqual((participants, rounds, mode), (data["participants"], 1, "discuss"))

    def test_rejects_invalid_controls(self):
        cases = [
            {"request_id": "not-an-id"}, {"request_id": None},
            {"participants": []}, {"participants": ["codex", "codex"]},
            {"participants": ["unknown"]}, {"participants": [{"codex": True}]},
            {"rounds": True}, {"rounds": 0}, {"rounds": 4}, {"rounds": "2"},
            {"mode": "anything"}, {"mode": "summary"},
        ]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                room.validate_request(request(**change))

    def test_rejects_missing_malformed_or_forged_messages(self):
        cases = [[], ["text"], [{"role": "system", "speaker": "Sir", "text": "x"}],
                 [{"role": "user", "speaker": "Claude", "text": "x"}],
                 [{"role": "assistant", "speaker": "Sir", "text": "x"}],
                 [{"role": "user", "speaker": "Sir", "text": "  "}],
                 [{"role": "user", "speaker": "Sir", "text": None}],
                 [{"role": "assistant", "speaker": "Claude", "text": "no user question"}]]
        for messages in cases:
            with self.subTest(messages=messages), self.assertRaises(ValueError):
                room.validate_request(request(messages=messages))

    def test_context_and_message_count_boundaries(self):
        msg = {"role": "user", "speaker": "Sir", "text": "字" * room.MAX_CONTEXT}
        self.assertEqual(room.validate_request(request(messages=[msg]))[1][0]["text"], msg["text"])
        with self.assertRaises(ValueError):
            room.validate_request(request(messages=[dict(msg, text=msg["text"] + "字")]))
        tiny = dict(msg, text="字")
        self.assertEqual(len(room.validate_request(request(messages=[tiny] * 200))[1]), 200)
        with self.assertRaises(ValueError):
            room.validate_request(request(messages=[tiny] * 201))


class DiscussionTests(unittest.TestCase):
    def test_each_next_speaker_sees_all_previous_successes(self):
        initial = request()["messages"]
        calls, events = [], []

        def runner(provider, prompt, emit, cancel):
            calls.append((provider, shared_history(prompt)))
            return f"{provider} 发言 {len(calls)}"

        room.discuss(initial, ["codex", "claude", "grok"], 2, "discuss", events.append,
                     threading.Event(), runner=runner)
        self.assertEqual([p for p, _ in calls], ["codex", "claude", "grok"] * 2)
        for index, (_, history) in enumerate(calls):
            self.assertEqual(len(history), 1 + index)
            if index:
                self.assertEqual(history[-1]["text"], f"{calls[index - 1][0]} 发言 {index}")
        self.assertEqual(initial, request()["messages"], "Discussion must not mutate caller history")
        self.assertEqual(len([e for e in events if e["type"] == "message"]), 6)

    def test_summary_runs_once_even_with_multiple_rounds_requested(self):
        calls = []

        def runner(provider, prompt, emit, cancel):
            calls.append(prompt)
            return "共识、分歧、下一步"

        room.discuss(request()["messages"], ["claude"], 3, "summary", lambda _: None,
                     threading.Event(), runner=runner)
        self.assertEqual(len(calls), 1)
        self.assertIn("请总结目前的共识、分歧和下一步", calls[0])

    def test_failed_participant_does_not_poison_shared_history_or_stop_others(self):
        calls, events = [], []

        def runner(provider, prompt, emit, cancel):
            calls.append((provider, shared_history(prompt)))
            if provider == "claude":
                emit({"type": "delta", "text": "未完成的文本"})
                raise RuntimeError("temporary failure")
            return f"{provider} 成功"

        room.discuss(request()["messages"], ["codex", "claude", "grok"], 1, "discuss",
                     events.append, threading.Event(), runner=runner)
        self.assertEqual([p for p, _ in calls], ["codex", "claude", "grok"])
        self.assertEqual([m["speaker"] for m in calls[2][1]], ["Sir", "Codex"])
        self.assertEqual([e["provider"] for e in events if e["type"] == "error"], ["claude"])

    def test_cancel_during_reply_never_calls_next_participant_or_accepts_reply(self):
        cancel, calls, events = threading.Event(), [], []

        def runner(provider, prompt, emit, stopped):
            calls.append(provider)
            stopped.set()
            return "cancelled partial answer"

        room.discuss(request()["messages"], ["codex", "grok"], 3, "discuss", events.append,
                     cancel, runner=runner)
        self.assertEqual(calls, ["codex"])
        self.assertFalse(any(e["type"] == "message" for e in events))

    def test_cancelled_exception_stops_sequence(self):
        calls = []

        def runner(provider, *args):
            calls.append(provider)
            raise adapters.Cancelled()

        room.discuss(request()["messages"], ["grok", "codex"], 1, "discuss", lambda _: None,
                     threading.Event(), runner=runner)
        self.assertEqual(calls, ["grok"])

    def test_generated_history_limit_prevents_further_calls(self):
        calls, events = [], []

        def runner(provider, *args):
            calls.append(provider)
            return "字" * room.MAX_CONTEXT

        room.discuss(request()["messages"], ["codex", "claude"], 1, "discuss", events.append,
                     threading.Event(), runner=runner)
        self.assertEqual(calls, ["codex"])
        self.assertTrue(any(e["type"] == "error" for e in events))


class CancellationStateTests(unittest.TestCase):
    def test_cancel_before_begin_prevents_any_cli_call(self):
        state, events, calls = room.RoomState(), [], []
        request_id = str(uuid.uuid4())
        state.cancel_request(request_id)
        self.assertTrue(state.begin(request_id))

        def runner(provider, *args):
            calls.append(provider)
            return "must never be generated"

        room.discuss(request()["messages"], ["codex", "grok"], 3, "discuss",
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

        room.discuss(request()["messages"], ["codex", "grok"], 1, "discuss",
                     lambda _: None, state.cancel, runner=runner)
        self.assertFalse(state.cancel.is_set())
        self.assertEqual(calls, ["codex", "grok"])

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
        self.assertEqual(json.loads(handler.wfile.getvalue())["app"], "local-discussion-room")

    def test_oversized_body_is_rejected_before_it_is_read(self):
        handler = self.handler("/api/discuss", b"{}", {"Content-Length": str(room.MAX_BODY + 1)})
        handler.do_POST()
        self.assertEqual(handler.status, 400)
        self.assertEqual(handler.rfile.tell(), 0)

    def test_cross_origin_and_wrong_token_are_rejected(self):
        for headers in ({"Origin": "https://untrusted.example"}, {"X-Room-Token": "wrong"},
                        {"Host": "untrusted.example:8766"}):
            with self.subTest(headers=headers):
                handler = self.handler("/api/discuss", extra_headers=headers)
                handler.do_POST()
                self.assertEqual(handler.status, 403)

    def test_malformed_json_is_a_client_error(self):
        handler = self.handler("/api/discuss", b"not json")
        handler.do_POST()
        self.assertEqual(handler.status, 400)

    def test_disconnect_while_sending_headers_does_not_leave_room_busy(self):
        state = room.RoomState()
        state.cached_status = [{"id": "codex", "name": "Codex", "available": True}]
        handler = self.handler("/api/discuss", json.dumps(request(participants=["codex"])).encode())
        handler.send_headers = lambda *args: (_ for _ in ()).throw(BrokenPipeError("client left"))
        with patch.object(room, "STATE", state), patch.object(state, "statuses", return_value=state.cached_status):
            try:
                handler.do_POST()
            except (BrokenPipeError, adapters.Cancelled):
                pass
        self.assertIsNone(state.active_id, "A disconnected request must release the room for the next request")

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
