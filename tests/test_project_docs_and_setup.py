from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_english_default_documents_match_their_named_versions():
    assert read("README.md") == read("README_EN.md")
    assert read("CHANGELOG.md") == read("CHANGELOG_EN.md")


def test_readmes_cover_current_m19_to_m21_modules():
    chinese = read("README_ZH-CN.md")
    english = read("README_EN.md")
    assert "二十个现存工具模块" in chinese
    assert all(code in chinese for code in ("M19", "M20", "M21"))
    assert "Twenty Current Tool Modules" in english
    assert all(code in english for code in ("M19", "M20", "M21"))


def test_beginner_setup_files_reference_real_entry_points():
    dev_requirements = read("requirements-dev.txt")
    installer = read("首次安装.bat")
    launcher = ROOT / "启动YaoYao工具箱.bat"
    tester = ROOT / "运行测试.bat"
    assert "-r requirements.txt" in dev_requirements
    assert "pytest" in dev_requirements
    assert "requirements-dev.txt" in installer
    assert launcher.exists()
    assert tester.exists()
    assert "streamlit run hello.py" in launcher.read_text(encoding="utf-8")
    assert "-m pytest -q" in tester.read_text(encoding="utf-8")


def test_generated_output_and_dependency_folders_are_ignored():
    ignore = read(".gitignore")
    for pattern in ("outputs/", "node_modules/", ".next/", ".next-build/"):
        assert pattern in ignore


def test_independent_subprojects_have_required_readmes():
    for name in ("Deepself", "zhongshengshi", "codex-grok-builder", "115-ai-organizer"):
        readme = ROOT / name / "README.md"
        assert readme.is_file(), f"{name} is missing README.md"


def test_grok_builder_changelog_language_and_default_files_match():
    grok = ROOT / "codex-grok-builder"
    changelog = grok / "CHANGELOG.md"
    english = grok / "CHANGELOG_EN.md"
    chinese = grok / "CHANGELOG_ZH-CN.md"
    assert changelog.is_file()
    assert english.is_file()
    assert chinese.is_file()
    assert changelog.read_text(encoding="utf-8") == english.read_text(encoding="utf-8")


def test_roster_artifact_ignore_rule_exists():
    ignore = read(".gitignore")
    assert "商业精英挑战赛_最终准确名单_*.md" in ignore
