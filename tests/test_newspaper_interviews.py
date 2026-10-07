"""Publication boundaries apply equally to live and previously cached interviews."""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import patch

import pytest

from utils import newspaper_sources as media
from utils import newspaper_data as news
from utils.newspaper_interviews import (
    INTERVIEW_CATEGORY, SHANGHAI, has_interview_label, interview_cutoff, is_recent_interview, retain_interviews, without_expired_interviews,
)


NOW = datetime(2026, 10, 6, 12, tzinfo=SHANGHAI)


def interview(published_at, **changes):
    return {"category": INTERVIEW_CATEGORY, "published_at": published_at, **changes}


@pytest.mark.parametrize("offset, expected", [
    (timedelta(), True), (timedelta(days=-183), True),
    (timedelta(days=-183, seconds=-1), False), (timedelta(seconds=1), False),
])
def test_six_calendar_month_window_has_explicit_inclusive_boundaries(offset, expected):
    assert is_recent_interview(interview((NOW + offset).isoformat()), NOW) is expected


@pytest.mark.parametrize("current, expected", [
    ("2026-08-31T12:00:00+08:00", "2026-02-28T12:00:00+08:00"),
    ("2024-08-31T12:00:00+08:00", "2024-02-29T12:00:00+08:00"),
    ("2026-03-31T23:00:00+00:00", "2025-10-01T07:00:00+08:00"),
])
def test_cutoff_uses_beijing_calendar_and_clamps_short_months(current, expected):
    assert interview_cutoff(datetime.fromisoformat(current)).isoformat() == expected


@pytest.mark.parametrize("value", [None, "", "not a date", "2026-10-05", "2026-10-05T12:00:00"])
def test_collection_or_update_never_substitutes_for_publication(value):
    row = interview(value, updated_at=NOW.isoformat(), discovered_at=NOW.isoformat())
    assert not is_recent_interview(row, NOW)


def test_timezone_offsets_represent_the_same_instant_and_other_sections_are_untouched():
    recent = interview(NOW.astimezone(timezone.utc).isoformat())
    old = interview((NOW - timedelta(days=184)).isoformat())
    other = {"category": "散文随笔", "published_at": ""}
    assert without_expired_interviews([old, recent, other], NOW) == [recent, other]
    assert len([old, recent, other]) == 3
    assert not is_recent_interview(interview(NOW.isoformat(), time_basis="updated"), NOW)


WRITER = media.SOURCE_BY_ID["media_chinawriter_interviews"]
LIFEWEEK = media.SOURCE_BY_ID["media_lifeweek_interviews"]
WRITER_URL = "https://www.chinawriter.com.cn/n1/2026/1005/c405057-40808385.html"


def writer_page(*rows):
    return ('<ul class="previous_list">' + ''.join(
        f'<li><span><a href="{url}">{title}</a></span><em>{date}</em></li>'
        for url, title, date in rows) + '</ul>').encode("utf-8")


def lifeweek_page(rows, recommendation=""):
    return ('<script>window.__NUXT__=(function(a){return {data:[{articleList:[' + rows
            + ']}],recommendations:[' + recommendation + ']}}(54));</script>').encode("utf-8")


def test_writer_column_membership_and_list_date_are_used_without_inventing_summaries():
    # An old-looking path cannot overrule the actual date printed in the list.
    url = WRITER_URL.replace("/1005/", "/0920/")
    rows = media._parse_chinawriter_interviews(writer_page(
        (url, "徐春林：南方县城与《经纬长江》", "2026-10-05"),
        (WRITER_URL, "没有日期", ""),
        ("https://other.test/n1/2026/1005/c405057-1.html", "站外内容", "2026-10-05"),
    ), WRITER, NOW)
    assert len(rows) == 1
    assert rows[0]["published_at"] == "2026-10-05T00:00:00+08:00"
    assert rows[0]["date_precision"] == "day"
    assert rows[0]["category"] == INTERVIEW_CATEGORY
    assert rows[0]["kind"] == "访谈"
    assert rows[0]["summary"] == ""
    assert rows[0]["summary_only"] is False


def test_old_or_future_interviews_are_successful_empty_results():
    content = writer_page((WRITER_URL, "旧作家访谈", "2026-04-05"),
                          (WRITER_URL.replace("40808385", "40808386"), "未来稿件", "2026-10-07"))
    assert media._parse_chinawriter_interviews(content, WRITER, NOW) == []
    with patch.object(media, "PUBLIC_SOURCES", (WRITER,)), patch.object(media, "INACTIVE_SOURCES", ()), \
         patch.object(media, "_request", return_value=(content, "")), patch.object(media, "_now", return_value=NOW):
        feed = media.load_extended_news_feed()
    assert feed["errors"] == []
    assert feed["sources"][0]["status"] == "ok"
    assert feed["sources"][0]["note"] == "近半年暂无新访谈"


@pytest.mark.parametrize("content", [b'<html>login or structure changed</html>',
    writer_page((WRITER_URL, "日期不明", ""))])
def test_missing_list_or_dates_are_reported_as_source_failures(content):
    with pytest.raises(ValueError):
        media._parse_chinawriter_interviews(content, WRITER, NOW)


def test_lifeweek_reads_only_the_interview_list_and_enforces_six_months():
    row = '{id:273320,title:"作家的文学世界",pubTime:"2026-04-06 12:00:00",contentType:a,summary:"公开导读"}'
    recommended = '{id:999999,title:"推荐广告",pubTime:"2026-10-05 12:00:00",contentType:a}'
    rows = media._parse_lifeweek_interviews(lifeweek_page(row, recommended), LIFEWEEK, NOW)
    assert len(rows) == 1
    assert rows[0]["url"] == "https://www.lifeweek.com.cn/article/273320"
    assert rows[0]["summary_only"] is True
    assert rows[0]["category"] == INTERVIEW_CATEGORY
    assert rows[0]["summary"] == "公开导读"
    assert media._parse_lifeweek_interviews(lifeweek_page(row.replace("12:00:00", "11:59:59")), LIFEWEEK, NOW) == []
    assert media._parse_lifeweek_interviews(lifeweek_page(row.replace("2026-04-06", "2026-10-07")), LIFEWEEK, NOW) == []
    with pytest.raises(ValueError):
        media._parse_lifeweek_interviews(lifeweek_page(row.replace("pubTime", "updateTime")), LIFEWEEK, NOW)


def test_interview_deduplication_preserves_column_membership_and_identity():
    row = media._parse_lifeweek_interviews(lifeweek_page(
        '{id:273320,title:"专访",pubTime:"2026-10-05 12:00:00",contentType:a}'), LIFEWEEK, NOW)[0]
    general = {**row, "source_id": "media_lifeweek", "category": "散文随笔", "summary": "首页导读"}
    assert media._deduplicate([general, row]) == [row]
    assert media._deduplicate([row, general]) == [row]


def test_writer_full_text_is_only_fetched_on_demand_and_paywall_is_respected():
    with patch.object(media, "_request") as request:
        row = media._parse_chinawriter_interviews(writer_page((WRITER_URL, "文学对话", "2026-10-05")), WRITER, NOW)[0]
    request.assert_not_called()
    body = '<div class="end_article"><p>' + '公开文学访谈内容。' * 30 + '</p><p>' + '对话第二部分。' * 30 + '</p></div>'
    with patch.object(media, "_request", return_value=(body.encode("utf-8"), "private, no-store")) as request:
        detail = media.fetch_extended_article(row)
    request.assert_called_once_with(WRITER_URL, WRITER, article=True)
    assert detail["status"] == "full"
    assert detail["cache_policy"] == {"store": False, "reuse": False}
    with patch.object(media, "_request", return_value=((body + '购买后阅读全文').encode("utf-8"), "")):
        assert media.fetch_extended_article(row)["status"] == "summary"
    teaser = '<div class="end_article"><p>' + '仅有导读。' * 20 + '</p></div>'
    with patch.object(media, "_request", return_value=(teaser.encode("utf-8"), "")):
        assert media.fetch_extended_article(row)["status"] == "summary"
    with patch.object(media, "_request") as request:
        restricted = media.fetch_extended_article({**row, "restricted": True})
    request.assert_not_called()
    assert restricted["status"] == "summary"


@pytest.mark.parametrize("title", [
    "专访企业创始人：制造业的新机会", "科学家访谈：量子实验室的一天", "对谈｜运动员与教练",
    "独家对话航天员：再赴太空", "对话工程师：让桥梁更安全", "对话丨从医生到公益发起人",
    "Interview: A robotics pioneer", "An interview with an Olympic champion",
])
def test_explicit_interview_labels_have_no_industry_or_fame_filter(title):
    assert has_interview_label(title)


@pytest.mark.parametrize("title", [
    "伊朗表示愿推动也门胡塞武装与沙特对话", "中美举行新一轮战略对话", "文明对话会在京举行",
    "科学家：人工智能的新前沿", "企业家年度人物评选启动", "双方同意建立对话机制",
])
def test_generic_person_news_and_diplomatic_dialogue_do_not_become_interviews(title):
    assert not has_interview_label(title)


def test_general_publishers_classify_recent_interviews_in_the_independent_group():
    source = media.SOURCE_BY_ID["media_yicai"]
    row = media._article(source, "专访科学家：芯片突破", "https://www.yicai.com/news/123.html",
                         NOW.isoformat(), "原站摘要", NOW)
    assert row["group"] == "人物与访谈"
    assert row["kind"] == "访谈"
    assert media._article(source, "专访企业家", row["url"], "", "", NOW) is None
    assert media._article(source, "专访企业家", row["url"], (NOW-timedelta(days=184)).isoformat(), "", NOW) is None
    assert media._article(source, "专访企业家", row["url"], (NOW-timedelta(days=100)).isoformat(), "", NOW) is not None
    assert media._article(source, "专访企业家", row["url"], NOW.isoformat(), "", NOW, time_basis="updated") is None
    base = news._article(news.SOURCES[5], "专访运动员：备战新赛季",
                         "https://www.chinanews.com.cn/ty/2026/10-06/123456.shtml", NOW.isoformat())
    assert base["category"] == INTERVIEW_CATEGORY
    assert base["group"] == "人物与访谈"


def test_recent_interviews_are_retained_before_the_general_feed_limit_without_reordering_dates():
    articles = [{"id": str(i), "category": "宏观经济"} for i in range(30)]
    articles.extend({"id": str(i), "category": INTERVIEW_CATEGORY} for i in range(30, 33))
    result = retain_interviews(articles, 20)
    assert [a["id"] for a in result] == [str(i) for i in (*range(17), 30, 31, 32)]
    assert len(articles) == 33


def dxw_page(*rows):
    return ('<div id="newlist"><ul class="news_list_ul">' + ''.join(
        f'<li><div class="news_title"><a href="{url}">{title}</a></div>'
        f'<div class="news_content"><a>{summary}</a><p class="time">{date}</p></div></li>'
        for url, title, summary, date in rows) + '</ul></div>').encode("utf-8")


def test_chinanews_uses_list_date_and_explicit_interview_evidence_not_just_a_person_name():
    source = media.SOURCE_BY_ID["media_chinanews_interviews"]
    url = "https://www.chinanews.com.cn/dxw/2026/09-20/12345.shtml"
    page = dxw_page((url, "跨文化教育如何创新？", "——专访某大学校长", "2026-10-5 20:48"),
                    (url.replace("12345", "12346"), "AI伦理困局何解？", "作者评论", "2026-10-5 18:53"),
                    (url.replace("12345", "12347"), "企业家怎么看未来？", "——访某企业创始人", "2026-10-4 19:45"),
                    (url.replace("/dxw/", "/cul/shipin/"), "同题视频", "专访科学家", "2026-10-5 19:00"),
                    (url.replace("12345", "12348"), "旧采访", "专访运动员", "2026-4-5 18:00"))
    rows = media._parse_chinanews_interviews(page, source, NOW)
    assert len(rows) == 2
    assert rows[0]["published_at"] == "2026-10-05T20:48:00+08:00"
    assert all(row["group"] == "人物与访谈" and not row["summary_only"] for row in rows)
    with patch.object(media, "_request", return_value=(page, "max-age=120")):
        loaded, _, _, _ = media._load_source(source, NOW)
    assert loaded[0]["cache_policy"]["max_age_seconds"] == 120


def test_cctv_full_programs_use_web_release_stamp_and_never_fetch_video_or_claim_full_text():
    source = media.SOURCE_BY_ID["media_cctv_dialogue"]
    url = "https://tv.cctv.com/2026/10/05/VIDEexample261005.shtml"
    row = {"mode": 0, "title": "《对话》企业家的创新探索", "brief": "本期节目对话企业创始人。", "url": url,
           "time": "2026-09-20 21:30:00", "focus_date": int((NOW-timedelta(days=1)).timestamp()*1000)}
    payload = {"data": {"list": [row, {**row, "mode": 1}, {**row, "title": "精彩预告"},
                                   {**row, "focus_date": int((NOW-timedelta(days=184)).timestamp()*1000)},
                                   {**row, "focus_date": None, "time": NOW.isoformat()},
                                   {**row, "url": "https://other.test/video.shtml"}]}}
    rows = media._parse_cctv_interviews(json.dumps(payload).encode(), source, NOW)
    assert len(rows) == 1
    assert rows[0]["published_at"] == (NOW-timedelta(days=1)).isoformat()
    assert rows[0]["kind"] == "视频访谈" and rows[0]["summary_only"]
    assert rows[0]["group"] == "人物与访谈"
    with patch.object(media, "_request") as request:
        detail = media.fetch_extended_article(rows[0])
    request.assert_not_called()
    assert detail["status"] == "summary"
    with pytest.raises(ValueError):
        media._parse_cctv_interviews(b'{"data":{}}', source, NOW)


def test_general_feeds_reject_expired_interviews_before_taking_the_display_limit():
    source = news.SOURCES[2]
    recent = news._article(source, "专访企业家：新市场",
                          "https://www.chinanews.com.cn/cj/2026/10-05/12345.shtml", NOW.isoformat())
    expired = {**recent, "id": "expired", "url": recent["url"].replace("12345", "12346"),
               "published_at": (NOW-timedelta(days=184)).isoformat()}
    with patch.object(news, "_fetch_bytes", return_value=b"unused"), patch.object(news, "_parse_rss", return_value=[expired, recent]):
        assert [row["id"] for row in news._load_source(source, NOW)] == [recent["id"]]


def test_writer_history_follows_public_links_and_keeps_more_than_twenty_articles():
    first = writer_page(*[(WRITER_URL.replace("40808385", str(41000000+i)), f"访谈 {i}", "2026-09-01")
                          for i in range(40)]) + b'<a href="index2.html">next</a>'
    second = writer_page((WRITER_URL, "半年前访谈", "2026-04-07"),
                         (WRITER_URL.replace("40808385", "40808386"), "过期访谈", "2026-04-01")) + b'<a href="index3.html">next</a>'
    with patch.object(media, "_request", side_effect=[(first, "max-age=600"), (second, "max-age=60")]) as request:
        rows, control, note, _ = media._load_source(WRITER, NOW)
    assert len(rows) == 41 and note == ""
    assert [call.args[0] for call in request.call_args_list] == [WRITER.url, WRITER.url.replace("index.html", "index2.html")]
    assert all(row["cache_policy"]["max_age_seconds"] == 60 for row in rows)
    assert media._cache_policy(control)["max_age_seconds"] == 60


def test_unavailable_history_preserves_current_articles_and_reports_incomplete_coverage():
    first = writer_page((WRITER_URL, "公开访谈", "2026-10-05")) + b'<a href="index2.html">next</a>'
    with patch.object(media, "_request", side_effect=[(first, ""), TimeoutError("private connection info")]), \
         patch.object(media, "PUBLIC_SOURCES", (WRITER,)), patch.object(media, "INACTIVE_SOURCES", ()), \
         patch.object(media, "_now", return_value=NOW):
        feed = media.load_extended_news_feed()
    assert len(feed["articles"]) == 1 and feed["sources"][0]["status"] == "ok"
    assert "部分历史列表" in feed["sources"][0]["note"]
    assert "private connection" not in str(feed)


def test_history_does_not_follow_unpublished_or_foreign_next_links():
    first = writer_page((WRITER_URL, "公开访谈", "2026-10-05")) + b'<a href="https://other.test/index2.html">next</a>'
    with patch.object(media, "_request", return_value=(first, "")) as request:
        assert len(media._load_source(WRITER, NOW)[0]) == 1
    request.assert_called_once_with(WRITER.url, WRITER)


def test_history_does_not_stop_before_other_items_on_the_inclusive_cutoff_day():
    now = NOW.replace(hour=0)
    first = writer_page((WRITER_URL, "边界日第一页", "2026-04-06")) + b'<a href="index2.html">next</a>'
    second = writer_page((WRITER_URL.replace("40808385", "40808386"), "边界日第二页", "2026-04-06"))
    with patch.object(media, "_request", side_effect=[(first, ""), (second, "")]):
        assert len(media._load_source(WRITER, now)[0]) == 2


def interview_rss(url, body, title="Guest interview"):
    return (f'<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item><title>{title}</title>'
            f'<link>{url}</link><pubDate>Thu, 01 Oct 2026 10:00:00 +0800</pubDate>'
            f'<description>Published introduction.</description><content:encoded><![CDATA[{body}]]></content:encoded>'
            '</item></channel></rss>').encode()


def test_independent_magazine_keeps_interview_body_without_promoting_other_feed_items():
    source = media.SOURCE_BY_ID["media_thetalks_interviews"]
    body = '<p>' + 'Interviewer asks about the architecture. ' * 5 + '</p><p>' + 'The guest discusses the design. ' * 5 + '</p>'
    rows = media._parse_feed(interview_rss("https://the-talks.com/interview/guest/", body), source, NOW)
    assert len(rows) == 1 and not rows[0]["summary_only"]
    assert rows[0]["category"] == INTERVIEW_CATEGORY
    with patch.object(media, "_request") as request:
        result = media.fetch_extended_article(rows[0])
    request.assert_not_called()
    assert result["status"] == "full" and len(result["paragraphs"]) == 2
    assert media._parse_feed(interview_rss("https://the-talks.com/advert/", body), source, NOW) == []


def test_blog_essays_are_excluded_while_a_long_complete_transcript_remains_readable():
    source = media.SOURCE_BY_ID["media_dwarkesh_interviews"]
    url = "https://www.dwarkesh.com/p/guest"
    section = '<p><strong>Dwarkesh Patel</strong></p><p>A question about the guest work.</p>'
    section += '<p><strong><span>Guest Name</span></strong></p><p>A complete answer from the interviewee.</p>'
    body = '<h2>Sponsors</h2><p>Unrelated advertisement.</p><h2><strong>Transcript</strong></h2>' + section * 120
    rows = media._parse_feed(interview_rss(url, body), source, NOW)
    assert len(rows) == 1 and not rows[0]["summary_only"]
    assert len(rows[0]["feed_paragraphs"]) == 480
    with patch.object(media, "_request") as request:
        detail = media.fetch_extended_article(rows[0])
    request.assert_not_called()
    assert detail["status"] == "full" and len(detail["paragraphs"]) == 480
    assert "advertisement" not in str(detail["paragraphs"])
    assert media._parse_feed(interview_rss(url, body.replace("Transcript", "Essay")), source, NOW) == []
    assert media._parse_feed(interview_rss(url, body.replace("Dwarkesh Patel", "No Host")), source, NOW) == []


def test_transcript_limits_reject_oversize_bodies_instead_of_truncating_them():
    source = media.SOURCE_BY_ID["media_dwarkesh_interviews"]
    section = '<p><strong>Dwarkesh Patel</strong></p><p>Question?</p><p><strong>Guest</strong></p><p>Answer.</p>'
    body = '<h2>Transcript</h2>' + section * 201
    rows = media._parse_feed(interview_rss("https://www.dwarkesh.com/p/guest", body), source, NOW)
    assert rows[0]["summary_only"] and rows[0]["feed_paragraphs"] == []
    assert media._dwarkesh_transcript(body + '<p>' + 'x'*240000 + '</p>') == ""


NEW_INTERVIEW_URLS = {
    "media_thepaper_interviews": "https://www.thepaper.cn/newsDetail_forward_34095826",
    "media_jiemian_interviews": "https://www.jiemian.com/article/15086667.html",
    "media_bjnews_interviews": "https://www.bjnews.com.cn/detail/1780394939168462.html",
    "media_creativeindependent_interviews": "https://thecreativeindependent.com/people/chef-mehreen-karim-on-keeping-the-playful-part-of-you-alive/",
    "media_interviewmagazine_interviews": "https://www.interviewmagazine.com/film/pierce-brosnan-is-relishing-playing-the-anti-bond",
    "media_quanta_interviews": "https://www.quantamagazine.org/in-an-age-of-ai-a-physicist-seeks-what-endures-20260903/",
    "media_lexfridman_interviews": "https://lexfridman.com/andrew-scull-transcript",
}


@pytest.mark.parametrize("source_id,url", NEW_INTERVIEW_URLS.items())
def test_new_adapters_join_live_interviews_and_preserve_all_response_cache_restrictions(source_id, url):
    source = media.SOURCE_BY_ID[source_id]
    adapter = media.INTERVIEW_ADAPTERS[source_id]
    article = media._article(source, "公开人物访谈", url, NOW.isoformat(), "来源摘要", NOW)
    article["summary_only"] = False
    with patch.object(media, "_request", return_value=(b"public list", "max-age=600")), \
            patch.object(adapter, "load_source", return_value=([article], ["private, no-store"], "部分历史已读取", True)) as load:
        rows, controls, note, incomplete = media._load_source(source, NOW)
    load.assert_called_once_with(b"public list", source, NOW)
    assert len(rows) == 1 and rows[0]["summary_only"] is False
    assert rows[0]["cache_policy"]["store"] is False
    assert rows[0]["cache_policy"]["reuse"] is False
    assert "private" in controls and note == "部分历史已读取"
    assert incomplete is True
    assert source_id in media.LIVE_INTERVIEW_SOURCE_IDS
    assert source_id in media.PUBLIC_ARTICLE_SOURCES


def test_partial_interview_fetch_keeps_verified_rows_and_explicit_incomplete_state():
    source = media.SOURCE_BY_ID["media_thepaper_interviews"]
    article = media._article(source, "公开人物访谈", NEW_INTERVIEW_URLS[source.id], NOW.isoformat(), "来源摘要", NOW)
    article["summary_only"] = False
    with patch.object(media, "_load_source", return_value=([article], "", "部分页面未完成读取", True)):
        feed = media.load_extended_news_feed(source_ids={source.id})
    assert feed["articles"] == [article]
    assert feed["sources"][0]["status"] == "ok"
    assert feed["sources"][0]["count"] == 1
    assert feed["sources"][0]["incomplete"] is True


@pytest.mark.parametrize("source_id,url", NEW_INTERVIEW_URLS.items())
def test_new_interview_list_metadata_can_open_real_body_but_not_arbitrary_source_paths(source_id, url):
    source = media.SOURCE_BY_ID[source_id]
    adapter = media.INTERVIEW_ADAPTERS[source_id]
    article = media._article(source, "公开人物访谈", url, NOW.isoformat(), "来源摘要", NOW)
    article.update(summary_only=False, content_origin="source_summary")
    paragraphs = ["采访者：公开提问。", "受访者：完整回答。"]
    with patch.object(media, "_request", return_value=(b"public article", "no-cache")) as request, \
            patch.object(adapter, "extract_article", return_value=paragraphs):
        detail = media.fetch_extended_article(article)
    request.assert_called_once_with(url, source, article=True)
    assert detail["status"] == "full" and detail["paragraphs"] == paragraphs
    assert detail["content_origin"] == "public_article" and detail["cache_policy"]["reuse"] is False
    arbitrary = "https://" + source.hosts[0] + "/account/settings"
    with patch.object(media.requests, "get") as request:
        with pytest.raises(ValueError, match="范围"):
            media._request(arbitrary, source, article=True)
    request.assert_not_called()


def test_complete_lex_transcript_can_be_reused_without_shortening_and_invalid_body_is_not_full():
    source = media.SOURCE_BY_ID["media_lexfridman_interviews"]
    article = media._article(source, "Andrew Scull 访谈", NEW_INTERVIEW_URLS[source.id], NOW.isoformat(), "访谈介绍", NOW)
    paragraphs = [f"{'Lex Fridman' if i % 2 == 0 else 'Andrew Scull'}: The complete exchange {i}." for i in range(431)]
    article.update(summary_only=False, content_origin="public_article", feed_paragraphs=paragraphs)
    with patch.object(media, "_request") as request:
        detail = media.fetch_extended_article(article)
    request.assert_not_called()
    assert detail["status"] == "full" and detail["paragraphs"] == paragraphs
    article["feed_paragraphs"] = []
    for invalid in ([], ["too long " * 1000], ["paragraph"] * 801):
        with patch.object(media, "_request", return_value=(b"public article", "")), \
                patch.object(media.INTERVIEW_ADAPTERS[source.id], "extract_article", return_value=invalid):
            assert media.fetch_extended_article(article)["status"] != "full"
