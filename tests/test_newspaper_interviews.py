"""Publication boundaries apply equally to live and previously cached interviews."""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import patch

import pytest

from utils import newspaper_sources as media
from utils import newspaper_data as news
from utils.newspaper_interviews import (
    INTERVIEW_CATEGORY, SHANGHAI, has_interview_label, is_recent_interview, retain_interviews, without_expired_interviews,
)


NOW = datetime(2026, 10, 6, 12, tzinfo=SHANGHAI)


def interview(published_at, **changes):
    return {"category": INTERVIEW_CATEGORY, "published_at": published_at, **changes}


@pytest.mark.parametrize("offset, expected", [
    (timedelta(), True), (timedelta(days=-7), True),
    (timedelta(days=-7, seconds=-1), False), (timedelta(seconds=1), False),
])
def test_seven_day_window_has_explicit_inclusive_boundaries(offset, expected):
    assert is_recent_interview(interview((NOW + offset).isoformat()), NOW) is expected


@pytest.mark.parametrize("value", [None, "", "not a date", "2026-10-05", "2026-10-05T12:00:00"])
def test_collection_or_update_never_substitutes_for_publication(value):
    row = interview(value, updated_at=NOW.isoformat(), discovered_at=NOW.isoformat())
    assert not is_recent_interview(row, NOW)


def test_timezone_offsets_represent_the_same_instant_and_other_sections_are_untouched():
    recent = interview(NOW.astimezone(timezone.utc).isoformat())
    old = interview((NOW - timedelta(days=8)).isoformat())
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
    content = writer_page((WRITER_URL, "旧作家访谈", "2026-09-28"),
                          (WRITER_URL.replace("40808385", "40808386"), "未来稿件", "2026-10-07"))
    assert media._parse_chinawriter_interviews(content, WRITER, NOW) == []
    with patch.object(media, "PUBLIC_SOURCES", (WRITER,)), patch.object(media, "INACTIVE_SOURCES", ()), \
         patch.object(media, "_request", return_value=(content, "")), patch.object(media, "_now", return_value=NOW):
        feed = media.load_extended_news_feed()
    assert feed["errors"] == []
    assert feed["sources"][0]["status"] == "ok"
    assert feed["sources"][0]["note"] == "近 7 天暂无新访谈"


@pytest.mark.parametrize("content", [b'<html>login or structure changed</html>',
    writer_page((WRITER_URL, "日期不明", ""))])
def test_missing_list_or_dates_are_reported_as_source_failures(content):
    with pytest.raises(ValueError):
        media._parse_chinawriter_interviews(content, WRITER, NOW)


def test_lifeweek_reads_only_the_interview_list_and_enforces_exact_week():
    row = '{id:273320,title:"作家的文学世界",pubTime:"2026-09-29 12:00:00",contentType:a,summary:"公开导读"}'
    recommended = '{id:999999,title:"推荐广告",pubTime:"2026-10-05 12:00:00",contentType:a}'
    rows = media._parse_lifeweek_interviews(lifeweek_page(row, recommended), LIFEWEEK, NOW)
    assert len(rows) == 1
    assert rows[0]["url"] == "https://www.lifeweek.com.cn/article/273320"
    assert rows[0]["summary_only"] is True
    assert rows[0]["category"] == INTERVIEW_CATEGORY
    assert rows[0]["summary"] == "公开导读"
    assert media._parse_lifeweek_interviews(lifeweek_page(row.replace("12:00:00", "11:59:59")), LIFEWEEK, NOW) == []
    assert media._parse_lifeweek_interviews(lifeweek_page(row.replace("2026-09-29", "2026-10-07")), LIFEWEEK, NOW) == []
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
    assert media._article(source, "专访企业家", row["url"], (NOW-timedelta(days=8)).isoformat(), "", NOW) is None
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
                    (url.replace("12345", "12348"), "旧采访", "专访运动员", "2026-9-28 18:00"))
    rows = media._parse_chinanews_interviews(page, source, NOW)
    assert len(rows) == 2
    assert rows[0]["published_at"] == "2026-10-05T20:48:00+08:00"
    assert all(row["group"] == "人物与访谈" and not row["summary_only"] for row in rows)
    with patch.object(media, "_request", return_value=(page, "max-age=120")):
        loaded, _ = media._load_source(source, NOW)
    assert loaded[0]["cache_policy"]["max_age_seconds"] == 120


def test_cctv_full_programs_use_web_release_stamp_and_never_fetch_video_or_claim_full_text():
    source = media.SOURCE_BY_ID["media_cctv_dialogue"]
    url = "https://tv.cctv.com/2026/10/05/VIDEexample261005.shtml"
    row = {"mode": 0, "title": "《对话》企业家的创新探索", "brief": "本期节目对话企业创始人。", "url": url,
           "time": "2026-09-20 21:30:00", "focus_date": int((NOW-timedelta(days=1)).timestamp()*1000)}
    payload = {"data": {"list": [row, {**row, "mode": 1}, {**row, "title": "精彩预告"},
                                   {**row, "focus_date": int((NOW-timedelta(days=8)).timestamp()*1000)},
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
               "published_at": (NOW-timedelta(days=8)).isoformat()}
    with patch.object(news, "_fetch_bytes", return_value=b"unused"), patch.object(news, "_parse_rss", return_value=[expired, recent]):
        assert [row["id"] for row in news._load_source(source, NOW)] == [recent["id"]]
