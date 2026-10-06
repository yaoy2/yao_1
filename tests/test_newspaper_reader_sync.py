"""Offline privacy, losslessness and CAS checks for cross-device reader state."""

import base64
from copy import deepcopy
import gzip
import hashlib
import json
import random
import string
import unittest
from unittest.mock import Mock, patch

from utils import newspaper_reader_sync as reader


ENV = {"GITHUB_BACKUP_TOKEN": "test-token-not-a-real-credential"}


def document():
    article = {"id": "news_test", "title": "保留原文的新闻", "group": "科技与科学", "category": "科学前沿",
               "kind": "报道", "source": "测试来源", "source_id": "test", "source_family": "public_news",
               "publisher": "测试来源", "published_at": "2026-10-06T09:00:00+08:00", "updated_at": None,
               "discovered_at": None, "time_basis": "published", "date_precision": "minute",
               "url": "https://example.org/news/1", "summary": "完整摘要。", "topic": "",
               "summary_origin": "来源摘要", "content_origin": "public_article", "summary_only": False,
               "ai_category": "", "ai_section": "", "rights": {"notice": "原版权声明"}}
    detail = {"id": "news_test", "status": "full", "paragraphs": ["第一段原文\n仍保持换行。", "第二段包含 emoji 📖 与空格  。"],
              "source": "测试来源", "url": "https://example.org/news/1", "title": article["title"],
              "published_at": article["published_at"], "content_origin": "public_article", "message": "来源正文"}
    record = {"article": article, "saved": True, "hidden": False, "read": True, "mark": "重要",
              "note": "我的笔记\n  缩进、换行都应保留。", "tags": "教学，AI", "folder": "工作资料",
              "saved_at": "2026-10-06T02:00:00Z", "detail": detail}
    return {"version": 1, "library": {"version": 1, "records": {"news_test": record}, "pins": ["教育校园"],
            "pinsCustomized": True, "following": ["group-0"], "lastArticle": deepcopy(article), "lastRead": "news_test",
            "design": {"columns": 3, "title": 17, "read": 18}},
            "recommendations": {"version": 1, "personalized": True, "strength": "balanced", "diversity": "standard",
             "profile": {"version": 1, "events": [{"id": "news_test", "category": "科学前沿", "group": "科技与科学",
                         "source": "测试来源", "type": "save", "at": 1791226800000}], "hiddenIds": []}}}


def response(status, payload=None):
    result = Mock()
    result.status_code = status
    result.json.return_value = payload
    return result


def private_response(**updates):
    metadata = {"private": True, "full_name": reader.PRIVATE_REPO}
    metadata.update(updates)
    return response(200, metadata)


def remote_response(doc=None, sha="old-sha", *, raw=None):
    raw = reader._encode_document(doc or document()) if raw is None else raw
    return response(200, {"sha": sha, "encoding": "base64", "size": len(raw),
                          "content": base64.b64encode(raw).decode("ascii")})


def session_with(*gets, put=None):
    session = Mock()
    session.get.side_effect = list(gets)
    session.put.return_value = put or response(200, {"content": {"sha": "new-sha"}})
    return session


class SchemaTest(unittest.TestCase):
    def test_document_round_trip_preserves_all_text_and_is_detached(self):
        original = document()
        validated = reader.validate_reader_document(original)
        self.assertEqual(original, validated)
        self.assertIsNot(original, validated)
        self.assertEqual(original, reader._decode_document(reader._encode_document(validated)))
        validated["library"]["records"]["news_test"]["note"] = "changed"
        self.assertNotEqual(original, validated)

    def test_current_empty_defaults_are_valid(self):
        value = {"version": 1, "library": {"version": 1, "records": {}, "pins": [], "pinsCustomized": False,
                  "following": [], "lastArticle": None, "lastRead": None, "design": {"columns": 3, "title": 17, "read": 18}},
                 "recommendations": {"version": 1, "personalized": True, "strength": "balanced", "diversity": "standard",
                                     "profile": {"version": 1, "events": [], "hiddenIds": []}}}
        self.assertEqual(value, reader.validate_reader_document(value))

    def test_unknown_fields_bad_types_and_mismatched_ids_are_not_dropped(self):
        changes = [lambda d: d.update(extra="unknown"), lambda d: d.update(version=True),
                   lambda d: d["library"].update(revision="local-only"),
                   lambda d: d["library"].update(pinsCustomized=1),
                   lambda d: d["library"]["design"].update(columns=9),
                   lambda d: d["library"]["records"]["news_test"].update(saved="yes"),
                   lambda d: d["library"]["records"]["news_test"].update(extra="unknown"),
                   lambda d: d["library"]["records"]["news_test"].update(folder="unsupported"),
                   lambda d: d["library"]["records"]["news_test"].update(mark="unsupported"),
                   lambda d: d["library"]["records"]["news_test"]["article"].update(id="other"),
                   lambda d: d["library"]["records"]["news_test"]["article"].update(title=123),
                   lambda d: d["library"]["records"]["news_test"]["article"].update(published_at="invalid date"),
                   lambda d: d["library"]["records"]["news_test"]["detail"].update(id="other"),
                   lambda d: d["library"]["records"]["news_test"]["detail"].update(paragraphs=[1]),
                   lambda d: d["library"]["records"]["news_test"]["detail"].update(status="made-up"),
                   lambda d: d["library"]["records"]["news_test"]["article"].update(summary_only=True),
                   lambda d: d["recommendations"].update(personalized=1),
                   lambda d: d["recommendations"].update(strength="unlimited"),
                   lambda d: d["recommendations"]["profile"]["events"][0].update(at=float("nan")),
                   lambda d: d["recommendations"]["profile"]["events"][0].update(at=True),
                   lambda d: d["recommendations"]["profile"]["events"][0].update(title="unexpected")]
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                value = document()
                change(value)
                before = deepcopy(value)
                with self.assertRaises(ValueError):
                    reader.validate_reader_document(value)
                self.assertEqual(before.keys(), value.keys())

    def test_unsafe_keys_are_rejected_at_every_depth(self):
        for key in ("constructor", "prototype", "__proto__"):
            value = document()
            value["library"]["records"]["news_test"]["article"]["rights"][key] = "unsafe"
            with self.subTest(key=key), self.assertRaises(ValueError):
                reader.validate_reader_document(value)
        value = document()
        value["library"]["records"]["constructor"] = value["library"]["records"].pop("news_test")
        with self.assertRaises(ValueError):
            reader.validate_reader_document(value)

    def test_urls_allow_only_http_https_without_embedded_credentials(self):
        for url in ("javascript:alert(1)", "data:text/plain,test", "file:///C:/private.txt", "https://user:pw@example.org/",
                    "https://example.org/\nsecret", "https:\\example.org/path", "https://example.org:99999/"):
            with self.subTest(url=url):
                value = document()
                value["library"]["records"]["news_test"]["article"]["url"] = url
                with self.assertRaises(ValueError):
                    reader.validate_reader_document(value)
        value = document()
        value["library"]["records"]["news_test"]["article"]["links"] = {"original": "javascript:alert(1)"}
        with self.assertRaises(ValueError):
            reader.validate_reader_document(value)
        value["library"]["records"]["news_test"]["article"]["links"] = {"original": "http://example.org/news"}
        reader.validate_reader_document(value)

    def test_notes_tags_paragraphs_and_profile_limits_fail_without_truncation(self):
        changes = [lambda d: d["library"]["records"]["news_test"].update(note="n" * 8001),
                   lambda d: d["library"]["records"]["news_test"].update(tags="t" * 501),
                   lambda d: d["library"]["records"]["news_test"]["detail"].update(paragraphs=["p"] * 1001),
                   lambda d: d["library"]["records"]["news_test"]["detail"].update(paragraphs=["p" * 20001]),
                   lambda d: d["recommendations"]["profile"].update(hiddenIds=["id-" + str(i) for i in range(2001)]),
                   lambda d: d["recommendations"]["profile"].update(events=[deepcopy(d["recommendations"]["profile"]["events"][0])] * 601)]
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                value = document()
                change(value)
                before = json.dumps(value)
                with self.assertRaises(ValueError):
                    reader.validate_reader_document(value)
                self.assertEqual(before, json.dumps(value))

    def test_link_metadata_preserves_titles_and_descriptions_next_to_urls(self):
        value = document()
        article = value["library"]["records"]["news_test"]["article"]
        article["links"] = [{"title": "原始来源", "url": "https://example.org/original", "description": "带文字的来源说明"}]
        article["canonical"] = {"name": "规范链接", "href": "https://example.org/canonical"}
        self.assertEqual(value, reader.validate_reader_document(value))
        article["links"][0]["url"] = "javascript:alert(1)"
        with self.assertRaises(ValueError):
            reader.validate_reader_document(value)

    def test_record_count_and_document_byte_limit(self):
        value = document()
        value["library"]["records"] = {"id-" + str(i): {"article": {"id": "id-" + str(i), "title": "T"}} for i in range(20001)}
        with self.assertRaisesRegex(ValueError, "20000"):
            reader.validate_reader_document(value)
        with patch.object(reader, "MAX_DOCUMENT_BYTES", 100), self.assertRaisesRegex(ValueError, "容量"):
            reader.validate_reader_document(document())

    def test_duplicate_profile_signals_or_lists_are_rejected(self):
        value = document()
        value["recommendations"]["profile"]["events"] *= 2
        with self.assertRaises(ValueError):
            reader.validate_reader_document(value)
        value = document()
        value["library"]["pins"] *= 2
        with self.assertRaises(ValueError):
            reader.validate_reader_document(value)

    def test_cycles_are_rejected_without_recursing_forever(self):
        value = document()
        value["library"]["records"]["news_test"]["article"]["rights"]["cycle"] = value
        with self.assertRaises(ValueError):
            reader.validate_reader_document(value)


class EncodingTest(unittest.TestCase):
    def test_envelope_is_deterministic_and_has_checked_plain_length_and_hash(self):
        encoded = reader._encode_document(document())
        self.assertEqual(encoded, reader._encode_document(document()))
        envelope = json.loads(encoded)
        raw = gzip.decompress(base64.b64decode(envelope["data"]))
        self.assertEqual(envelope["uncompressed_bytes"], len(raw))
        self.assertEqual(envelope["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertLessEqual(len(encoded), reader.MAX_FILE_BYTES)

    def test_bounded_decompression_rejects_bomb_even_with_false_declared_length(self):
        raw = b"x" * (reader.MAX_DOCUMENT_BYTES + 1)
        envelope = {"format": "newspaper-reader-state", "version": 1, "encoding": "gzip+base64",
                    "uncompressed_bytes": 1024, "sha256": hashlib.sha256(raw).hexdigest(),
                    "data": base64.b64encode(gzip.compress(raw)).decode("ascii")}
        with self.assertRaisesRegex(ValueError, "容量"):
            reader._decode_document(json.dumps(envelope).encode())

    def test_truncated_concatenated_and_tampered_compression_is_rejected(self):
        original = json.loads(reader._encode_document(document()))
        data = base64.b64decode(original["data"])
        for changed in (data[:-5], data + gzip.compress(b"extra"), data + b"trailing", data[:20] + b"broken" + data[26:]):
            envelope = {**original, "data": base64.b64encode(changed).decode("ascii")}
            with self.subTest(size=len(changed)), self.assertRaises(ValueError):
                reader._decode_document(json.dumps(envelope).encode())
        for change in ({"sha256": "0" * 64}, {"uncompressed_bytes": original["uncompressed_bytes"] + 1}, {"extra": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                reader._decode_document(json.dumps({**original, **change}).encode())

    def test_unsafe_duplicate_json_keys_are_not_silently_overwritten(self):
        for raw in (b'{"version":1,"version":2}', b'{"__proto__":{}}', b'{"n":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                reader._decode_document(raw)

    def test_stored_size_overflow_is_explicit(self):
        value = document()
        rng = random.Random(42)
        value["library"]["records"]["news_test"]["detail"]["paragraphs"] = ["".join(rng.choices(string.ascii_letters, k=10000))]
        with patch.object(reader, "MAX_FILE_BYTES", 2000), self.assertRaisesRegex(ValueError, "容量"):
            reader._encode_document(value)


class TransportTest(unittest.TestCase):
    def load(self, session, **kwargs):
        return reader.load_reader_state(environ=ENV, session=session, **kwargs)

    def save(self, session, doc=None, expected_sha="old-sha", **kwargs):
        return reader.save_reader_state(doc or document(), expected_sha, environ=ENV, session=session, **kwargs)

    def test_missing_file_is_loaded_none_after_private_verification(self):
        session = session_with(private_response(), response(404))
        self.assertEqual({"ok": True, "status": "loaded", "document": None, "sha": None}, self.load(session))
        self.assertEqual(2, session.get.call_count)
        session.put.assert_not_called()

    def test_load_is_fresh_uncached_and_supports_plain_wire_document(self):
        first, second = document(), document()
        second["library"]["records"]["news_test"]["note"] = "另一设备的新笔记"
        session = session_with(private_response(), remote_response(first), private_response(),
                               remote_response(second, "next-sha", raw=reader._json_bytes(second)))
        self.assertEqual(first, self.load(session)["document"])
        self.assertEqual(second, self.load(session)["document"])
        self.assertEqual(4, session.get.call_count)
        for call in session.get.call_args_list:
            self.assertFalse(call.kwargs["allow_redirects"])
            self.assertIn("no-store", call.kwargs["headers"]["Cache-Control"])

    def test_public_wrong_repository_and_redirect_stop_before_content(self):
        for repo in (private_response(private=False), private_response(full_name="other/private"), response(302)):
            with self.subTest(status=repo.status_code):
                session = session_with(repo)
                self.assertFalse(self.load(session)["ok"])
                self.assertEqual(1, session.get.call_count)
                session.put.assert_not_called()

    def test_config_cannot_redirect_personal_data_to_other_repo_or_branch(self):
        for env in ({**ENV, "GITHUB_BACKUP_REPO": "other/private"}, {**ENV, "GITHUB_BACKUP_BRANCH": "feature"}, {}):
            with self.subTest(env=env):
                session = Mock()
                result = reader.save_reader_state(document(), None, environ=env, session=session)
                self.assertFalse(result["ok"])
                session.get.assert_not_called()
                session.put.assert_not_called()

    def test_remote_bad_encoding_size_base64_or_schema_is_never_accepted(self):
        valid = remote_response().json.return_value
        for change in ({"encoding": "none"}, {"size": reader.MAX_FILE_BYTES + 1}, {"content": "!invalid!"},
                       {"sha": None}, {"content": base64.b64encode(b'{"version":1}').decode(), "size": 13}):
            session = session_with(private_response(), response(200, {**valid, **change}))
            with self.subTest(change=change):
                result = self.load(session)
                self.assertEqual("error", result["status"])
                session.put.assert_not_called()

    def test_http_and_exception_messages_never_expose_secrets(self):
        for fault in (RuntimeError("Bearer SECRET_TOKEN https://private.example/secret"), response(403, {"message": "SECRET_TOKEN"})):
            session = session_with(private_response(), fault)
            result = self.load(session)
            self.assertFalse(result["ok"])
            self.assertNotIn("SECRET", json.dumps(result))
            self.assertNotIn("private.example", json.dumps(result))

    def test_initial_save_uses_no_sha_and_returns_actual_readback_without_files(self):
        value = document()
        before = deepcopy(value)
        session = session_with(private_response(), response(404), remote_response(value, "new-sha"),
                               put=response(201, {"content": {"sha": "new-sha"}}))
        with patch("builtins.open", side_effect=AssertionError("No plaintext file may be opened")):
            result = self.save(session, value, expected_sha=None)
        self.assertEqual({"ok": True, "status": "saved", "document": value, "sha": "new-sha"}, result)
        self.assertEqual(before, value)
        call = session.put.call_args
        self.assertNotIn("sha", call.kwargs["json"])
        self.assertEqual("main", call.kwargs["json"]["branch"])
        self.assertTrue(call.args[0].endswith("/repos/yaoy2/yao_1-data/contents/data/newspaper_reader.json"))
        self.assertFalse(call.kwargs["allow_redirects"])
        stored = reader._decode_document(base64.b64decode(call.kwargs["json"]["content"]))
        self.assertEqual(value, stored)

    def test_existing_save_uses_fresh_observed_sha(self):
        old, updated = document(), document()
        updated["library"]["records"]["news_test"]["note"] = "new content"
        session = session_with(private_response(), remote_response(old), remote_response(updated, "new-sha"))
        result = self.save(session, updated)
        self.assertEqual("saved", result["status"])
        self.assertEqual("old-sha", session.put.call_args.kwargs["json"]["sha"])
        self.assertEqual(updated, result["document"])

    def test_fresh_conflict_returns_current_document_and_never_puts(self):
        current = document()
        current["library"]["records"]["news_test"]["note"] = "current remote"
        for expected, remote in (("stale-sha", remote_response(current, "current-sha")),
                                 (None, remote_response(current, "current-sha")), ("old-sha", response(404))):
            with self.subTest(expected=expected):
                session = session_with(private_response(), remote)
                result = self.save(session, expected_sha=expected)
                self.assertEqual("conflict", result["status"])
                self.assertEqual(current if remote.status_code == 200 else None, result["document"])
                self.assertEqual("current-sha" if remote.status_code == 200 else None, result["sha"])
                session.put.assert_not_called()

    def test_put_409_and_concurrent_create_422_return_latest_not_local(self):
        latest = document()
        latest["library"]["records"]["news_test"]["note"] = "concurrent edit"
        for status in (409, 422):
            with self.subTest(status=status):
                session = session_with(private_response(), response(404), remote_response(latest, "concurrent-sha"), put=response(status))
                result = self.save(session, expected_sha=None)
                self.assertEqual("conflict", result["status"])
                self.assertEqual(latest, result["document"])
                self.assertEqual("concurrent-sha", result["sha"])
                self.assertEqual(1, session.put.call_count)

    def test_422_without_version_change_is_an_error_not_fake_conflict(self):
        session = session_with(private_response(), remote_response(), remote_response(), put=response(422))
        self.assertEqual("error", self.save(session)["status"])
        self.assertEqual(1, session.put.call_count)

    def test_readback_must_match_both_new_sha_and_complete_document(self):
        changed = document()
        changed["library"]["records"]["news_test"]["detail"]["paragraphs"][0] = "different body"
        for verified in (remote_response(document(), "another-sha"), remote_response(changed, "new-sha"), response(404)):
            session = session_with(private_response(), remote_response(), verified)
            with self.subTest(verified=verified.status_code):
                result = self.save(session)
                self.assertEqual("error", result["status"])
                self.assertNotIn("document", result)

    def test_put_network_error_or_missing_commit_sha_never_claim_success(self):
        session = session_with(private_response(), remote_response())
        session.put.side_effect = RuntimeError("private-token SECRET")
        result = self.save(session)
        self.assertEqual("error", result["status"])
        self.assertNotIn("SECRET", json.dumps(result))
        session = session_with(private_response(), remote_response(), put=response(200, {"content": {}}))
        self.assertEqual("error", self.save(session)["status"])

    def test_invalid_or_oversize_local_payload_never_puts_or_truncates(self):
        value = document()
        value["library"]["records"]["news_test"]["note"] = "n" * 8001
        before = deepcopy(value)
        session = session_with(private_response())
        self.assertEqual("error", self.save(session, value)["status"])
        session.put.assert_not_called()
        self.assertEqual(before, value)
        with patch.object(reader, "MAX_FILE_BYTES", 100):
            session = session_with(private_response())
            result = self.save(session)
        self.assertIn("容量", result["message"])
        session.put.assert_not_called()

    def test_corrupt_current_remote_is_not_overwritten_even_with_matching_sha(self):
        session = session_with(private_response(), remote_response(raw=b"bad-json"))
        result = self.save(session)
        self.assertEqual("error", result["status"])
        session.put.assert_not_called()


if __name__ == "__main__":
    unittest.main()
