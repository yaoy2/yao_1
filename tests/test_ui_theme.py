"""Theme integration checks without a server, accounts, or production writes."""

import ast
import re
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from utils import home_theme, ui_theme


ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted((ROOT / "pages").glob("*.py"))


def _call_name(statement):
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
        return ast.unparse(statement.value.func)
    return None


@pytest.mark.parametrize("page", PAGES, ids=lambda path: path.stem)
def test_every_toolbox_page_initializes_theme_before_auth_or_content(page):
    tree = ast.parse(page.read_text(encoding="utf-8"))
    bodies = [tree.body, *(n.body for n in tree.body if isinstance(n, ast.FunctionDef))]
    configured = 0
    for body in bodies:
        for index, statement in enumerate(body):
            if _call_name(statement) == "st.set_page_config":
                configured += 1
                assert _call_name(body[index + 1]) == "render_home_link"
    assert configured == 1


def test_native_theme_matches_shared_colors_in_every_launch_directory():
    tokens = (ROOT / "utils/theme_tokens.css").read_text(encoding="utf-8")
    colors = dict(re.findall(r"--colors-([\w-]+):\s*(#[\da-f]+);", tokens))
    expected = {
        "base": "light",
        "primaryColor": colors["primary"],
        "backgroundColor": colors["canvas"],
        "secondaryBackgroundColor": colors["canvas-parchment"],
        "textColor": colors["ink"],
        "font": "sans-serif",
    }
    for directory in (ROOT, ROOT / "Deepself", ROOT / "115-ai-organizer"):
        config = tomllib.loads((directory / ".streamlit/config.toml").read_text(encoding="utf-8"))
        assert config["theme"] == expected, directory


def test_independent_apps_use_the_theme_without_toolbox_navigation():
    for relative in ("wechat_app.py", "Deepself/app.py", "115-ai-organizer/app/web.py"):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        configured = next(i for i, n in enumerate(tree.body) if _call_name(n) == "st.set_page_config")
        initialization = tree.body[configured + 1]
        assert _call_name(initialization) == "apply_global_theme"
        assert ast.literal_eval(initialization.value.keywords[0].value) is False


def test_theme_is_emitted_on_each_rerun_while_css_reads_are_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(ui_theme, "st", SimpleNamespace(markdown=lambda body, **kw: calls.append(body)))
    ui_theme.apply_global_theme(include_sidebar=False)
    ui_theme.apply_global_theme(include_sidebar=False)
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert ui_theme.load_theme_css.cache_info().hits > 0


def test_homepage_uses_same_shell_and_scopes_its_layout(monkeypatch):
    calls = []
    monkeypatch.setattr(home_theme, "st", SimpleNamespace(markdown=lambda body, **kw: calls.append(body)))
    home_theme.apply_home_theme()
    assert ui_theme.load_theme_css() in calls[0]
    css = home_theme._home_css()
    for selector in re.findall(r"([^{}]+)\{", css):
        if selector.strip().startswith("@"):
            continue
        assert all(part.strip().startswith("body:has(.apple-home)") for part in selector.split(","))


def test_navigation_keeps_one_sidebar_and_no_legacy_dark_skin():
    app = AppTest.from_file(str(ROOT / "hello.py"), default_timeout=10).run()
    assert not app.exception
    for target in ("pages/22_23_docker_monitor.py", "pages/21_22_gpt_planner_luna_executor.py", "hello.py"):
        app.switch_page(target).run()
        assert not app.exception
        rendered = "\n".join(element.value for element in app.markdown)
        assert ui_theme.load_theme_css() in rendered
        assert "#05070d" not in rendered
        assert "rgba(57, 223, 247" not in rendered
        assert len(app.sidebar.markdown) == (0 if target == "hello.py" else 1)


@pytest.mark.parametrize("page", ["00_13_llm_budget.py", "02_11_recorder.py", "05_8_budget.py", "14_todos.py"])
def test_locked_pages_render_theme_even_when_auth_stops_execution(page, monkeypatch):
    # No credential lookup, database initialization, or remote sync past the gate.
    from utils import budget_auth

    monkeypatch.setattr(budget_auth, "get_budget_password", lambda *args, **kwargs: "")
    app = AppTest.from_file(str(ROOT / "pages" / page), default_timeout=10).run()
    assert not app.exception
    assert app.warning
    assert len(app.sidebar.markdown) == 1
    assert [button.label for button in app.button] == ["回到主页"]
    assert ui_theme.load_theme_css() in "\n".join(element.value for element in app.markdown)
