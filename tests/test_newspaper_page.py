"""Check the Cloud entry without starting a Streamlit server."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "27_28_newspaper.py"


def test_newspaper_page_registers_component_and_labels_preview():
    app = AppTest.from_file(str(PAGE)).run()
    assert not app.exception
    assert any("M28·Newspaper" in item.value for item in app.markdown)
    assert any("真实新闻采集与私人同步尚未接入" in item.value for item in app.caption)
    assert app.get("component_instance")
    assert (ROOT / "integrations" / "newspaper" / "frontend" / "index.html").is_file()


def test_newspaper_registration_survives_detached_page_execution():
    app = AppTest.from_string(
        "from pathlib import Path\n"
        f"exec(compile(Path({str(PAGE)!r}).read_text(encoding='utf-8'), {str(PAGE)!r}, 'exec'), "
        f"{{'__name__': 'detached_newspaper_page', '__file__': {str(PAGE)!r}}})"
    ).run()
    assert not app.exception
    assert app.get("component_instance")
