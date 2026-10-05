"""Offline checks for publisher adapters, honest dates, and bounded reading."""

from datetime import datetime
import json
import unittest
from unittest.mock import MagicMock, patch

import requests

from utils import newspaper_sources as media


NOW = datetime(2026, 10, 5, 11, 40, tzinfo=media.SHANGHAI)
IT = media.SOURCE_BY_ID["media_ithome"]
BBC = media.SOURCE_BY_ID["media_bbc"]
YICAI = media.SOURCE_BY_ID["media_yicai"]
LIFEWEEK = media.SOURCE_BY_ID["media_lifeweek"]
TOUTIAO = media.SOURCE_BY_ID["media_toutiao"]
URL = "https://www.ithome.com/1/009/783.htm"
BODY = "<p>" + "第一段公开正文，保留来源提供的完整文字。" * 6 + "</p><p>" + "第二段公开正文，核实完整内容并保留原文链接。" * 6 + "</p>"


def rss(*rows):
    parts = ['<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>']
    for row in rows:
        data = {"title": "科技进展", "link": URL, "pubDate": "Mon, 05 Oct 2026 02:30:00 GMT", "description": "来源摘要"}
        data.update(row)
        parts.append("<item>" + "".join("<%s><![CDATA[%s]]></%s>" % (key, value, key)
                                      for key, value in data.items()) + "</item>")
    return ("".join(parts) + "</channel></rss>").encode("utf-8")


def response(body, status=200, headers=None):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status_code = status
    result.headers = headers or {}
    result.iter_content.return_value = [body]
    return result


def nuxt(body, params="a,b", args='54,"2026-10-02 17:00:00"'):
    return ('<html><script>window.__NUXT__=(function(' + params + '){return ' + body + '}(' + args + '));</script></html>').encode("utf-8")


class PublicFeedParsingTest(unittest.TestCase):
    def test_known_complete_rss_description_keeps_body_and_attribution(self):
        row = media._parse_feed(rss({"description": BODY}), IT, NOW)[0]
        self.assertEqual("IT之家", row["publisher"])
        self.assertEqual("public_media", row["source_family"])
        self.assertEqual("2026-10-05T10:30:00+08:00", row["published_at"])
        self.assertEqual("feed_full", row["content_origin"])
        self.assertEqual(2, len(row["feed_paragraphs"]))
        self.assertFalse(row["summary_only"])
        with patch.object(media.requests, "get") as get:
            detail = media.fetch_extended_article(row)
        get.assert_not_called()
        self.assertEqual("full", detail["status"])
        self.assertEqual(row["feed_paragraphs"], detail["paragraphs"])

    def test_generic_rss_description_is_summary_even_when_long(self):
        row = media._parse_feed(rss({"link": "https://www.bbc.co.uk/news/articles/abc", "description": BODY}), BBC, NOW)[0]
        self.assertEqual("source_summary", row["content_origin"])
        self.assertEqual([], row["feed_paragraphs"])
        self.assertTrue(row["summary_only"])

    def test_explicit_encoded_content_and_teasers_are_distinguished(self):
        row = media._parse_feed(rss({"link": "https://www.bbc.co.uk/news/articles/abc", "content:encoded": BODY}), BBC, NOW)[0]
        self.assertEqual("feed_full", row["content_origin"])
        teaser = media._parse_feed(rss({"description": BODY + "<p>购买后阅读全文</p>"}), IT, NOW)[0]
        self.assertEqual("source_summary", teaser["content_origin"])

    def test_missing_publication_keeps_collection_time_separate(self):
        row = media._parse_feed(rss({"pubDate": ""}), IT, NOW)[0]
        self.assertEqual("", row["published_at"])
        self.assertEqual("collected", row["time_basis"])
        self.assertEqual(NOW.isoformat(), row["discovered_at"])
        self.assertEqual("收录 2026-10-05 11:40", row["time"])

    def test_stale_and_future_items_are_excluded(self):
        for value in ("2025-01-01T00:00:00Z", "2026-10-05T04:26:00Z"):
            with self.subTest(value=value):
                self.assertEqual([], media._parse_feed(rss({"pubDate": value}), IT, NOW))

    def test_rdf_namespaces_and_day_precision(self):
        source = media.SOURCE_BY_ID["media_nature"]
        xml = b'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
          xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <item><title>Research</title><link>https://www.nature.com/articles/test</link>
          <dc:date>2026-10-02</dc:date><description>Journal summary</description></item></rdf:RDF>'''
        row = media._parse_feed(xml, source, NOW)[0]
        self.assertEqual("day", row["date_precision"])
        self.assertEqual("2026-10-02", row["time"])

    def test_atom_updated_only_is_not_claimed_as_publication(self):
        xml = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Update</title>
          <link rel="self" href="https://www.bbc.co.uk/feed/item"/>
          <link href="https://www.bbc.co.uk/news/articles/abc"/>
          <updated>2026-10-04T12:00:00Z</updated><summary>Summary</summary></entry></feed>'''
        row = media._parse_feed(xml, BBC, NOW)[0]
        self.assertEqual("", row["published_at"])
        self.assertEqual("updated", row["time_basis"])
        self.assertTrue(row["time"].startswith("更新 "))

    def test_duplicate_url_prefers_available_summary(self):
        rows = media._parse_feed(rss({"description": ""}, {"description": "完整来源摘要"}), IT, NOW)
        rows = media._deduplicate(rows)
        self.assertEqual(1, len(rows))
        self.assertEqual("完整来源摘要", rows[0]["summary"])

    def test_xml_entities_are_rejected_but_cdata_examples_are_allowed(self):
        xml = '<!DOCTYPE rss [<!ENTITY x "bad">]><rss><channel/></rss>'
        for encoding in ("utf-8", "utf-16"):
            with self.subTest(encoding=encoding), self.assertRaisesRegex(ValueError, "实体"):
                media._parse_feed(xml.encode(encoding), IT, NOW)
        self.assertEqual(1, len(media._parse_feed(rss({"description": "<!DOCTYPE html> example"}), IT, NOW)))


class PublicListParsingTest(unittest.TestCase):
    def test_yicai_dates_attribution_and_readability_follow_actual_record(self):
        row = {"url": "/news/123456.html", "NewsTitle": "公司动态", "NewsNotes": "来源介绍",
               "EntityPublishDate": "2026-10-04T17:36:00", "CreateDate": "2026-10-05T10:00:00",
               "NewsSource": "央视新闻", "ProductId": 0}
        content = ("var breakNews = " + json.dumps([row]) + ";").encode()
        article = media._parse_yicai(content, YICAI, NOW)[0]
        self.assertEqual("2026-10-04T17:36:00+08:00", article["published_at"])
        self.assertEqual("央视新闻", article["publisher"])
        self.assertFalse(article["summary_only"])
        row["LoginLimit"] = True
        article = media._parse_yicai(("var headList = " + json.dumps([row]) + ";").encode(), YICAI, NOW)[0]
        self.assertTrue(article["summary_only"])

    def test_toutiao_list_categories_and_tracking_urls_do_not_manufacture_dates(self):
        rows = [{"Title": "国际新闻", "Url": "https://www.toutiao.com/trending/123/?log_pb=abc&rank=1", "InterestCategory": ["international"]},
                {"Title": "体育新闻", "Url": "https://www.toutiao.com/article/456", "InterestCategory": "sports"},
                {"Title": "外链", "Url": "https://example.com/7", "InterestCategory": None}]
        data = json.dumps({"status": "success", "data": rows}).encode()
        articles = media._parse_toutiao(data, TOUTIAO, NOW)
        self.assertEqual(2, len(articles))
        self.assertEqual("https://www.toutiao.com/trending/123/", articles[0]["url"])
        self.assertEqual("国际要闻", articles[0]["category"])
        self.assertEqual("热点", articles[0]["kind"])
        self.assertTrue(all(a["published_at"] == "" and a["time_basis"] == "collected" for a in articles))

    def test_lifeweek_uses_article_rows_and_does_not_import_magazine_or_audio_cards(self):
        body = '{data:[{items:[{id:274131,title:"公开长文",contentType:a,pubTime:b,daodu:"来源导读"},' \
               '{id:5000,title:"期刊广告",contentType:5,pubTime:b},' \
               '{contentId:2000,title:"旧音频",contentType:11}]}]}'
        rows = media._parse_lifeweek(nuxt(body), LIFEWEEK, NOW)
        self.assertEqual(1, len(rows))
        self.assertEqual("https://www.lifeweek.com.cn/article/274131", rows[0]["url"])
        self.assertEqual("来源导读", rows[0]["summary"])
        self.assertEqual("深读", rows[0]["kind"])
        self.assertEqual("2026-10-02T17:00:00+08:00", rows[0]["published_at"])

    def test_nuxt_parser_accepts_data_but_never_javascript_expressions(self):
        data = media._nuxt_data(nuxt('{value:a,missing:b}', "a,b", '"literal",void 0'))
        self.assertEqual({"value": "literal", "missing": None}, data)
        for value in ('alert("x")', "(()=>1)()", "document.cookie", "void 1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                media._nuxt_data(nuxt("{value:a}", "a", value))


class PublicRequestsTest(unittest.TestCase):
    def test_url_validation_is_specific_to_each_publisher(self):
        for value in ("https://www.ithome.com.evil.com/1.htm", "https://127.0.0.1/x", "file:///secret",
                      "https://user:pass@www.ithome.com/a", "https://www.ithome.com:444/a",
                      "https://www.ithome.com\\@evil.com/x", "https://www.ithome.com/x\ny"):
            with self.subTest(value=value):
                self.assertEqual("", media._safe_url(value, IT))
        self.assertEqual(URL, media._safe_url(URL + "?utm_source=abc#fragment", IT))
        self.assertEqual(URL + "?article=2", media._safe_url(URL + "?article=2", IT))

    def test_redirects_are_not_followed_or_read(self):
        result = response(b"secret", status=302, headers={"Location": "http://169.254.169.254/"})
        with patch.object(media.requests, "get", return_value=result) as get:
            with self.assertRaisesRegex(ValueError, "跳转"):
                media._request(IT.url, IT)
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
            result.iter_content.assert_not_called()

    def test_private_no_store_and_no_cache_remain_readable_with_shared_cache_policy(self):
        cases = (("private", False, False), ("no-store", False, False),
                 ("public, no-cache", True, False), ("public, max-age=0, must-revalidate", True, False),
                 ("public, max-age=60, s-maxage=0", True, False), ("public, max-age=600", True, True))
        for control, store, reuse in cases:
            result = response(rss({"description": BODY}), headers={"Cache-Control": control})
            with self.subTest(control=control), patch.object(media.requests, "get", return_value=result), \
                    patch.object(media, "PUBLIC_SOURCES", (IT,)), patch.object(media, "_now", return_value=NOW):
                feed = media.load_extended_news_feed()
            self.assertEqual([], feed["errors"])
            self.assertEqual(1, len(feed["articles"]))
            self.assertEqual("ok", feed["sources"][0]["status"])
            self.assertEqual(control, feed["sources"][0]["cache_control"])
            for policy in (feed["cache_policy"], feed["articles"][0]["cache_policy"]):
                self.assertEqual(store, policy["store"])
                self.assertEqual(reuse, policy["reuse"])
            if not reuse:
                self.assertTrue(feed["sources"][0]["note"])
            detail = media.fetch_extended_article(feed["articles"][0])
            self.assertEqual("full", detail["status"])
            self.assertEqual(store, detail["cache_policy"]["store"])
            self.assertEqual(reuse, detail["cache_policy"]["reuse"])

    def test_response_size_and_elapsed_time_are_bounded(self):
        result = response(b"12345")
        with patch.object(media.requests, "get", return_value=result), patch.object(media, "MAX_RESPONSE_BYTES", 4):
            with self.assertRaisesRegex(ValueError, "过大"):
                media._request(IT.url, IT)
        with patch.object(media.requests, "get", return_value=result), patch.object(media.time, "monotonic", side_effect=[0, 19]):
            with self.assertRaises(TimeoutError):
                media._request(IT.url, IT)

    def test_arbitrary_feed_paths_are_not_requested(self):
        with patch.object(media.requests, "get") as get, self.assertRaisesRegex(ValueError, "范围"):
            media._request("https://www.ithome.com/arbitrary", IT)
        get.assert_not_called()

    def test_source_failures_are_isolated_and_order_and_limit_are_stable(self):
        def load(source, now):
            if source == BBC:
                raise requests.Timeout("private connection details")
            return media._parse_feed(rss({}), source, now), "public, max-age=600"
        with patch.object(media, "PUBLIC_SOURCES", (IT, BBC)), patch.object(media, "_load_source", side_effect=load), patch.object(media, "_now", return_value=NOW):
            result = media.load_extended_news_feed()
        self.assertEqual(1, len(result["articles"]))
        self.assertEqual(["ok", "error"], [s["status"] for s in result["sources"][:2]])
        self.assertNotIn("private connection", str(result))
        self.assertEqual(["excluded", "excluded"], [s["status"] for s in result["sources"][2:]])
        data = rss(*({"link": URL + "?article=" + str(i), "pubDate": "2026-10-%02dT00:00:00Z" % (1 + i % 4)} for i in range(25)))
        with patch.object(media, "_request", return_value=(data, "public")):
            rows, _ = media._load_source(IT, NOW)
        self.assertEqual(20, len(rows))
        self.assertEqual("2026-10-04T08:00:00+08:00", rows[0]["published_at"])


class PublicArticleTest(unittest.TestCase):
    def article(self, **changes):
        result = media._article(YICAI, "文章", "https://www.yicai.com/news/123456.html", "2026-10-05T10:00:00", "来源摘要", NOW, local=True)
        result.update(changes)
        return result

    def test_public_yicai_body_supports_short_single_paragraph_news(self):
        body = "<div id='multi-text'><p>" + "这是一篇完整的公开新闻快讯，内容很短但仍可在本站阅读全文。" * 4 + "</p></div>"
        with patch.object(media, "_request", return_value=(body.encode(), "public, max-age=43200")) as get:
            detail = media.fetch_extended_article(self.article())
        self.assertEqual("full", detail["status"])
        self.assertFalse(detail["summary_only"])
        self.assertEqual(1, len(detail["paragraphs"]))
        self.assertEqual("public_article", detail["content_origin"])
        self.assertTrue(get.call_args.kwargs["article"])

    def test_restricted_cards_are_not_fetched_and_page_paywalls_are_not_full_text(self):
        with patch.object(media, "_request") as get:
            detail = media.fetch_extended_article(self.article(restricted=True))
        get.assert_not_called()
        self.assertEqual("summary", detail["status"])
        body = "<div id='multi-text'>" + BODY + "</div><aside>登录后阅读全文</aside>"
        with patch.object(media, "_request", return_value=(body.encode(), "")):
            detail = media.fetch_extended_article(self.article())
        self.assertEqual("summary", detail["status"])
        self.assertEqual(["来源摘要"], detail["paragraphs"])

    def test_transient_read_error_is_retryable_and_retains_summary(self):
        with patch.object(media, "_request", side_effect=requests.Timeout("private details")):
            detail = media.fetch_extended_article(self.article())
        self.assertEqual("error", detail["status"])
        self.assertEqual(["来源摘要"], detail["paragraphs"])
        self.assertNotIn("private", str(detail))

    def test_article_response_and_feed_cache_rules_are_both_preserved(self):
        body = ("<div id='multi-text'>" + BODY + "</div>").encode()
        for control, feed_policy, expected in (("private", {}, {"store": False, "reuse": False}),
                                               ("no-store", {}, {"store": False, "reuse": False}),
                                               ("no-cache", {}, {"store": True, "reuse": False}),
                                               ("public", {"store": False, "reuse": False}, {"store": False, "reuse": False})):
            with self.subTest(control=control, feed_policy=feed_policy), patch.object(media, "_request", return_value=(body, control)):
                detail = media.fetch_extended_article(self.article(cache_policy=feed_policy))
            self.assertEqual("full", detail["status"])
            self.assertEqual(expected, detail["cache_policy"])

    def test_non_supported_article_hosts_and_routes_never_trigger_requests(self):
        for changes in ({"url": "https://www.yicai.com/profile/123"}, {"url": "https://evil.com/article/1"}, {"source_id": []}):
            with self.subTest(changes=changes), patch.object(media, "_request") as get:
                detail = media.fetch_extended_article(self.article(**changes))
            get.assert_not_called()
            self.assertNotEqual("full", detail["status"])


if __name__ == "__main__":
    unittest.main()
