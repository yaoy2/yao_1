from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_english_default_documents_match_their_named_versions():
    assert read("README.md") == read("README_EN.md")
    assert read("CHANGELOG.md") == read("CHANGELOG_EN.md")


def test_readmes_cover_current_grade_workbench_modules():
    chinese = read("README_ZH-CN.md")
    english = read("README_EN.md")
    assert "十九个工具模块" in chinese
    assert "M19" in chinese and "M18" in chinese and "M17" in chinese and "M16" in chinese
    assert "Nineteen Tool Modules" in english
    assert "M19" in english and "M18" in english and "M17" in english and "M16" in english


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
