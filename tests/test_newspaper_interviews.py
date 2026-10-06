"""Publication boundaries apply equally to live and previously cached interviews."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from utils import newspaper_sources as media
from utils.newspaper_interviews import (
    INTERVIEW_CATEGORY, SHANGHAI, is_recent_interview, without_expired_interviews,
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
