"""Offline checks for public English interview discovery and complete reading."""

from datetime import datetime
from html import escape
import json
import unittest
from unittest.mock import patch

from utils import newspaper_interview_english as english
from utils import newspaper_sources as media


NOW = datetime(2026, 10, 7, 12, tzinfo=media.SHANGHAI)
DATE = "2026-09-30T12:00:00+00:00"
PUBDATE = "Wed, 30 Sep 2026 12:00:00 +0000"
ANSWER = "This is a complete public answer about a person's work, experience and choices, with sufficient context for the reader. " * 3
QA = ("<p><strong>How did your work begin?</strong></p><p>" + ANSWER + "</p>"
      "<p><strong>What did you learn?</strong></p><p>" + ANSWER + " Final answer retained.</p>")
SOURCES = {
    english.CREATIVE: media.PublicSource(english.CREATIVE, "TCI", "https://thecreativeindependent.com/feed.xml",
                                        ("thecreativeindependent.com",), media.INTERVIEW_CATEGORY, "english_interviews", 184),
    english.INTERVIEW: media.PublicSource(english.INTERVIEW, "Interview Magazine", "https://www.interviewmagazine.com/culture",
                                         ("www.interviewmagazine.com",), media.INTERVIEW_CATEGORY, "english_interviews", 184),
    english.QUANTA: media.PublicSource(english.QUANTA, "Quanta Q&A", "https://www.quantamagazine.org/tag/qa/feed/",
                                      ("www.quantamagazine.org",), media.INTERVIEW_CATEGORY, "english_interviews", 184),
    english.LEX: media.PublicSource(english.LEX, "Lex Fridman", "https://lexfridman.com/feed/podcast/",
                                   ("lexfridman.com",), media.INTERVIEW_CATEGORY, "english_interviews", 184),
}
URLS = {
    english.CREATIVE: "https://thecreativeindependent.com/people/a-chef-on-creative-work/",
    english.INTERVIEW: "https://www.interviewmagazine.com/culture/a-conversation-with-a-chef",
    english.QUANTA: "https://www.quantamagazine.org/a-scientist-on-research-20260930/",
    english.LEX: "https://lexfridman.com/test-guest-transcript",
}


def atom(*entries):
    parts = ['<feed xmlns="http://www.w3.org/2005/Atom">']
    for entry in entries:
        row = {"url": URLS[english.CREATIVE], "published": DATE, "body": QA, "title": "A chef on creative work"}
        row.update(entry)
        parts.append("<entry><title>" + escape(row["title"]) + '</title><link href="' + row["url"] + '"/>'
                     + ("<published>" + row["published"] + "</published>" if row["published"] else "")
                     + "<updated>" + DATE + "</updated><content type=\"html\"><![CDATA[" + row["body"]
                     + "]]></content><summary>Public introduction.</summary></entry>")
    return ("".join(parts) + "</feed>").encode()


def rss(*entries):
    parts = ['<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>']
    for row in entries:
        data = {"title": "A recent conversation", "link": URLS[english.QUANTA], "pubDate": PUBDATE,
                "description": "Publisher introduction."}
        data.update(row)
        parts.append("<item>" + "".join("<%s><![CDATA[%s]]></%s>" % (key, value, key)
                                      for key, value in data.items()) + "</item>")
    return ("".join(parts) + "</channel></rss>").encode()


def page(body, *, published=DATE, extra=""):
    return ("<html><head>" + ('<meta property="article:published_time" content="' + published + '">'
                              if published else "")
            + extra + '</head><body><h1>Verified conversation</h1>' + body + "</body></html>").encode()


def interview_page(*, published=DATE):
    body = "<div id='post-body'>"
    for index in range(2):
        body += "<p><strong>HOST:</strong> How did you decide?</p><p>GUEST: " + ANSWER + str(index) + "</p>"
    return page(body + "</div>", published=published)


def quanta_page(*, published=DATE):
    body = '<div id="postBody">'
    for index in range(2):
        body += ('<div class="post__content__section"><div class="post__content">'
                 + ("<p>Quanta spoke with the scientist. This interview was edited for clarity.</p>" if index == 0 else "")
                 + '<h3><strong>What is question ' + str(index) + '?</strong></h3><p>' + ANSWER
                 + (" Final section retained." if index == 1 else "")
                 + '</p><aside><p>Duplicated pull quote.</p></aside></div></div>')
    return page(body + "</div><div class='related'><h3>Unrelated question?</h3></div>", published=published)


def lex_page(count=6, *, single_speaker=False, missing_turn=False, segments_per_turn=1):
    body = '<div class="entry-content">'
    for index in range(count):
        name = "Lex Fridman" if single_speaker or (index // segments_per_turn) % 2 == 0 else "Test Guest"
        text = ANSWER + (" Last complete turn." if index == count - 1 else str(index))
        body += ('<div class="ts-segment"><span class="ts-name">' + name
                 + '</span><span class="ts-timestamp">(00:01:00)</span>'
                 + ("" if missing_turn and index == 1 else '<span class="ts-text">' + text + "</span>") + "</div>")
    return page(body + "</div>")


class EnglishInterviewURLsTest(unittest.TestCase):
    def test_exact_origins_and_article_routes_exclude_downloads_accounts_and_lookalikes(self):
        for source_id, source in SOURCES.items():
            with self.subTest(source=source_id):
                self.assertTrue(english.allows_article_url(source, URLS[source_id]))
                for url in (source.url, URLS[source_id] + "?redirect=https://evil.example/", URLS[source_id] + "#media",
                            URLS[source_id].replace("https://", "https://reader:password@"),
                            URLS[source_id].replace("https://", "http://"),
                            URLS[source_id].replace(source.hosts[0], source.hosts[0] + ".evil.example"),
                            "https://" + source.hosts[0] + "/wp-json/", "https://" + source.hosts[0] + "/audio.mp3"):
                    self.assertFalse(english.allows_article_url(source, url), url)


class CreativeIndependentTest(unittest.TestCase):
    def test_full_atom_interview_is_readable_without_extra_requests(self):
        with patch.object(media, "_request") as request:
            rows, controls, note, incomplete = english.load_source(atom({}), SOURCES[english.CREATIVE], NOW)
        request.assert_not_called()
        self.assertEqual(1, len(rows))
        self.assertEqual("feed_full", rows[0]["content_origin"])
        self.assertFalse(rows[0]["summary_only"])
        self.assertIn("Final answer retained.", rows[0]["feed_paragraphs"][-1])
        self.assertEqual([], controls)
        self.assertEqual("", note)
        self.assertFalse(incomplete)

    def test_essays_paid_previews_old_future_and_updated_only_items_are_excluded(self):
        for change in ({"body": "<p>" + ANSWER + "</p><p>" + ANSWER + "</p>"},
                       {"body": QA + "<p>Subscribe to read the remainder.</p>"},
                       {"published": "2025-01-01T00:00:00Z"}, {"published": "2027-01-01T00:00:00Z"},
                       {"published": ""}, {"url": "https://thecreativeindependent.com/essays/a-personal-essay/"}):
            with self.subTest(change=change):
                self.assertEqual([], english.load_source(atom(change), SOURCES[english.CREATIVE], NOW)[0])

    def test_article_fallback_keeps_only_the_actual_conversation(self):
        html = page('<div id="article__main__content"><div class="article-section__body">' + QA
                    + '</div></div><aside><p>Unrelated recommendation.</p></aside>')
        paragraphs = english.extract_article(html, SOURCES[english.CREATIVE])
        self.assertEqual(4, len(paragraphs))
        self.assertIn("Final answer retained.", paragraphs[-1])

    def test_a_recognized_interview_that_cannot_be_read_keeps_the_batch_incomplete(self):
        rows, _, note, incomplete = english.load_source(
            atom({"body": QA + "<p>Subscribe to read the remainder.</p>"}), SOURCES[english.CREATIVE], NOW)
        self.assertEqual([], rows)
        self.assertTrue(incomplete)
        self.assertIn("完整性", note)


class QuantaInterviewsTest(unittest.TestCase):
    def test_rss_teaser_is_replaced_by_all_body_sections_and_cache_headers_survive(self):
        feed = rss({"content:encoded": "<p>" + ANSWER + "</p><p>Read the article at its source.</p>"})
        with patch.object(media, "_request", return_value=(quanta_page(), "private, no-store")) as request:
            rows, controls, note, incomplete = english.load_source(feed, SOURCES[english.QUANTA], NOW)
        request.assert_called_once_with(URLS[english.QUANTA], SOURCES[english.QUANTA], article=True)
        self.assertEqual(["private, no-store"], controls)
        self.assertEqual("public_article", rows[0]["content_origin"])
        body = " ".join(rows[0]["feed_paragraphs"])
        self.assertIn("Final section retained.", body)
        self.assertNotIn("Duplicated pull quote.", body)
        self.assertNotIn("Read the article at its source.", body)
        self.assertEqual("", note)
        self.assertFalse(incomplete)

    def test_a_current_url_or_modified_time_does_not_make_old_publication_recent(self):
        html = quanta_page(published="2020-01-01T00:00:00Z").replace(
            b"</head>", b'<meta property="article:modified_time" content="2026-10-01T00:00:00Z"></head>')
        with patch.object(media, "_request", return_value=(html, "")):
            self.assertEqual([], english.load_source(rss({}), SOURCES[english.QUANTA], NOW)[0])

    def test_ordinary_article_or_incomplete_qa_is_not_a_full_interview(self):
        ordinary = page('<div id="postBody"><div class="post__content__section"><div class="post__content">'
                        + QA + "</div></div></div>")
        self.assertEqual([], english.extract_article(ordinary, SOURCES[english.QUANTA]))
        with patch.object(media, "_request", return_value=(ordinary, "max-age=60")):
            rows, controls, _, incomplete = english.load_source(rss({}), SOURCES[english.QUANTA], NOW)
        self.assertEqual([], rows)
        self.assertEqual(["max-age=60"], controls)
        self.assertTrue(incomplete)


class InterviewMagazineTest(unittest.TestCase):
    def test_section_discovery_deduplicates_and_requires_real_dialogue(self):
        first, second = URLS[english.INTERVIEW], "https://www.interviewmagazine.com/film/a-film-essay"
        listing = ('<a href="' + first + '">Conversation</a><a href="' + first + '">Image</a>'
                   '<a href="https://evil.example/film/bad">Bad</a>').encode()
        extra = ('<a href="' + second + '">An essay</a><a href="' + first + '">Conversation</a>').encode()

        def request(url, source, **kwargs):
            if url == english.INTERVIEW_FILM:
                self.assertFalse(kwargs.get("article", False))
                return extra, "max-age=600"
            self.assertTrue(kwargs.get("article"))
            return (interview_page() if url == first else page('<div id="post-body">' + QA + '</div>')), "no-cache"

        with patch.object(media, "_request", side_effect=request) as get:
            rows, controls, _, incomplete = english.load_source(listing, SOURCES[english.INTERVIEW], NOW)
        self.assertEqual([first], [row["url"] for row in rows])
        self.assertEqual(3, get.call_count)
        self.assertEqual(["max-age=600", "no-cache", "no-cache"], controls)
        self.assertFalse(incomplete)

    def test_failed_extra_section_keeps_main_results_and_modified_only_page_is_rejected(self):
        listing = ('<a href="' + URLS[english.INTERVIEW] + '">Conversation</a>').encode()
        with patch.object(media, "_request", side_effect=[OSError("section unavailable"), (interview_page(), "")]):
            rows, _, note, incomplete = english.load_source(listing, SOURCES[english.INTERVIEW], NOW)
        self.assertEqual(1, len(rows))
        self.assertIn("补充栏目", note)
        self.assertTrue(incomplete)
        html = interview_page(published="").replace(
            b"</head>", b'<meta property="article:modified_time" content="2026-09-30T12:00:00Z"></head>')
        with patch.object(media, "_request", side_effect=[(b"", ""), (html, "")]):
            self.assertEqual([], english.load_source(listing, SOURCES[english.INTERVIEW], NOW)[0])

    def test_publication_can_come_from_article_jsonld_graph_but_never_webpage_modified(self):
        data = {"@graph": [{"@type": "WebPage", "dateModified": DATE},
                           {"@type": "Article", "datePublished": DATE}]}
        soup = english._soup(page("", published="", extra='<script type="application/ld+json">' + json.dumps(data) + '</script>'))
        self.assertEqual(DATE, english._publication(soup))
        data["@graph"].pop()
        soup = english._soup(page("", published="", extra='<script type="application/ld+json">' + json.dumps(data) + '</script>'))
        self.assertEqual("", english._publication(soup))


class LexInterviewsTest(unittest.TestCase):
    def test_only_explicit_transcript_links_are_fetched_not_episode_or_audio(self):
        description = ('<a href="https://lexfridman.com/test-guest/">Episode</a>'
                       '<a href="https://lexfridman.com/audio.mp3">Audio</a>'
                       '<a href="' + URLS[english.LEX] + '">Transcript</a>')
        feed = rss({"link": "https://lexfridman.com/test-guest/", "description": description},
                   {"link": "https://lexfridman.com/another-episode/", "description": "Only a video introduction."})
        with patch.object(media, "_request", return_value=(lex_page(), "no-cache")) as request:
            rows, controls, _, incomplete = english.load_source(feed, SOURCES[english.LEX], NOW)
        request.assert_called_once_with(URLS[english.LEX], SOURCES[english.LEX], article=True)
        self.assertEqual(URLS[english.LEX], rows[0]["url"])
        self.assertEqual("A recent conversation", rows[0]["title"])
        self.assertIn("Last complete turn.", rows[0]["feed_paragraphs"][-1])
        self.assertEqual(["no-cache"], controls)
        self.assertFalse(incomplete)

    def test_long_transcripts_are_complete_while_over_limit_or_missing_turns_are_rejected(self):
        paragraphs = english.extract_article(lex_page(530), SOURCES[english.LEX])
        self.assertEqual(530, len(paragraphs))
        self.assertIn("Last complete turn.", paragraphs[-1])
        for html in (lex_page(801), lex_page(single_speaker=True), lex_page(missing_turn=True),
                     lex_page().replace(ANSWER.encode(), b"x" * 6001, 1),
                     lex_page().replace(ANSWER.encode(), b"Subscribe to read the rest.", 1)):
            with self.subTest(length=len(html)):
                self.assertEqual([], english.extract_article(html, SOURCES[english.LEX]))

    def test_adjacent_timestamp_spans_are_combined_without_dropping_text(self):
        paragraphs = english.extract_article(lex_page(1080, segments_per_turn=2), SOURCES[english.LEX])
        self.assertEqual(540, len(paragraphs))
        self.assertEqual(1080, " ".join(paragraphs).count("(00:01:00)"))
        self.assertIn("Last complete turn.", paragraphs[-1])
        # One guest monologue with many timestamps is not alternating dialogue.
        self.assertEqual([], english.extract_article(lex_page(6, segments_per_turn=3), SOURCES[english.LEX]))

    def test_old_feed_entries_are_filtered_before_any_article_request(self):
        feed = rss({"description": URLS[english.LEX], "pubDate": "Wed, 01 Jan 2020 12:00:00 +0000"})
        with patch.object(media, "_request") as request:
            self.assertEqual([], english.load_source(feed, SOURCES[english.LEX], NOW)[0])
        request.assert_not_called()

    def test_an_explicit_but_oversized_transcript_is_not_a_successful_complete_batch(self):
        with patch.object(media, "_request", return_value=(lex_page(801), "max-age=60")):
            rows, controls, note, incomplete = english.load_source(
                rss({"description": URLS[english.LEX]}), SOURCES[english.LEX], NOW)
        self.assertEqual([], rows)
        self.assertEqual(["max-age=60"], controls)
        self.assertTrue(incomplete)
        self.assertIn("完整性或长度", note)


class EnglishInterviewBoundsTest(unittest.TestCase):
    def test_all_article_requests_failing_is_not_a_successful_empty_batch(self):
        with patch.object(media, "_request", side_effect=OSError("source unavailable")), \
                self.assertRaisesRegex(ValueError, "读取失败"):
            english.load_source(rss({"description": URLS[english.LEX]}), SOURCES[english.LEX], NOW)

    def test_request_limit_partial_failures_and_cache_policies_are_preserved(self):
        feed = rss(*[{"description": "https://lexfridman.com/person-%d-transcript" % number} for number in range(4)])
        with patch.object(english, "MAX_ARTICLE_REQUESTS", 3), patch.object(media, "_request", side_effect=[
                (lex_page(), "max-age=60"), OSError("unavailable"), (lex_page(), "no-store")]) as request:
            rows, controls, note, incomplete = english.load_source(feed, SOURCES[english.LEX], NOW)
        self.assertEqual(3, request.call_count)
        self.assertEqual(2, len(rows))
        self.assertEqual(["max-age=60", "no-store"], controls)
        self.assertIn("暂时无法读取", note)
        self.assertIn("上限", note)
        self.assertTrue(incomplete)

    def test_time_budget_stops_before_starting_another_request(self):
        feed = rss({"description": URLS[english.LEX]})
        with patch.object(english.time, "monotonic", side_effect=[0, english.MAX_SOURCE_SECONDS + 1]), \
                patch.object(media, "_request") as request:
            rows, _, note, incomplete = english.load_source(feed, SOURCES[english.LEX], NOW)
        request.assert_not_called()
        self.assertEqual([], rows)
        self.assertIn("上限", note)
        self.assertTrue(incomplete)

    def test_feed_entities_and_non_xml_formats_do_not_reach_article_requests(self):
        malicious = b'<!DOCTYPE rss [<!ENTITY secret "data">]><rss><channel/></rss>'
        with patch.object(media, "_request") as request:
            for value in (malicious, b"<html><body>Verification required.</body></html>"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    english.load_source(value, SOURCES[english.LEX], NOW)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
