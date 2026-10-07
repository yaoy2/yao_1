"""Chinese interview adapters keep publication, origin and request boundaries."""

from datetime import datetime, timedelta
import json
from unittest.mock import patch

import pytest

from utils import newspaper_interview_chinese as chinese
from utils import newspaper_sources as media
from utils.newspaper_interviews import INTERVIEW_CATEGORY, SHANGHAI, interview_cutoff


NOW = datetime(2026, 10, 7, 12, tzinfo=SHANGHAI)
PAPER = media.PublicSource("media_thepaper_interviews", "澎湃新闻·思想市场", "https://www.thepaper.cn/list_25483",
                           ("www.thepaper.cn",), INTERVIEW_CATEGORY, "chinese_interviews", 184)
JIEMIAN = media.PublicSource("media_jiemian_interviews", "界面新闻·文化", "https://m.jiemian.com/lists/130_1.html",
                             ("m.jiemian.com", "www.jiemian.com"), INTERVIEW_CATEGORY, "chinese_interviews", 184)
BJNEWS = media.PublicSource("media_bjnews_interviews", "新京报·书评周刊", "https://www.bjnews.com.cn/culture",
                            ("www.bjnews.com.cn", "m.bjnews.com.cn"), INTERVIEW_CATEGORY, "chinese_interviews", 184)


def qa(label):
    return (f"<p><strong>{label}：</strong>你的研究从哪里开始？</p><p><strong>受访者：</strong>{'这是来源实际提供的第一段完整回答。' * 10}</p>"
            f"<p><strong>{label}：</strong>这段经历带来了什么影响？</p><p><strong>受访者：</strong>{'这是来源实际提供的第二段完整回答。' * 10}</p>")


def paper_row(identifier="1001", **changes):
    return {"contId": identifier, "name": "人物专访：成长与阅读", "originalFlag": "1", "contType": 0,
            "publishTime": "2026-10-06 10:55:00", "paywalled": False, "trackArticleType": "文章", **changes}


def paper_list(rows, has_next=False):
    value = {"props": {"pageProps": {"data": {"list": rows, "hasNext": has_next}}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(value, ensure_ascii=False)}</script>'.encode()


def paper_detail(**changes):
    item = {"name": "人物专访：成长与阅读", "source": "澎湃新闻", "originalFlag": "1", "contType": 0,
            "pubTime": "2026-10-06 10:55", "content": qa("澎湃新闻"), **changes}
    value = {"props": {"pageProps": {"detailData": {"contentDetail": item}}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(value, ensure_ascii=False)}</script>'.encode()


def jiemian_list(identifiers, next_url="", titles=None):
    cards = "".join(f'<div class="news-view"><h3><a href="https://m.jiemian.com/article/{identifier}.html">'
                    f'{titles[index] if titles else "专访学者" + str(identifier)}</a></h3>'
                    '<div class="news-footer"><span>09/15 11:00</span></div></div>'
                    for index, identifier in enumerate(identifiers))
    return (f'<div class="news-list">{cards}</div>' + (f'<a href="{next_url}">下一页</a>' if next_url else "")).encode()


def jiemian_detail(published="2026/09/15 11:00", *, origin="界面新闻", body=None, duplicate=False, epoch=False):
    clock = f'<span data-article-publish-time="{published}"></span>' if epoch else f"<span>{published}</span>"
    content = f'<div class="article-content">{qa("界面文化") if body is None else body}</div>'
    return (f'<h1>专访学者：自然与写作</h1><div class="article-info">{clock}<span>来源：{origin}</span></div>'
            + content + (content if duplicate else "")).encode()


def bjnews_list(identifier="2001", title="提问为什么重要", summary="这是一场圆桌对话，我们邀请不同领域的受访者回答。", next_url=""):
    return (f'<div class="pin_demo"><a href="https://www.bjnews.com.cn/detail/{identifier}.html"><div class="pin_tit">{title}</div></a>'
            f'<div class="pin_tips">{summary}</div></div>' + (f'<a href="{next_url}">下一页</a>' if next_url else "")).encode()


def bjnews_detail(published="2026-06-02 18:08", *, body=None):
    return (f'<h1>提问为什么重要</h1><div class="employ-line"><span class="timer">{published}</span></div>'
            f'<div id="contentStr"><div class="content-name">{qa("新京报") if body is None else body}</div>'
            '<ul class="Recommended-below"><li>无关推荐不进入正文</li></ul></div>').encode()


@pytest.mark.parametrize("source,url", [
    (PAPER, "https://www.thepaper.cn/newsDetail_forward_1001"),
    (JIEMIAN, "https://www.jiemian.com/article/1001.html"),
    (BJNEWS, "https://www.bjnews.com.cn/detail/1780394939168462.html"),
])
def test_only_exact_canonical_public_article_paths_are_allowed(source, url):
    assert chinese.allows_article_url(source, url)
    for invalid in (url + "?redirect=https://evil.test/", url + "#part", url.replace("https:", "http:"),
                    url.replace("www.", "m."), url.replace(".cn/", ".cn.evil.test/"),
                    url.replace("/article/", "/video/"), "https://www.thepaper.cn/list_25483"):
        if invalid != url:
            assert not chinese.allows_article_url(source, invalid)
    assert not chinese.allows_article_url(PAPER if source != PAPER else JIEMIAN, url)


def test_paper_list_uses_original_text_type_and_absolute_publication_only():
    rows = [paper_row(), paper_row("1002", originalFlag="0"), paper_row("1003", contType=1),
            paper_row("1004", paywalled=True), paper_row("1005", isOutForward="1"),
            paper_row("1006", publishTime="3小时前", pubTime="3小时前", updateTime=NOW.isoformat()),
            paper_row("1007", publishTime="2026-04-07 11:59:59"),
            paper_row("1008", publishTime="2026-10-08 00:00:00"),
            paper_row("1009", name="讲座预告｜对谈学者"), paper_row("1010", name="普通人物报道")]
    with patch.object(media, "_request") as request:
        articles, controls, note, incomplete = chinese.load_source(paper_list(rows, True), PAPER, NOW)
    assert len(articles) == 1
    assert articles[0]["published_at"] == "2026-10-06T10:55:00+08:00"
    assert articles[0]["summary_only"] is False and articles[0]["feed_paragraphs"] == []
    assert controls == [] and "未作为半年完整归档" in note
    assert incomplete is False
    request.assert_not_called()


def test_paper_list_accepts_explicit_publication_epoch_but_not_update_epoch():
    stamp = int((NOW - timedelta(days=1)).timestamp() * 1000)
    result, _, _, _ = chinese.load_source(paper_list([paper_row(publishTime=None, pubTimeLong=stamp)]), PAPER, NOW)
    assert result[0]["published_at"] == (NOW - timedelta(days=1)).isoformat()
    empty, _, _, _ = chinese.load_source(paper_list([paper_row(publishTime=None, updateTime=stamp)]), PAPER, NOW)
    assert empty == []


def test_paper_empty_list_is_valid_but_an_unrecognized_page_is_not():
    assert chinese.load_source(paper_list([]), PAPER, NOW)[0] == []
    with pytest.raises(ValueError, match="列表格式"):
        chinese.load_source(b'<h1>temporary site page</h1>', PAPER, NOW)


@pytest.mark.parametrize("changes", [
    {"source": "文学报"}, {"originalFlag": "0"}, {"contType": 1}, {"paywalled": True},
    {"podcastAudioUrl": "https://example.org/a.mp3"},
    {"content": "<p>只有一段视频简介。</p>"},
    {"content": qa("澎湃新闻") + "<p>购买后阅读全文</p>"},
    {"content": "<p>本文节选自另一机构出版的访谈集。</p>" + qa("澎湃新闻")},
])
def test_paper_body_rejects_reprints_video_teasers_and_restricted_content(changes):
    assert chinese.extract_article(paper_detail(**changes), PAPER) == []


def test_paper_extracts_actual_questions_and_answers_without_generated_text():
    result = chinese.extract_article(paper_detail(), PAPER)
    assert len(result) == 4
    assert result[0] == "澎湃新闻： 你的研究从哪里开始？"
    assert result[-1].endswith("这是来源实际提供的第二段完整回答。" * 10)


def test_jiemian_confirms_year_and_body_in_details_instead_of_guessing_from_list():
    stamp = str(int((NOW - timedelta(days=2)).timestamp()))
    with patch.object(media, "_request", return_value=(jiemian_detail(stamp, epoch=True), "private, no-store")) as request:
        result, controls, _, incomplete = chinese.load_source(jiemian_list([3001]), JIEMIAN, NOW)
    assert len(result) == 1 and len(result[0]["feed_paragraphs"]) == 4
    assert result[0]["published_at"] == (NOW - timedelta(days=2)).isoformat()
    assert result[0]["summary_only"] is False
    assert result[0]["content_origin"] == "public_article"
    assert controls == ["private, no-store"]
    assert incomplete is False
    request.assert_called_once_with("https://www.jiemian.com/article/3001.html", JIEMIAN, article=True)


def test_jiemian_extracts_one_body_and_requires_publisher_origin():
    assert len(chinese.extract_article(jiemian_detail(duplicate=True), JIEMIAN)) == 4
    assert chinese.extract_article(jiemian_detail(origin="转载媒体"), JIEMIAN) == []
    ordinary = "<p>这是关于采访技巧的普通文章。</p>" * 20
    assert chinese.extract_article(jiemian_detail(body=ordinary), JIEMIAN) == []


def test_bjnews_roundtable_uses_published_timer_and_ignores_recommendations():
    with patch.object(media, "_request", return_value=(bjnews_detail(), "max-age=60")):
        result, controls, _, incomplete = chinese.load_source(bjnews_list(), BJNEWS, NOW)
    assert len(result) == 1 and result[0]["published_at"] == "2026-06-02T18:08:00+08:00"
    assert len(result[0]["feed_paragraphs"]) == 4
    assert all("无关推荐" not in line for line in result[0]["feed_paragraphs"])
    assert controls == ["max-age=60"]
    assert incomplete is False


@pytest.mark.parametrize("source,page,detail", [
    (JIEMIAN, jiemian_list([3001]), jiemian_detail("09/15 11:00")),
    (BJNEWS, bjnews_list("1780394939168462"), bjnews_detail("")),
    (BJNEWS, bjnews_list(), bjnews_detail("2026-10-08 18:08")),
    (BJNEWS, bjnews_list(), bjnews_detail("2026-04-06 18:08")),
])
def test_unknown_old_and_future_publication_are_never_replaced_with_collection_time(source, page, detail):
    with patch.object(media, "_request", return_value=(detail, "")):
        assert chinese.load_source(page, source, NOW)[0] == []


def test_video_podcast_and_event_previews_never_trigger_body_requests():
    page = bjnews_list(title="对话作家：写作人生", summary="本期为新京报书评周刊出品的视频播客节目。")
    with patch.object(media, "_request") as request:
        assert chinese.load_source(page, BJNEWS, NOW)[0] == []
        assert chinese.load_source(jiemian_list([1, 2], titles=["【视频】专访作家", "专访作家活动预告"]), JIEMIAN, NOW)[0] == []
    request.assert_not_called()


def test_history_follows_only_observed_fixed_next_links_and_keeps_inclusive_cutoff():
    page2 = "https://m.jiemian.com/lists/130_2.html"
    page3 = "https://m.jiemian.com/lists/130_3.html"
    boundary = interview_cutoff(NOW).strftime("%Y/%m/%d %H:%M")
    replies = [(jiemian_detail(boundary), "max-age=120"),
               (jiemian_list([3002], page3), "max-age=60"),
               (jiemian_detail("2026/04/06 12:00"), "private")]
    with patch.object(media, "_request", side_effect=replies) as request:
        result, controls, _, incomplete = chinese.load_source(jiemian_list([3001], page2), JIEMIAN, NOW)
    assert len(result) == 1
    assert controls == ["max-age=120", "max-age=60", "private"]
    assert incomplete is False
    assert [call.args[0] for call in request.call_args_list] == [
        "https://www.jiemian.com/article/3001.html", page2, "https://www.jiemian.com/article/3002.html"]
    with patch.object(media, "_request", return_value=(jiemian_detail(), "")) as request:
        chinese.load_source(jiemian_list([3001], "https://evil.test/list"), JIEMIAN, NOW)
        assert request.call_count == 1


def test_partial_request_failures_keep_verified_results_but_total_failure_is_not_an_empty_success():
    with patch.object(media, "_request", side_effect=[(jiemian_detail(), "public"), TimeoutError("private connection info")]):
        result, controls, note, incomplete = chinese.load_source(jiemian_list([3001, 3002]), JIEMIAN, NOW)
    assert len(result) == 1 and controls == ["public"]
    assert "部分候选" in note and "private connection" not in note
    assert incomplete is True
    with patch.object(media, "_request", side_effect=TimeoutError("private connection info")):
        with pytest.raises(ValueError, match="暂未完成读取"):
            chinese.load_source(jiemian_list([3001]), JIEMIAN, NOW)


def test_candidate_detail_requests_are_bounded_and_duplicate_cards_are_read_once():
    page = jiemian_list([3001, 3001, *range(3002, 3020)])
    with patch.object(media, "_request", return_value=(jiemian_detail(), "")) as request:
        result, _, note, incomplete = chinese.load_source(page, JIEMIAN, NOW)
    assert request.call_count == chinese.MAX_DETAIL_REQUESTS
    assert len(result) == chinese.MAX_DETAIL_REQUESTS
    assert "数量或时间上限" in note
    assert incomplete is True


@pytest.mark.parametrize("reply", [TimeoutError("temporary failure"), (b'<h1>Changed history layout</h1>', "private")])
def test_history_request_and_format_failures_mark_retained_articles_incomplete(reply):
    page2 = "https://m.jiemian.com/lists/130_2.html"
    with patch.object(media, "_request", side_effect=[(jiemian_detail(), "public"), reply]):
        rows, _, note, incomplete = chinese.load_source(jiemian_list([3001], page2), JIEMIAN, NOW)
    assert len(rows) == 1 and incomplete is True
    assert "历史列表" in note


def test_elapsed_time_marks_retained_articles_incomplete_without_an_extra_request():
    page2 = "https://m.jiemian.com/lists/130_2.html"
    with patch.object(chinese.time, "monotonic", side_effect=[0, 0, chinese.MAX_LOAD_SECONDS]), \
            patch.object(media, "_request", return_value=(jiemian_detail(), "")) as request:
        rows, _, note, incomplete = chinese.load_source(jiemian_list([3001], page2), JIEMIAN, NOW)
    assert len(rows) == 1 and incomplete is True
    assert "时间上限" in note and request.call_count == 1


def test_history_page_limit_is_incomplete_even_when_existing_articles_are_readable():
    with patch.dict(chinese._HISTORY, {JIEMIAN.id: ()}), \
            patch.object(media, "_request", return_value=(jiemian_detail(), "")):
        rows, _, note, incomplete = chinese.load_source(jiemian_list([3001]), JIEMIAN, NOW)
    assert len(rows) == 1 and incomplete is True
    assert "最多检查" in note


def test_extra_feeds_are_fixed_public_history_urls_only():
    assert len(chinese.EXTRA_FEED_URLS) == 40
    assert all(url.startswith(("https://m.jiemian.com/lists/130_", "https://www.bjnews.com.cn/culture/"))
               for url in chinese.EXTRA_FEED_URLS)
    assert PAPER.url not in chinese.EXTRA_FEED_URLS
