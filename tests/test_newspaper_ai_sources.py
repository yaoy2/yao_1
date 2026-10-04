"""Offline checks for bounded official RSS/Atom reading and truthful attribution."""

from datetime import datetime
import unittest
from unittest.mock import MagicMock, patch

import requests

from utils import newspaper_ai_sources as ai


NOW = datetime(2026, 10, 4, 21, tzinfo=ai.SHANGHAI)
SOURCE = ai.AI_SOURCES[0]
URL = "https://openai.com/index/research-test/"


def rss(*rows):
    content = ['<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>']
    for change in rows:
        row = {"title": "A benchmark for language models", "link": URL,
               "pubDate": "Fri, 02 Oct 2026 16:15:00 GMT", "description": "Official feed summary."}
        row.update(change)
        content.append("<item>" + "".join("<%s><![CDATA[%s]]></%s>" % (key, value, key)
                                        for key, value in row.items()) + "</item>")
    return ("".join(content) + "</channel></rss>").encode("utf-8")


def response(body, *, status=200, headers=None):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status_code = status
    result.headers = headers or {}
    result.iter_content.return_value = [body]
    return result


class OfficialAIParsingTest(unittest.TestCase):
    def test_official_attribution_dates_and_summary_never_claim_aihot_or_full_text(self):
        row = ai._parse_feed(rss({}), SOURCE, NOW)[0]
        self.assertTrue(row["id"].startswith("ai_official_"))
        self.assertEqual("OpenAI News", row["publisher"])
        self.assertEqual("ai_official", row["source_family"])
        self.assertEqual("科技与科学", row["group"])
        self.assertEqual("AI与互联网", row["category"])
        self.assertEqual("paper", row["ai_category"])
        self.assertEqual("2026-10-03T00:15:00+08:00", row["published_at"])
        self.assertEqual("Official feed summary.", row["summary"])
        self.assertTrue(row["summary_only"])
        self.assertFalse(row["available"])
        self.assertNotIn("aggregator", row)
        self.assertNotIn("aihot_score", row)
        self.assertIn("未核验原文全文", row["content_origin"])

    def test_missing_invalid_future_or_old_publication_is_not_replaced_with_today(self):
        for date in ("", "invalid", "2026-10-01", "2025-01-01T00:00:00Z", "2030-01-01T00:00:00Z"):
            with self.subTest(date=date):
                self.assertEqual([], ai._parse_feed(rss({"pubDate": date}), SOURCE, NOW))

    def test_atom_updated_only_is_labelled_updated_and_summary_not_content(self):
        xml = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <title>Product release</title><link rel="self" href="https://openai.com/feed/1"/>
          <link rel="alternate" href="https://openai.com/index/product/"/>
          <updated>2026-10-01T12:00:00Z</updated><summary>Official short summary.</summary>
          <content>Do not copy full syndicated body.</content></entry></feed>'''
        row = ai._parse_feed(xml, SOURCE, NOW)[0]
        self.assertEqual("", row["published_at"])
        self.assertEqual("updated", row["time_basis"])
        self.assertTrue(row["time"].startswith("更新 "))
        self.assertEqual("Official short summary.", row["summary"])
        self.assertEqual("https://openai.com/index/product/", row["url"])

    def test_html_and_full_content_are_not_used_as_verified_text(self):
        row = ai._parse_feed(rss({"description": "<p>One</p><script>bad()</script><p>Two</p>",
                                 "content:encoded": "Full article body"}), SOURCE, NOW)[0]
        self.assertEqual("One Two", row["summary"])
        without = ai._parse_feed(rss({"description": "", "content:encoded": "Full article body"}), SOURCE, NOW)[0]
        self.assertEqual("", without["summary"])

    def test_exact_url_deduplication_and_stable_id_do_not_merge_similar_titles(self):
        rows = ai._parse_feed(rss({}, {"title": "Changed title"}, {"link": URL + "other"}), SOURCE, NOW)
        self.assertEqual(2, len(rows))
        first = ai._parse_feed(rss({"title": "Changed title"}), SOURCE, NOW)[0]
        self.assertEqual(rows[0]["id"], first["id"])
        self.assertNotEqual(rows[0]["id"], rows[1]["id"])

    def test_limit_applies_after_publication_sort(self):
        data = rss(*({"link": URL + str(i), "pubDate": "2026-09-%02dT00:00:00Z" % (i + 1)} for i in range(15)))
        rows = ai._parse_feed(data, SOURCE, NOW)
        self.assertEqual(10, len(rows))
        self.assertEqual(URL + "14", rows[0]["url"])

    def test_source_specific_host_validation_rejects_foreign_local_and_credentials(self):
        for value in ("https://openai.com.evil.com/x", "https://google.com/x", "https://127.0.0.1/x",
                      "https://user:pw@openai.com/x", "https://openai.com:8443/x", "file:///secret",
                      "https://openai.com\\@evil.com/x", "https://openai.com/\npath"):
            with self.subTest(value=value):
                self.assertEqual("", ai._safe_url(value, SOURCE))
        self.assertEqual(URL, ai._safe_url(URL.replace("https:", "http:") + "#fragment", SOURCE))

    def test_entity_declarations_in_utf8_and_utf16_are_rejected(self):
        xml = '<!DOCTYPE rss [<!ENTITY x "unsafe">]><rss><channel/></rss>'
        for encoding in ("utf-8", "utf-16"):
            with self.subTest(encoding=encoding), self.assertRaisesRegex(ValueError, "实体"):
                ai._parse_feed(xml.encode(encoding), SOURCE, NOW)

    def test_literal_doctype_inside_syndicated_code_sample_is_not_a_dtd(self):
        rows = ai._parse_feed(rss({"content:encoded": "<pre>&lt;!DOCTYPE html&gt;</pre> <!DOCTYPE html>"}), SOURCE, NOW)
        self.assertEqual(1, len(rows))
        self.assertEqual("Official feed summary.", rows[0]["summary"])

    def test_five_sections_use_explicit_title_terms_or_source_topic(self):
        examples = {"A partnership announcement": "industry", "A research benchmark": "paper",
                    "How to build an agent": "tip", "A new language model": "ai-models",
                    "Introducing a new application": "ai-products"}
        for title, expected in examples.items():
            with self.subTest(title=title):
                self.assertEqual(expected, ai._classify(title, "industry"))
        self.assertEqual("paper", ai._classify("Unclassified title", "paper"))


class OfficialAIFeedTest(unittest.TestCase):
    def test_failures_are_isolated_and_old_valid_feeds_are_empty_without_global_error(self):
        sources = ai.AI_SOURCES[:3]
        def fetch(source):
            if source == sources[1]:
                raise requests.Timeout("private connection information")
            if source == sources[2]:
                return rss({"link": "https://research.google/blog/old/", "pubDate": "2025-01-01T00:00:00Z"}), ""
            return rss({}), "public, max-age=60"
        with patch.object(ai, "AI_SOURCES", sources), patch.object(ai, "_fetch_source", side_effect=fetch), \
                patch.object(ai, "_now", return_value=NOW):
            result = ai.load_ai_official_feed()
        self.assertEqual(1, len(result["articles"]))
        self.assertEqual(["ok", "error", "ok"], [s["status"] for s in result["sources"]])
        self.assertEqual([1, 0, 0], [s["count"] for s in result["sources"]])
        self.assertEqual("最近 60 天无新条目", result["sources"][2]["note"])
        self.assertEqual(["Google DeepMind：读取官方订阅超时"], result["errors"])
        self.assertNotIn("private", str(result))

    def test_no_store_sources_are_excluded_without_retaining_body(self):
        with patch.object(ai, "AI_SOURCES", (SOURCE,)), \
                patch.object(ai, "_fetch_source", return_value=(rss({}), "no-cache, no-store, must-revalidate")), \
                patch.object(ai, "_parse_feed") as parse:
            result = ai.load_ai_official_feed()
        parse.assert_not_called()
        self.assertEqual([], result["articles"])
        self.assertEqual([], result["errors"])
        self.assertIn("不缓存", result["sources"][0]["note"])
        self.assertTrue(result["cache_policy"]["store"])
        self.assertNotIn("ai_nvidia", {s.id for s in ai.AI_SOURCES})

    def test_only_fixed_feed_urls_are_requested_and_redirects_are_not_followed(self):
        redirect = response(b"", status=302, headers={"Location": "http://169.254.169.254/metadata"})
        with patch.object(ai.requests, "get", return_value=redirect) as get:
            with self.assertRaisesRegex(ValueError, "未跟随"):
                ai._fetch_source(SOURCE)
            get.assert_called_once()
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
        changed = ai.AISource("fake", "fake", "https://openai.com/arbitrary/", SOURCE.hosts, "industry")
        with patch.object(ai.requests, "get") as get, self.assertRaisesRegex(ValueError, "允许范围"):
            ai._fetch_source(changed)
        get.assert_not_called()

    def test_response_size_is_bounded_before_and_during_reading(self):
        for sample in (response(b"", headers={"Content-Length": str(ai.MAX_RESPONSE_BYTES + 1)}),
                       response(b"x" * (ai.MAX_RESPONSE_BYTES + 1))):
            with self.subTest(headers=sample.headers), patch.object(ai.requests, "get", return_value=sample), \
                    self.assertRaisesRegex(ValueError, "响应过大"):
                ai._fetch_source(SOURCE)

    def test_reading_is_always_summary_only_and_never_requests_original(self):
        row = ai._parse_feed(rss({}), SOURCE, NOW)[0]
        with patch.object(ai.requests, "get") as get:
            result = ai.fetch_ai_official_article(row)
            bad = ai.fetch_ai_official_article({**row, "url": "https://evil.com/private"})
            invalid = ai.fetch_ai_official_article({"source_id": []})
            empty = ai.fetch_ai_official_article({**row, "summary": ""})
        get.assert_not_called()
        self.assertEqual("summary", result["status"])
        self.assertTrue(result["summary_only"])
        self.assertEqual([row["summary"]], result["paragraphs"])
        self.assertEqual("error", bad["status"])
        self.assertEqual("error", invalid["status"])
        self.assertEqual("summary", empty["status"])
        self.assertEqual([], empty["paragraphs"])


if __name__ == "__main__":
    unittest.main()
