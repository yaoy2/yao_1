"""Exercise the component event bridge without network or a Streamlit server."""

from copy import deepcopy
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
    assert any("公开新闻聚合" in item.value for item in app.caption)
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
