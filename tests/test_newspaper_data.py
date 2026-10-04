"""Offline tests for public-source parsing, isolation and safe reading."""

from datetime import datetime
import json
import unittest
from unittest.mock import MagicMock, patch

import requests

from utils import newspaper_data as news


NOW = datetime(2026, 10, 4, 16, tzinfo=news.SHANGHAI)
CN_URL = "https://www.chinanews.com.cn/cj/2026/10-04/10707824.shtml"
CCTV_URL = "https://news.cctv.com/2026/10/04/ARTIJtL8gUEa30jeFiJ41Vmd261004.shtml"
RSS_SOURCE = news.SOURCES[2]


def rss(*items):
    xml = '<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel>'
    for item in items:
        values = {"title": "金融市场真实报道", "link": CN_URL,
                  "pubDate": "Sun, 4 Oct 2026 15:50:25 +0800",
                  "description": "来源给出的真实摘要。"}
        values.update(item)
        xml += "<item>" + "".join("<%s><![CDATA[%s]]></%s>" % (key, value, key)
                                   for key, value in values.items()) + "</item>"
    return (xml + "</channel></rss>").encode("utf-8")


def response(status=200, body=b"", headers=None):
    value = MagicMock()
    value.__enter__.return_value = value
    value.status_code = status
    value.headers = headers or {}
    value.iter_content.return_value = [body]
    return value


class NewspaperParsingTest(unittest.TestCase):
    def test_rss_requires_real_date_title_and_official_article_url(self):
        payload = rss({}, {"pubDate": ""}, {"title": ""},
                      {"link": "https://evil.example/news"},
                      {"link": "https://www.chinanews.com.cn/rss/china.xml"})
        rows = news._parse_rss(payload, RSS_SOURCE)
        self.assertEqual(1, len(rows))
        self.assertEqual("2026-10-04T15:50:25+08:00", rows[0]["published_at"])
        self.assertFalse(rows[0]["available"])
        self.assertEqual("中新网", rows[0]["source"])

    def test_markup_is_plain_text_and_scripts_are_not_displayed(self):
        rows = news._parse_rss(rss({"title": "<b>真实标题</b><script>bad()</script>",
                                   "description": "<p>第一段</p><script>private()</script><p>第二段</p>"}), RSS_SOURCE)
        self.assertEqual("真实标题", rows[0]["title"])
        self.assertEqual("第一段 第二段", rows[0]["summary"])

    def test_id_and_exact_url_deduplication_do_not_merge_similar_titles(self):
        first = news._parse_rss(rss({}), RSS_SOURCE)[0]
        second_source = news.SOURCES[0]
        same = news._parse_rss(rss({"title": "同一网址的另一个标题"}), second_source)[0]
        different = news._parse_rss(rss({"link": CN_URL.replace("10707824", "10707825")}), RSS_SOURCE)[0]
        self.assertEqual(first["id"], same["id"])
        self.assertNotEqual(first["id"], different["id"])
        self.assertEqual([first, different], news._deduplicate([first, same, different]))

    def test_rss_entity_declarations_are_rejected(self):
        with self.assertRaises(ValueError):
            news._parse_rss(b'<!DOCTYPE rss [<!ENTITY secret SYSTEM "file:///etc/passwd">]><rss/>', RSS_SOURCE)

    def test_cctv_jsonp_is_parsed_without_evaluation(self):
        source = next(s for s in news.SOURCES if s.id == "cctv_tech")
        row = {"title": "我国卫星发射取得成功", "url": CCTV_URL,
               "brief": "<b>原始摘要</b>", "focus_date": "2026-10-04 12:55:47"}
        payload = ("tech(" + json.dumps({"data": {"list": [row]}}) + ");").encode()
        articles = news._parse_cctv(payload, source)
        self.assertEqual("航天航空", articles[0]["category"])
        self.assertEqual("原始摘要", articles[0]["summary"])
        with self.assertRaises(ValueError):
            news._parse_cctv(b'tech({});runMaliciousCode()', source)

    def test_military_json_uses_its_actual_fields(self):
        source = next(s for s in news.SOURCES if s.parser == "military")
        payload = json.dumps({"rollData": [{"title": "国防军事训练报道", "url": CCTV_URL,
                                           "dateTime": "2026-10-04 11:14", "description": "演训摘要"}]}).encode()
        article = news._parse_cctv(payload, source)[0]
        self.assertEqual("国防军事", article["category"])
        self.assertEqual("演训摘要", article["summary"])

    def test_books_use_publication_day_and_skip_navigation(self):
        source = next(s for s in news.SOURCES if s.parser == "books")
        page = '''<a href="/404058/index.html">书汇</a>
          <p><a href="/n1/2026/0923/c405071-40804261.html">《真实小说》新书推荐</a> 作者的介绍。</p>
          <a href="https://evil.example/n1/2026/0923/c405071-1.html">伪造推荐</a>'''
        rows = news._parse_books(page.encode("utf-8"), source)
        self.assertEqual(1, len(rows))
        self.assertEqual("2026-09-23", rows[0]["time"])
        self.assertEqual("day", rows[0]["date_precision"])
        self.assertEqual("推荐", rows[0]["kind"])
        self.assertEqual("小说推荐", rows[0]["category"])

    def test_book_title_without_genre_is_not_assumed_to_be_nonfiction(self):
        source = next(s for s in news.SOURCES if s.parser == "books")
        page = '<a href="/n1/2026/0923/c405071-40804261.html">《激情》</a>'
        article = news._parse_books(page.encode("utf-8"), source)[0]
        self.assertEqual("新书与综合书单", article["category"])
        self.assertEqual("阅读与文学", article["group"])

    def test_stale_sources_and_future_items_do_not_look_current(self):
        payload = rss({"pubDate": "2025-06-05"}, {"pubDate": "2030-01-01"})
        with patch.object(news, "_fetch_bytes", return_value=payload):
            with self.assertRaisesRegex(ValueError, "近期有效"):
                news._load_source(RSS_SOURCE, NOW)


class NewspaperFeedTest(unittest.TestCase):
    def test_failure_is_isolated_and_completion_order_does_not_change_source_priority(self):
        first, second = news.SOURCES[:2]
        broken = news.Source("broken", "错误来源", "测试", "https://news.cctv.com/", "rss", "地方城市")

        def fetch(url):
            if url == broken.url:
                raise requests.Timeout("raw internal connection details")
            return rss({})

        with patch.object(news, "SOURCES", (first, broken, second)), \
                patch.object(news, "_fetch_bytes", side_effect=fetch), \
                patch.object(news, "_now", return_value=NOW):
            result = news.load_newspaper_feed()
        self.assertEqual(1, len(result["articles"]))
        self.assertEqual(first.id, result["articles"][0]["source_id"])
        self.assertEqual(["ok", "error", "ok"], [s["status"] for s in result["sources"]])
        self.assertEqual([1, 0, 1], [s["count"] for s in result["sources"]])
        self.assertEqual("错误来源 · 测试：读取来源超时", result["errors"][0])
        self.assertEqual(NOW.isoformat(), result["fetched_at"])

    def test_source_limit_applies_after_deduplication_and_sorting(self):
        source = news.Source("small", "中新网", "测试", RSS_SOURCE.url, "rss", "宏观经济", limit=1)
        payload = rss({"pubDate": "2026-10-02"}, {"link": CN_URL.replace("10707824", "10707825")})
        with patch.object(news, "_fetch_bytes", return_value=payload):
            rows = news._load_source(source, NOW)
        self.assertEqual(1, len(rows))
        self.assertIn("10707825", rows[0]["url"])


class NewspaperSafetyTest(unittest.TestCase):
    def test_url_rejects_local_hosts_lookalikes_credentials_and_other_paths(self):
        invalid = ["file:///etc/passwd", "http://127.0.0.1/", "http://localhost/",
                   "https://www.chinanews.com.cn.evil.example/x", "https://user@www.chinanews.com.cn/x",
                   "https://www.chinanews.com.cn:8443/x", "https://www.chinanews.com.cn\\@evil.example/x",
                   "https://www.chinanews.com.cn/\npath", "https://www.chinanews.com.cn/rss/china.xml"]
        for url in invalid:
            with self.subTest(url=url):
                self.assertEqual("", news._safe_url(url, article_only=True))
        self.assertEqual(CN_URL, news._safe_url(CN_URL.replace("https:", "http:") + "#fragment", article_only=True))

    def test_redirect_to_untrusted_host_is_never_requested(self):
        redirect = response(302, headers={"Location": "http://169.254.169.254/metadata"})
        with patch.object(news.requests, "get", return_value=redirect) as get:
            with self.assertRaisesRegex(ValueError, "不允许"):
                news._fetch_bytes(CN_URL, article_only=True)
        self.assertEqual(1, get.call_count)
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_response_size_is_bounded_even_without_content_length(self):
        with patch.object(news.requests, "get", return_value=response(body=b"x" * 9)), \
                patch.object(news, "MAX_RESPONSE_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "过大"):
                news._fetch_bytes(CN_URL)

    def test_invalid_article_does_not_make_a_network_request(self):
        with patch.object(news, "_fetch_bytes") as fetch:
            result = news.fetch_newspaper_article({"url": "http://127.0.0.1/", "summary": "something"})
        fetch.assert_not_called()
        self.assertEqual("error", result["status"])
        self.assertEqual([], result["paragraphs"])


class NewspaperReaderTest(unittest.TestCase):
    def setUp(self):
        self.article = news._parse_rss(rss({}), RSS_SOURCE)[0]

    def test_known_article_container_becomes_plain_paragraphs(self):
        first = "第一段真实正文，保留新闻事实和原始出处。" * 8
        second = "第二段真实正文，补充背景与时间。" * 8
        payload = ('<nav>无关导航</nav><div class="left_zw"><p>' + first +
                   '</p><script>evil()</script><p>' + second +
                   '</p><p>编辑：某某</p></div><footer>广告</footer>').encode("utf-8")
        with patch.object(news, "_fetch_bytes", return_value=payload):
            result = news.fetch_newspaper_article(self.article)
        self.assertEqual("full", result["status"])
        self.assertEqual([first, second], result["paragraphs"])
        self.assertEqual(CN_URL, result["url"])

    def test_repeated_literary_paragraphs_are_preserved_in_order(self):
        repeated = "这是一段有意反复出现的文学文字。" * 6
        middle = "这是中间一段。" * 6
        payload = ('<div class="left_zw"><p>' + repeated + '</p><p>' + middle +
                   '</p><p>' + repeated + '</p></div>').encode("utf-8")
        with patch.object(news, "_fetch_bytes", return_value=payload):
            result = news.fetch_newspaper_article(self.article)
        self.assertEqual("full", result["status"])
        self.assertEqual([repeated, middle, repeated], result["paragraphs"])

    def test_missing_container_video_teaser_and_paywall_fall_back_to_summary(self):
        pages = [b"<html><p>navigation only</p></html>",
                 '<div class="left_zw"><p>短视频说明。</p></div>'.encode("utf-8"),
                 '<div class="left_zw"><p>订阅后阅读</p><p>公开摘要</p></div>'.encode("utf-8")]
        for page in pages:
            with self.subTest(page=page), patch.object(news, "_fetch_bytes", return_value=page):
                result = news.fetch_newspaper_article(self.article)
            self.assertEqual("summary", result["status"])
            self.assertEqual([self.article["summary"]], result["paragraphs"])

    def test_network_restriction_returns_summary_without_retry_or_bypass(self):
        denied = requests.HTTPError("sensitive transport details")
        denied.response = response(403)
        with patch.object(news, "_fetch_bytes", side_effect=denied) as fetch:
            result = news.fetch_newspaper_article(self.article)
        fetch.assert_called_once()
        self.assertEqual("error", result["status"])
        self.assertIn("403", result["message"])
        self.assertNotIn("sensitive", result["message"])

    def test_oversized_article_is_not_mislabeled_as_complete_after_truncation(self):
        body = '<div class="left_zw"><p>' + ('正文' * 3100) + '</p><p>另一段内容。</p></div>'
        with patch.object(news, "_fetch_bytes", return_value=body.encode("utf-8")):
            result = news.fetch_newspaper_article(self.article)
        self.assertEqual("summary", result["status"])
        self.assertEqual([self.article["summary"]], result["paragraphs"])


if __name__ == "__main__":
    unittest.main()
