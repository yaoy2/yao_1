"""Exercise the component event bridge without network or a Streamlit server."""

from copy import deepcopy
import importlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

import utils.newspaper_component as component


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "27_28_newspaper.py"
KEY = "newspaper-live-v1"
ARTICLE = {
    "id": "news-test-1",
    "title": "测试用公开新闻",
    "url": "https://www.chinanews.com.cn/gn/2026/10-04/fixture.shtml",
    "source": "中新网",
    "published_at": "2026-10-04T08:30:00+08:00",
    "time": "2026-10-04 08:30",
    "summary": "测试摘要",
    "category": "时政要闻",
    "group": "时政与国防",
    "kind": "报道",
}
FEED = {
    "articles": [ARTICLE],
    "sources": [{"name": "中新网", "status": "ok", "count": 1}],
    "errors": [],
    "fetched_at": "2026-10-04T08:45:00+08:00",
}


@pytest.fixture(autouse=True)
def isolate_public_source_caches(monkeypatch):
    def clear():
        component._complete_newspaper_feed.clear()
        component._recent_newspaper_feed.clear()
        component._complete_ai_official_feed.clear()
        component._recent_ai_official_feed.clear()

    clear()
    monkeypatch.setattr(component, "load_extended_news_feed", Mock(return_value={
        "articles": [], "sources": [], "errors": [],
    }))
    yield
    clear()


@pytest.fixture
def service(monkeypatch):
    feed = Mock(return_value=deepcopy(FEED))
    detail = Mock(return_value={"id": ARTICLE["id"], "status": "full", "paragraphs": ["正文"]})
    monkeypatch.setattr(component, "cached_newspaper_feed", feed)
    monkeypatch.setattr(component, "cached_newspaper_article", detail)
    return feed, detail


def component_args(app):
    return json.loads(app.get("component_instance")[0].proto.json_args)


def test_newspaper_page_passes_real_source_metadata(service):
    app = AppTest.from_file(str(PAGE)).run()
    assert not app.exception
    assert any("M28·Newspaper" in item.value for item in app.markdown)
    assert any("公开新闻与 AI 专版" in item.value for item in app.caption)
    assert component_args(app)["feed"]["articles"][0]["url"] == ARTICLE["url"]
    assert (ROOT / "integrations" / "newspaper" / "frontend" / "index.html").is_file()


def test_newspaper_registration_survives_detached_page_execution(service):
    app = AppTest.from_string(
        "from pathlib import Path\n"
        f"exec(compile(Path({str(PAGE)!r}).read_text(encoding='utf-8'), {str(PAGE)!r}, 'exec'), "
        f"{{'__name__': 'detached_newspaper_page', '__file__': {str(PAGE)!r}}})"
    ).run()
    assert not app.exception
    assert app.get("component_instance")


def test_page_refreshes_a_retained_legacy_service_only_once(service, monkeypatch):
    monkeypatch.setattr(component, "NEWSPAPER_SERVICE_VERSION", 0)

    def upgrade(module):
        assert module is component
        module.NEWSPAPER_SERVICE_VERSION = 3
        return module

    reload_service = Mock(side_effect=upgrade)
    monkeypatch.setattr(importlib, "reload", reload_service)
    app = AppTest.from_file(str(PAGE)).run()
    assert not app.exception
    assert component_args(app)["feed"]["articles"] == FEED["articles"]
    app.run()
    assert not app.exception
    reload_service.assert_called_once_with(component)


def test_read_uses_displayed_feed_and_does_not_replay_nonce(service):
    feed, detail = service
    app = AppTest.from_file(str(PAGE)).run()
    feed.return_value = {**deepcopy(FEED), "articles": []}
    app.session_state[KEY] = {"action": "read", "id": ARTICLE["id"], "nonce": "read-1"}
    app.run()
    assert not app.exception
    detail.assert_called_once_with(ARTICLE)
    assert feed.call_count == 1  # A click must not silently swap the displayed feed.
    assert component_args(app)["article_detail"]["status"] == "full"
    app.run()
    assert not app.exception
    detail.assert_called_once()


def test_browser_url_or_unknown_id_cannot_trigger_fetch(service):
    _, detail = service
    app = AppTest.from_file(str(PAGE)).run()
    app.session_state[KEY] = {
        "action": "read", "id": "unknown", "nonce": "bad-1", "url": "http://127.0.0.1/secret"
    }
    app.run()
    assert not app.exception
    detail.assert_not_called()
    assert component_args(app)["article_detail"]["status"] == "summary"


def test_malformed_event_does_not_break_page_or_fetch_article(service):
    _, detail = service
    app = AppTest.from_file(str(PAGE)).run()
    app.session_state[KEY] = {"action": ["read"], "id": ARTICLE["id"], "nonce": "bad-type"}
    app.run()
    assert not app.exception
    detail.assert_not_called()


def test_failed_refresh_keeps_last_success_and_throttles_repeat(service):
    feed, _ = service
    app = AppTest.from_file(str(PAGE)).run()
    feed.return_value = {
        "articles": [], "sources": [{"name": "中新网", "status": "error", "count": 0}],
        "errors": ["来源暂不可用"], "fetched_at": "2026-10-04T09:00:00+08:00",
    }
    app.session_state[KEY] = {"action": "refresh", "nonce": "refresh-1"}
    app.run()
    assert not app.exception
    result = component_args(app)
    assert result["feed"]["articles"] == FEED["articles"]
    assert result["feed"]["stale"] is True
    assert result["feed"]["fetched_at"] == FEED["fetched_at"]
    assert result["feed"]["attempted_at"] == "2026-10-04T09:00:00+08:00"
    app.session_state[KEY] = {"action": "refresh", "nonce": "refresh-2"}
    app.run()
    assert not app.exception
    feed.clear.assert_called_once()
    assert "稍后" in component_args(app)["request_message"]


def test_initial_source_failure_is_real_empty_state(service):
    feed, _ = service
    feed.side_effect = RuntimeError("transport internals must not appear")
    app = AppTest.from_file(str(PAGE)).run()
    assert not app.exception
    result = component_args(app)["feed"]
    assert result["articles"] == []
    assert result["errors"]
    assert "transport internals" not in str(result)


def test_article_transport_failure_returns_readable_error(service):
    _, detail = service
    detail.side_effect = RuntimeError("network failed")
    app = AppTest.from_file(str(PAGE)).run()
    app.session_state[KEY] = {"action": "read", "id": ARTICLE["id"], "nonce": "read-error"}
    app.run()
    assert not app.exception
    result = component_args(app)["article_detail"]
    assert result["id"] == ARTICLE["id"]
    assert result["status"] == "error"
    assert "原文" in result["message"]


def test_transient_article_failure_is_not_retained_in_long_cache(monkeypatch):
    component.cached_newspaper_article.clear()
    fetch = Mock(side_effect=[
        {"id": ARTICLE["id"], "status": "error", "paragraphs": []},
        {"id": ARTICLE["id"], "status": "full", "paragraphs": ["恢复后的公开正文"]},
    ])
    monkeypatch.setattr(component, "fetch_newspaper_article", fetch)
    try:
        with pytest.raises(RuntimeError, match="temporarily unavailable"):
            component.cached_newspaper_article(ARTICLE)
        result = component.cached_newspaper_article(ARTICLE)
        assert result["status"] == "full"
        assert fetch.call_count == 2
    finally:
        component.cached_newspaper_article.clear()


def test_official_ai_summary_does_not_fetch_original_site(monkeypatch):
    component.cached_newspaper_article.clear()
    official = {**ARTICLE, "id": "ai_official_test", "source_family": "ai_official",
                "summary_only": True}
    public_fetch = Mock()
    ai_summary = Mock(return_value={"id": official["id"], "status": "summary",
                                    "paragraphs": ["官方 RSS 摘要"]})
    monkeypatch.setattr(component, "fetch_newspaper_article", public_fetch)
    monkeypatch.setattr(component, "fetch_ai_official_article", ai_summary)
    try:
        assert component.cached_newspaper_article(official)["status"] == "summary"
        ai_summary.assert_called_once_with(official)
        public_fetch.assert_not_called()
    finally:
        component.cached_newspaper_article.clear()


def test_combined_feed_preserves_official_metadata_and_deduplicates_urls(monkeypatch):
    component.cached_newspaper_feed.clear()
    official = {**ARTICLE, "id": "ai_official_test", "url": "https://openai.com/index/test",
                "source_family": "ai_official", "ai_category": "ai-models", "summary_only": True}
    monkeypatch.setattr(component, "load_newspaper_feed", Mock(return_value=deepcopy(FEED)))
    monkeypatch.setattr(component, "cached_ai_official_feed", Mock(return_value={
        "articles": [official, {**official, "id": "duplicate"}],
        "sources": [{"id": "official", "status": "ok", "count": 2}], "errors": [],
    }))
    try:
        result = component.cached_newspaper_feed()
        assert result["articles"] == [ARTICLE, official]
        assert len(result["sources"]) == 2
        assert not result["errors"]
    finally:
        component.cached_newspaper_feed.clear()


def test_one_feed_failure_does_not_remove_other_public_articles(monkeypatch):
    component.cached_newspaper_feed.clear()
    monkeypatch.setattr(component, "load_newspaper_feed", Mock(return_value=deepcopy(FEED)))
    monkeypatch.setattr(component, "cached_ai_official_feed", Mock(side_effect=RuntimeError("private internals")))
    try:
        result = component.cached_newspaper_feed()
        assert result["articles"] == [ARTICLE]
        assert result["errors"]
        assert "private internals" not in str(result)
    finally:
        component.cached_newspaper_feed.clear()


def test_failed_ai_feed_retries_after_refresh_instead_of_waiting_two_hours(monkeypatch):
    failure = {"articles": [], "sources": [{"id": "official", "status": "error"}],
               "errors": ["公开来源暂不可用"]}
    recovered = {"articles": [{**ARTICLE, "id": "ai-recovered",
                               "url": "https://openai.com/index/recovered"}],
                 "sources": [{"id": "official", "status": "ok"}], "errors": []}
    fetch = Mock(side_effect=[failure, recovered])
    monkeypatch.setattr(component, "load_ai_official_feed", fetch)
    monkeypatch.setattr(component, "load_newspaper_feed", Mock(return_value=deepcopy(FEED)))
    first = component.cached_newspaper_feed()
    assert first["errors"]
    assert component.cached_newspaper_feed() == first
    assert fetch.call_count == 1  # Share the brief retry window across viewers.
    component.cached_newspaper_feed.clear()
    second = component.cached_newspaper_feed()
    assert not second["errors"]
    assert [item["id"] for item in second["articles"]] == [ARTICLE["id"], "ai-recovered"]
    assert fetch.call_count == 2
    component.cached_newspaper_feed.clear()
    assert component.cached_newspaper_feed()["articles"] == second["articles"]
    assert fetch.call_count == 2  # Successful AI batches keep their longer cache.


def test_partial_ai_failure_is_also_retried(monkeypatch):
    partial = {"articles": [ARTICLE], "sources": [{"id": "a", "status": "ok"},
                 {"id": "b", "status": "error"}], "errors": []}
    complete = {**partial, "sources": [{"id": "a", "status": "ok"},
                                      {"id": "b", "status": "ok"}]}
    fetch = Mock(side_effect=[partial, complete])
    monkeypatch.setattr(component, "load_ai_official_feed", fetch)
    assert component.cached_ai_official_feed() == partial
    component.cached_newspaper_feed.clear()
    assert component.cached_ai_official_feed() == complete
    assert fetch.call_count == 2


def test_extended_sources_merge_and_route_to_their_reader(monkeypatch):
    extended = {**ARTICLE, "id": "media-test", "source_family": "public_media",
                "url": "https://www.yicai.com/news/fixture.html"}
    monkeypatch.setattr(component, "load_newspaper_feed", Mock(return_value=deepcopy(FEED)))
    monkeypatch.setattr(component, "cached_ai_official_feed", Mock(return_value={
        "articles": [], "sources": [], "errors": []}))
    monkeypatch.setattr(component, "load_extended_news_feed", Mock(return_value={
        "articles": [extended], "sources": [{"id": "media", "status": "ok"}], "errors": []}))
    result = component.cached_newspaper_feed()
    assert result["articles"] == [ARTICLE, extended]
    assert len(result["sources"]) == 2
    reader = Mock(return_value={"id": extended["id"], "status": "full", "paragraphs": ["公开正文"]})
    old_reader = Mock()
    monkeypatch.setattr(component, "fetch_extended_article", reader)
    monkeypatch.setattr(component, "fetch_newspaper_article", old_reader)
    component.cached_newspaper_article.clear()
    assert component.cached_newspaper_article(extended)["status"] == "full"
    reader.assert_called_once_with(extended)
    old_reader.assert_not_called()


def test_publisher_no_reuse_policy_survives_both_combined_cache_layers(monkeypatch):
    def feed_with_id(article_id):
        return {"articles": [{**ARTICLE, "id": article_id,
                              "url": "https://openai.com/index/" + article_id}],
                "sources": [{"id": "official", "status": "ok"}], "errors": [],
                "cache_policy": {"store": True, "reuse": False}}

    fetch = Mock(side_effect=[feed_with_id("first"), feed_with_id("second")])
    monkeypatch.setattr(component, "load_ai_official_feed", fetch)
    monkeypatch.setattr(component, "load_newspaper_feed", Mock(return_value=deepcopy(FEED)))
    first = component.cached_newspaper_feed()
    second = component.cached_newspaper_feed()
    assert first["cache_policy"]["reuse"] is False
    assert second["cache_policy"]["reuse"] is False
    assert first["articles"][-1]["id"] == "first"
    assert second["articles"][-1]["id"] == "second"
    assert fetch.call_count == 2


def test_article_no_reuse_policy_returns_content_without_retaining_it(monkeypatch):
    article = {**ARTICLE, "id": "media-no-reuse", "source_family": "public_media"}
    fetch = Mock(side_effect=[
        {"id": article["id"], "status": "full", "paragraphs": ["第一版正文"],
         "cache_policy": {"store": True, "reuse": False}},
        {"id": article["id"], "status": "full", "paragraphs": ["更新后的正文"],
         "cache_policy": {"store": True, "reuse": False}},
    ])
    monkeypatch.setattr(component, "fetch_extended_article", fetch)
    component.cached_newspaper_article.clear()
    assert component.cached_newspaper_article(article)["paragraphs"] == ["第一版正文"]
    assert component.cached_newspaper_article(article)["paragraphs"] == ["更新后的正文"]
    assert fetch.call_count == 2


def test_short_publisher_expiry_cannot_be_extended_by_a_one_hour_article_cache(monkeypatch):
    article = {**ARTICLE, "id": "media-short-expiry", "source_family": "public_media"}
    fetch = Mock(return_value={"id": article["id"], "status": "full", "paragraphs": ["公开正文"],
                               "cache_policy": {"store": True, "reuse": True, "max_age_seconds": 60}})
    monkeypatch.setattr(component, "fetch_extended_article", fetch)
    component.cached_newspaper_article.clear()
    assert component.cached_newspaper_article(article)["status"] == "full"
    assert component.cached_newspaper_article(article)["status"] == "full"
    assert fetch.call_count == 2
