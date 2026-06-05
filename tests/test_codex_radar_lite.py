import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from codex_radar_lite.collectors import extract_matching_signals, extract_statuspage_incidents
from codex_radar_lite.demo_alert import build_demo_state
from codex_radar_lite.feed import build_feed
from codex_radar_lite.models import RadarState, Signal
from codex_radar_lite.notifiers import send_dingtalk, should_push, signed_webhook
from codex_radar_lite.rules import evaluate
from codex_radar_lite.storage import load_previous_state, save_outputs, update_history


class CodexRadarLiteTest(unittest.TestCase):
    def make_signal(self, title):
        return Signal(
            source_id="test",
            source_name="Test Source",
            title=title,
            summary=title,
            url="https://example.com",
            observed_at="2026-06-05T00:00:00Z",
            weight=40,
            tags=["codex"],
        )

    def test_extract_matching_signals_keeps_relevant_lines(self):
        source = {
            "id": "status",
            "name": "Status",
            "url": "https://status.openai.com/history",
            "weight": 40,
            "keywords": ["codex", "rate limit"],
        }
        text = """
        Everything normal.
        Increased latency for Codex compaction for a subset of users.
        Rate limit has no relation here.
        """

        signals = extract_matching_signals(text, source)

        self.assertEqual(2, len(signals))
        self.assertEqual("Status", signals[0].source_name)
        self.assertIn("Codex compaction", signals[0].title)

    def test_extract_statuspage_incidents_reads_json_feed(self):
        payload = """
        {
          "incidents": [
            {
              "name": "Increased latency for Codex compaction",
              "status": "resolved",
              "updated_at": "2026-06-05T00:00:00Z",
              "shortlink": "https://stspg.io/example",
              "components": [{"name": "Codex"}],
              "incident_updates": [{"body": "All impacted services have now fully recovered."}]
            }
          ]
        }
        """
        source = {
            "id": "openai_status",
            "name": "OpenAI Status",
            "url": "https://status.openai.com/api/v2/incidents.json",
            "weight": 40,
            "keywords": ["codex", "recovered"],
        }

        signals = extract_statuspage_incidents(payload, source)

        self.assertEqual(1, len(signals))
        self.assertEqual("OpenAI Status", signals[0].source_name)
        self.assertIn("fully recovered", signals[0].summary)

    def test_open_signal_triggers_push_state(self):
        rules = {
            "high_probability_threshold": 60,
            "watch_threshold": 25,
            "cooldown_hours_after_closed": 24,
            "keywords": {
                "open": ["will reset"],
                "closed": ["fully recovered"],
                "codex": ["codex"],
                "limit": ["usage limits"],
                "incident": ["latency"],
            },
        }

        state = evaluate([self.make_signal("Codex usage limits will reset soon")], rules, [])

        self.assertEqual("open", state.status)
        self.assertEqual("push", state.alert_level)
        self.assertGreaterEqual(state.probability_24h, 60)

    def test_closed_signal_updates_history(self):
        rules = {
            "high_probability_threshold": 60,
            "watch_threshold": 25,
            "cooldown_hours_after_closed": 24,
            "keywords": {
                "open": ["will reset"],
                "closed": ["fully recovered"],
                "codex": ["codex"],
                "limit": ["usage limits"],
                "incident": ["latency", "recovered"],
            },
        }

        state = evaluate([self.make_signal("Codex usage limits fully recovered")], rules, [])
        history = update_history([], state)

        self.assertEqual("closed", state.status)
        self.assertEqual("closed", history[0]["status"])
        self.assertIsNotNone(history[0]["closed_at"])

    def test_codex_latency_recovered_without_limit_does_not_trigger_alert(self):
        rules = {
            "high_probability_threshold": 60,
            "watch_threshold": 25,
            "cooldown_hours_after_closed": 24,
            "keywords": {
                "open": ["will reset"],
                "closed": ["fully recovered"],
                "codex": ["codex"],
                "limit": ["usage limits"],
                "incident": ["latency", "recovered"],
            },
        }

        state = evaluate([self.make_signal("Codex compaction latency fully recovered")], rules, [])

        self.assertEqual("watch", state.status)
        self.assertEqual("silent", state.alert_level)

    def test_non_codex_recovered_incident_does_not_trigger_alert(self):
        rules = {
            "high_probability_threshold": 60,
            "watch_threshold": 25,
            "cooldown_hours_after_closed": 24,
            "keywords": {
                "open": ["will reset"],
                "closed": ["fully recovered"],
                "codex": ["codex"],
                "limit": ["usage limits"],
                "incident": ["latency", "recovered"],
            },
        }

        state = evaluate([self.make_signal("Image API requests have now fully recovered")], rules, [])

        self.assertEqual("normal", state.status)
        self.assertEqual("silent", state.alert_level)

    def test_should_push_only_for_important_changes(self):
        previous = RadarState(
            status="watch",
            probability_24h=30,
            probability_48h=40,
            reason="watch",
            checked_at="2026-06-05T00:00:00Z",
            signals=[],
            alert_level="silent",
        )
        current = RadarState(
            status="high_probability",
            probability_24h=70,
            probability_48h=80,
            reason="high",
            checked_at="2026-06-05T01:00:00Z",
            signals=[],
            alert_level="push",
        )

        self.assertTrue(should_push(previous, current))
        self.assertFalse(should_push(current, current))

    def test_signed_webhook_does_not_change_without_secret(self):
        webhook = "https://oapi.dingtalk.com/robot/send"

        self.assertEqual(webhook, signed_webhook(webhook, None))

    def test_storage_roundtrip_and_feed(self):
        state = RadarState(
            status="normal",
            probability_24h=5,
            probability_48h=13,
            reason="ok",
            checked_at="2026-06-05T00:00:00Z",
            signals=[],
            alert_level="silent",
        )
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            save_outputs(data_dir, state, [])
            loaded = load_previous_state(data_dir)

        self.assertIsNotNone(loaded)
        self.assertEqual("normal", loaded.status)
        self.assertIn("Codex Radar Lite", build_feed(state))

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_dingtalk_webhook_is_safe(self):
        state = RadarState(
            status="open",
            probability_24h=90,
            probability_48h=95,
            reason="open",
            checked_at="2026-06-05T00:00:00Z",
            signals=[],
            alert_level="push",
        )

        self.assertEqual("skipped:no_webhook", send_dingtalk(state))

    @patch.dict(os.environ, {"DINGTALK_WEBHOOK": "https://oapi.dingtalk.com/robot/send"}, clear=True)
    @patch("codex_radar_lite.notifiers.requests.post")
    def test_dingtalk_rejection_raises_error(self, post):
        response = Mock()
        response.json.return_value = {"errcode": 310000, "errmsg": "keywords not in content"}
        post.return_value = response
        state = RadarState(
            status="open",
            probability_24h=90,
            probability_48h=95,
            reason="open",
            checked_at="2026-06-05T00:00:00Z",
            signals=[],
            alert_level="push",
        )

        with self.assertRaises(RuntimeError):
            send_dingtalk(state)

    def test_demo_alert_looks_like_real_high_probability_window(self):
        state = build_demo_state()

        self.assertEqual("high_probability", state.status)
        self.assertEqual("push", state.alert_level)
        self.assertGreaterEqual(state.probability_24h, 60)
        self.assertIn("Codex", state.reason)
        self.assertGreaterEqual(len(state.signals), 2)


if __name__ == "__main__":
    unittest.main()
