"""Daily delivery correctness without source requests or private repository writes."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from utils import newspaper_daily as daily


NOW = datetime(2026, 10, 5, 9, 1, tzinfo=daily.SHANGHAI)
ENV = {"GITHUB_BACKUP_TOKEN": "test-only-token"}


def item(sid="media_solidot", *, policy=None, url=None):
    family = daily._family(sid)
    url = url or ("https://www.solidot.org/story?sid=82645" if family == "public_media" else
                  "https://openai.com/index/test-announcement/" if family == "ai_official" else
                  "https://www.chinanews.com.cn/gn/2026/10-05/10999001.shtml")
    prefix = {"public_media": "media_", "ai_official": "ai_official_", "public_news": "news_"}[family]
    result = {"id": prefix + hashlib.sha256(url.encode()).hexdigest()[:24], "source_id": sid,
              "source": daily.SOURCE_MAP[sid].name, "source_family": family, "title": "新闻标题与完整来源",
              "url": url, "summary": "公开订阅摘要", "published_at": NOW.isoformat(),
              "group": "科技与科学", "category": "科学前沿", "available": False,
              "feed_paragraphs": ["正文不得进入快照"], "content_origin": "feed_full"}
    if policy is not None:
        result["cache_policy"] = policy
    return result


def feed(rows=None, *, control="", policy=None, failed=False):
    rows = [item()] if rows is None else rows
    ids = list(dict.fromkeys(row["source_id"] for row in rows)) or ["media_solidot"]
    result = {"articles": rows, "sources": [
        {"id": sid, "name": daily.SOURCE_MAP[sid].name, "status": "error" if failed else "ok",
         "count": sum(row["source_id"] == sid for row in rows), "checked_at": NOW.isoformat(),
         "cache_control": control, "error": "error" if failed else ""} for sid in ids]}
    if policy is not None:
        result["cache_policy"] = policy
    return result


def snapshot(at=NOW, *, source_feed=None):
    if source_feed is None:
        source_feed = feed()
        for row in source_feed["articles"]:
            row["published_at"] = at.isoformat()
        for state in source_feed["sources"]:
            state["checked_at"] = at.isoformat()
    with patch.object(daily.base, "load_newspaper_feed", return_value={"articles": [], "sources": []}), \
         patch.object(daily.ai, "load_ai_official_feed", return_value={"articles": [], "sources": []}), \
         patch.object(daily.media, "load_extended_news_feed", return_value=source_feed):
        return daily.build_daily_snapshot(now=at)


class SnapshotTest(unittest.TestCase):
    def test_interview_snapshot_keeps_column_and_on_demand_reading(self):
        row = item("media_chinawriter_interviews",
                   url="https://www.chinawriter.com.cn/n1/2026/1005/c405057-40808385.html")
        row.update(group="人物与访谈", category="访谈与对话", kind="访谈",
                   summary_only=False, content_origin="source_summary")
        result = daily.validate_daily_snapshot(snapshot(source_feed=feed([row])))
        assert result["articles"][0]["category"] == "访谈与对话"
        assert result["articles"][0]["summary_only"] is False
        assert "feed_paragraphs" not in result["articles"][0]

    def test_interviews_cannot_use_discovery_time_or_survive_the_week_in_a_cached_edition(self):
        row = item("media_lifeweek_interviews", url="https://www.lifeweek.com.cn/article/273320")
        row.update(group="人物与访谈", category="访谈与对话", kind="访谈",
                   published_at=(NOW - timedelta(days=6, hours=23)).isoformat(),
                   time_basis="published")
        payload = snapshot(source_feed=feed([row, item()]))
        result = daily.feed_from_daily_snapshot(payload, now=NOW + timedelta(hours=2))
        assert [article["source_id"] for article in result["articles"]] == ["media_solidot"]
        assert payload["article_count"] == 2
        for published in ("", (NOW - timedelta(days=8)).isoformat()):
            invalid = {**row, "published_at": published, "discovered_at": NOW.isoformat()}
            assert snapshot(source_feed=feed([invalid]))["articles"] == []

    def test_duplicate_in_book_and_interview_sources_keeps_column_and_correct_counts(self):
        url = "https://www.chinawriter.com.cn/n1/2026/1005/c405057-40808385.html"
        book, interview = item("chinawriter_books", url=url), item("media_chinawriter_interviews", url=url)
        book.update(category="新书与综合书单", group="阅读与文学")
        interview.update(category="访谈与对话", group="人物与访谈", summary_only=False)
        with patch.object(daily.base, "load_newspaper_feed", return_value=feed([book])), \
             patch.object(daily.ai, "load_ai_official_feed", return_value={"articles": [], "sources": []}), \
             patch.object(daily.media, "load_extended_news_feed", return_value=feed([interview])):
            result = daily.validate_daily_snapshot(daily.build_daily_snapshot(now=NOW))
        assert result["article_count"] == 1
        assert result["articles"][0]["source_id"] == "media_chinawriter_interviews"
        assert {s["id"]: s["count"] for s in result["sources"]} == {
            "chinawriter_books": 0, "media_chinawriter_interviews": 1}

    def test_list_only_preserves_live_identity_and_provenance(self):
        result = daily.validate_daily_snapshot(snapshot())
        row = result["articles"][0]
        self.assertNotIn("feed_paragraphs", row)
        self.assertEqual(item()["id"], row["id"])
        self.assertEqual("Solidot", row["source"])
        self.assertTrue(row["summary_only"])
        self.assertEqual("source_summary", row["content_origin"])
        self.assertEqual(1, result["sources"][0]["count"])

    def test_each_cache_restriction_and_unknown_are_excluded(self):
        for control in ("private", "no-store", "no-cache", "max-age=60", "s-maxage=86400",
                        "must-revalidate", "proxy-revalidate"):
            with self.subTest(control=control):
                result = snapshot(source_feed=feed(control=control))
                self.assertEqual([], result["articles"])
                self.assertEqual(1, result["sources"][0]["excluded_count"])
        unknown = feed()
        del unknown["sources"][0]["cache_control"]
        self.assertEqual([], snapshot(source_feed=unknown)["articles"])
        for policy in ({"store": False, "reuse": False}, {"store": True, "reuse": False},
                       {"store": True, "reuse": True, "max_age_seconds": 60}):
            with self.subTest(policy=policy):
                self.assertEqual([], snapshot(source_feed=feed([item(policy=policy)]))["articles"])

    def test_source_policy_is_independent_of_aggregate(self):
        result = snapshot(source_feed=feed(policy={"store": False, "reuse": False, "max_age_seconds": 0}))
        self.assertEqual(1, result["article_count"])
        result = snapshot(source_feed=feed([item(policy={"store": True, "reuse": True, "max_age_seconds": None})]))
        self.assertEqual(1, result["article_count"])

    def test_policy_unknown_not_repaired_by_aggregate(self):
        source_feed = feed(policy={"store": True, "reuse": True})
        del source_feed["sources"][0]["cache_control"]
        self.assertEqual([], snapshot(source_feed=source_feed)["articles"])

    def test_invalid_ids_urls_future_dates_and_duplicates(self):
        bad = item()
        bad["id"] = "unverified"
        self.assertEqual([], snapshot(source_feed=feed([bad]))["articles"])
        for url in ("https://evil.test/a", "https://www.solidot.org.evil.test/a", "https://user@www.solidot.org/a"):
            with self.subTest(url=url):
                self.assertEqual([], snapshot(source_feed=feed([item(url=url)]))["articles"])
        bad = item()
        bad["published_at"] = (NOW + timedelta(days=3)).isoformat()
        self.assertEqual([], snapshot(source_feed=feed([bad]))["articles"])
        result = daily.validate_daily_snapshot(snapshot(source_feed=feed([item(), item()])))
        self.assertEqual(1, result["article_count"])

    def test_validation_rejects_body_counts_bad_dates_and_forged_urls(self):
        for change in (lambda p: p["articles"][0].update(feed_paragraphs=["body"]),
                       lambda p: p.update(article_count=22),
                       lambda p: p.update(completed_at="2026-10-05T09:00:00"),
                       lambda p: p["articles"][0].update(url="https://evil.test"),
                       lambda p: p["sources"][0].update(count=22),
                       lambda p: p.update(expires_at=(NOW + timedelta(days=5)).isoformat())):
            with self.subTest(change=change):
                payload = snapshot()
                change(payload)
                with self.assertRaises(ValueError):
                    daily.validate_daily_snapshot(payload)

    def test_readable_feed_uses_real_edition_and_expires(self):
        payload = snapshot()
        result = daily.feed_from_daily_snapshot(payload, now=NOW + timedelta(hours=25))
        self.assertEqual("daily", result["delivery"])
        self.assertEqual("2026-10-05", result["edition_date"])
        self.assertEqual(NOW.isoformat(), result["fetched_at"])
        self.assertIsNone(daily.feed_from_daily_snapshot(payload, now=NOW + timedelta(hours=48)))
        self.assertIsNone(daily.feed_from_daily_snapshot(payload, now=NOW - timedelta(hours=1)))
        self.assertIsNone(daily.feed_from_daily_snapshot("bad json", now=NOW))

    def test_beijing_date_uses_offset_not_machine_timezone(self):
        utc = datetime(2026, 10, 4, 16, 1, tzinfo=timezone.utc)
        source_feed = feed()
        source_feed["articles"][0]["published_at"] = utc.isoformat()
        source_feed["sources"][0]["checked_at"] = utc.isoformat()
        result = daily.validate_daily_snapshot(snapshot(utc, source_feed=source_feed))
        self.assertEqual("2026-10-05", result["edition_date"])

    def test_source_failure_is_partial_and_has_actual_checked_time(self):
        with patch.object(daily.base, "load_newspaper_feed", side_effect=RuntimeError("secret-token")), \
             patch.object(daily.ai, "load_ai_official_feed", return_value={"articles": [], "sources": []}), \
             patch.object(daily.media, "load_extended_news_feed", return_value=feed()):
            result = daily.validate_daily_snapshot(daily.build_daily_snapshot(now=NOW))
        self.assertEqual("partial", result["status"])
        self.assertTrue(result["errors"])
        self.assertNotIn("secret-token", json.dumps(result))
        self.assertTrue(all(state["checked_at"] == NOW.isoformat() for state in result["sources"]))

    def test_oversized_edition_trims_oldest_rows_and_reconciles_counts(self):
        rows = [item(url="https://www.solidot.org/story?sid=" + str(82000 + index)) for index in range(30)]
        for index, row in enumerate(rows):
            row["summary"] = "摘要" * 700
            row["published_at"] = (NOW - timedelta(minutes=index)).isoformat()
        with patch.object(daily, "MAX_CONTENT_BYTES", 15000):
            result = daily.validate_daily_snapshot(snapshot(source_feed=feed(rows)))
            self.assertLessEqual(len(daily._snapshot_text(result).encode("utf-8")), 15000)
        self.assertGreater(result["article_count"], 0)
        self.assertLess(result["article_count"], 30)
        self.assertEqual(rows[0]["id"], result["articles"][0]["id"])
        self.assertEqual(30, result["sources"][0]["count"] + result["sources"][0]["excluded_count"])
        self.assertTrue(all(len(row["summary"]) <= 500 for row in result["articles"]))

    def test_dict_payload_size_is_checked_before_publish(self):
        payload = snapshot()
        payload["articles"][0]["summary"] = "字" * 400000
        with self.assertRaises(ValueError):
            daily.validate_daily_snapshot(payload)


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        for patcher in (patch.object(daily, "LOCAL_DIR", Path(self.directory.name)), patch.object(daily, "_now", return_value=NOW),
                        patch.object(daily, "_verify_private_repository")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.payload = snapshot()

    def test_dry_run_never_reads_or_writes_remote(self):
        with patch.object(daily, "build_daily_snapshot", return_value=self.payload), \
             patch.object(daily.sync, "read_file_from_github") as read, patch.object(daily.sync, "sync_file_to_github") as write:
            result = daily.run_daily(environ={})
        self.assertTrue(result["ok"])
        self.assertEqual("dry_run", result["status"])
        read.assert_not_called()
        write.assert_not_called()
        self.assertFalse((daily.LOCAL_DIR / "last_success.json").exists())
        self.assertEqual(result, json.loads((daily.LOCAL_DIR / "last_run.json").read_text(encoding="utf-8")))

    def test_first_publish_expected_absence_and_readback(self):
        remote = {"ok": True, "sha": "newsha", "content": json.dumps(self.payload)}
        with patch.object(daily, "build_daily_snapshot", return_value=self.payload), \
             patch.object(daily.sync, "read_file_from_github", side_effect=[{"ok": False, "reason": "missing_remote_file"}, remote]), \
             patch.object(daily.sync, "sync_file_to_github", return_value={"ok": True, "sha": "newsha"}) as write:
            result = daily.run_daily(dry_run=False, environ=ENV)
        self.assertTrue(result["ok"])
        self.assertEqual("published", result["status"])
        self.assertIsNone(write.call_args.kwargs["expected_sha"])
        self.assertEqual(daily.SNAPSHOT_PATH, write.call_args.args[1])
        self.assertEqual(self.payload, json.loads((daily.LOCAL_DIR / "last_success.json").read_text(encoding="utf-8")))

    def test_same_beijing_cycle_is_idempotent_without_new_fetch(self):
        previous = snapshot(NOW - timedelta(minutes=1))
        with patch.object(daily.sync, "read_file_from_github", return_value={"ok": True, "sha": "old", "content": json.dumps(previous)}), \
             patch.object(daily, "build_daily_snapshot") as build, patch.object(daily.sync, "sync_file_to_github") as write:
            result = daily.run_daily(dry_run=False, environ=ENV)
        self.assertEqual("already_published", result["status"])
        self.assertEqual(len(previous["sources"]), result["source_count"])
        self.assertEqual(len(previous["errors"]), result["source_errors"])
        self.assertEqual(previous["status"], result["snapshot_status"])
        build.assert_not_called()
        write.assert_not_called()
        self.assertEqual(previous["completed_at"], result["snapshot_completed_at"])

    def test_pre_nine_installation_check_does_not_skip_scheduled_run(self):
        previous = snapshot(NOW.replace(hour=8, minute=30))
        with patch.object(daily.sync, "read_file_from_github", side_effect=[
             {"ok": True, "sha": "old", "content": json.dumps(previous)},
             {"ok": True, "sha": "new", "content": json.dumps(self.payload)}]), \
             patch.object(daily, "build_daily_snapshot", return_value=self.payload) as build, \
             patch.object(daily.sync, "sync_file_to_github", return_value={"ok": True, "sha": "new"}) as write:
            result = daily.run_daily(dry_run=False, environ=ENV)
        self.assertEqual("published", result["status"])
        self.assertEqual("2026-10-05T09:00:00+08:00", result["cycle_start_at"])
        build.assert_called_once()
        self.assertEqual("old", write.call_args.kwargs["expected_sha"])

    def test_nine_one_then_nine_ten_skips_in_beijing_even_with_utc_clock(self):
        at = NOW.replace(minute=10).astimezone(timezone.utc)
        with patch.object(daily, "_now", return_value=at), \
             patch.object(daily.sync, "read_file_from_github", return_value={"ok": True, "sha": "s", "content": json.dumps(self.payload)}), \
             patch.object(daily, "build_daily_snapshot") as build, patch.object(daily.sync, "sync_file_to_github") as write:
            result = daily.run_daily(dry_run=False, environ=ENV)
        self.assertEqual("already_published", result["status"])
        self.assertEqual("2026-10-05T09:00:00+08:00", result["cycle_start_at"])
        self.assertEqual("same_beijing_cycle", result["reason"])
        build.assert_not_called()
        write.assert_not_called()

    def test_before_nine_previous_day_cycle_remains_idempotent(self):
        previous = snapshot((NOW - timedelta(days=1)).replace(minute=10))
        at = NOW.replace(hour=8, minute=30).astimezone(timezone.utc)
        with patch.object(daily, "_now", return_value=at), \
             patch.object(daily.sync, "read_file_from_github", return_value={"ok": True, "sha": "s", "content": json.dumps(previous)}), \
             patch.object(daily, "build_daily_snapshot") as build:
            result = daily.run_daily(dry_run=False, environ=ENV)
        self.assertEqual("already_published", result["status"])
        self.assertEqual("2026-10-04T09:00:00+08:00", result["cycle_start_at"])
        self.assertEqual(previous["edition_date"], result["edition_date"])
        build.assert_not_called()

    def test_force_still_passes_observed_sha(self):
        previous = snapshot(NOW - timedelta(minutes=1))
        with patch.object(daily.sync, "read_file_from_github", side_effect=[
             {"ok": True, "sha": "old", "content": json.dumps(previous)},
             {"ok": True, "sha": "new", "content": json.dumps(self.payload)}]), \
             patch.object(daily, "build_daily_snapshot", return_value=self.payload), \
             patch.object(daily.sync, "sync_file_to_github", return_value={"ok": True, "sha": "new"}) as write:
            self.assertTrue(daily.run_daily(dry_run=False, environ=ENV, force=True)["ok"])
        self.assertEqual("old", write.call_args.kwargs["expected_sha"])

    def test_empty_failure_keeps_previous_and_never_writes(self):
        marker = daily.LOCAL_DIR / "last_success.json"
        marker.write_text("previous", encoding="utf-8")
        empty = snapshot(source_feed=feed(rows=[]))
        with patch.object(daily.sync, "read_file_from_github", return_value={"ok": False, "reason": "missing_remote_file"}), \
             patch.object(daily, "build_daily_snapshot", return_value=empty), \
             patch.object(daily.sync, "sync_file_to_github") as write:
            result = daily.run_daily(dry_run=False, environ=ENV)
        self.assertFalse(result["ok"])
        self.assertEqual("no_eligible_articles", result["reason"])
        self.assertEqual("previous", marker.read_text(encoding="utf-8"))
        write.assert_not_called()

    def test_bad_or_newer_remote_stops_before_fetch(self):
        for content in ("bad", json.dumps(snapshot(NOW + timedelta(minutes=1)))):
            with self.subTest(content=content[:10]), \
                 patch.object(daily.sync, "read_file_from_github", return_value={"ok": True, "sha": "s", "content": content}), \
                 patch.object(daily, "build_daily_snapshot") as build, patch.object(daily.sync, "sync_file_to_github") as write:
                self.assertFalse(daily.run_daily(dry_run=False, environ=ENV, force=True)["ok"])
                build.assert_not_called()
                write.assert_not_called()

    def test_conflict_or_failed_readback_is_not_success(self):
        for outcome in (RuntimeError("409 bearer SECRET"), {"ok": True, "sha": "new"}):
            with self.subTest(outcome=str(outcome)), \
                 patch.object(daily, "build_daily_snapshot", return_value=self.payload), \
                 patch.object(daily.sync, "read_file_from_github", side_effect=[{"ok": False, "reason": "missing_remote_file"},
                                                                                {"ok": True, "sha": "other", "content": json.dumps(self.payload)}]), \
                 patch.object(daily.sync, "sync_file_to_github", side_effect=outcome if isinstance(outcome, Exception) else None,
                              return_value=outcome if isinstance(outcome, dict) else None):
                result = daily.run_daily(dry_run=False, environ=ENV)
                self.assertFalse(result["ok"])
                self.assertNotIn("SECRET", json.dumps(result))
                self.assertFalse((daily.LOCAL_DIR / "last_success.json").exists())

    def test_wrong_repo_branch_or_missing_credentials_never_access_remote(self):
        for env in ({}, {**ENV, "GITHUB_BACKUP_REPO": "yaoy2/yao_1"}, {**ENV, "GITHUB_BACKUP_BRANCH": "other"}):
            with self.subTest(env=env), patch.object(daily.sync, "read_file_from_github") as read:
                self.assertFalse(daily.run_daily(dry_run=False, environ=env)["ok"])
                read.assert_not_called()

    def test_lock_blocks_overlap_and_stale_file_is_recoverable(self):
        with daily._run_lock(daily.LOCAL_DIR), patch.object(daily, "build_daily_snapshot") as build:
            result = daily.run_daily(environ={})
            self.assertEqual("daily_locked", result["reason"])
            build.assert_not_called()
        with patch.object(daily, "build_daily_snapshot", return_value=self.payload):
            self.assertTrue(daily.run_daily(environ={})["ok"])

    def test_atomic_replace_failure_preserves_previous_file_and_cleans_temp(self):
        target = daily.LOCAL_DIR / "last_success.json"
        target.write_text("previous", encoding="utf-8")
        with patch.object(daily.os, "replace", side_effect=OSError("blocked")), self.assertRaises(OSError):
            daily._atomic_json(target, self.payload)
        self.assertEqual("previous", target.read_text(encoding="utf-8"))
        self.assertEqual([], list(daily.LOCAL_DIR.glob("*.tmp")))

    def test_reader_returns_none_for_absent_bad_or_expired_remote(self):
        for remote in ({"ok": False}, {"ok": True, "content": "bad"},
                       {"ok": True, "content": json.dumps(snapshot(NOW - timedelta(days=3)))}):
            with patch.object(daily.sync, "read_file_from_github", return_value=remote):
                self.assertIsNone(daily.read_daily_feed(environ=ENV))
        with patch.object(daily.sync, "read_file_from_github", return_value={"ok": True, "content": json.dumps(self.payload)}):
            self.assertEqual("daily", daily.read_daily_feed(environ=ENV)["delivery"])


class PrivateTargetAndCliTest(unittest.TestCase):
    def test_repository_must_be_actual_private_and_exact_target(self):
        for metadata in ({"private": False, "full_name": daily.PRIVATE_REPO},
                         {"private": True, "full_name": "other/repo"}):
            session = Mock()
            session.get.return_value.status_code = 200
            session.get.return_value.json.return_value = metadata
            with patch.object(daily.sync, "_session", return_value=session), self.assertRaises(ValueError):
                daily._verify_private_repository({"token": "test"})

    def test_cli_defaults_dry_and_publish_explicit_exit_status(self):
        path = daily.ROOT / "scripts" / "newspaper_daily.py"
        spec = importlib.util.spec_from_file_location("newspaper_daily_cli_test", path)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with patch.object(cli, "_local_secrets", return_value={}), patch.object(cli, "run_daily", return_value={"ok": True}) as run, patch("builtins.print"):
            self.assertEqual(0, cli.main([]))
            self.assertTrue(run.call_args.kwargs["dry_run"])
            self.assertEqual(0, cli.main(["--publish", "--force"]))
            self.assertFalse(run.call_args.kwargs["dry_run"])
            self.assertTrue(run.call_args.kwargs["force"])
        with patch.object(cli, "_local_secrets", return_value={}), patch.object(cli, "run_daily", return_value={"ok": False}), patch("builtins.print"):
            self.assertEqual(1, cli.main([]))

    def test_import_has_no_streamlit_dependency(self):
        process = subprocess.run([sys.executable, "-c", "import sys; import utils.newspaper_daily; assert 'streamlit' not in sys.modules"],
                                 cwd=daily.ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(0, process.returncode, process.stderr)


if __name__ == "__main__":
    unittest.main()
