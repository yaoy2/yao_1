import ast
from collections import Counter
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_english_default_documents_match_their_named_versions():
    assert read("README.md") == read("README_EN.md")
    assert read("CHANGELOG.md") == read("CHANGELOG_EN.md")


def test_module_catalog_matches_homepage_registry():
    # Read metadata without importing Streamlit or starting application services.
    tree = ast.parse(read("hello.py"))
    assignment = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "TOOLS" for target in node.targets)
    )
    tools = ast.literal_eval(assignment.value)
    catalog = read("docs/guides/module-catalog.md")
    rows = [
        [cell.strip() for cell in line.strip("|").split("|")]
        for line in catalog.splitlines()
        if re.match(r"^\| M\d{2} \|", line)
    ]
    assert len(rows) == len(tools), "Catalog must document every registered entry exactly once"
    documented = {row[0]: row for row in rows}
    assert len(documented) == len(rows), "Duplicate module IDs in the catalog"
    assert set(documented) == {tool["code"] for tool in tools}
    sections = {"行政": "Administration", "教学": "Teaching", "个人": "Personal", "archived": "Archived"}
    for tool in tools:
        row = documented[tool["code"]]
        assert row[1] == sections[tool["section"]]
        assert row[2] == ("Archived" if tool.get("blocked") else "Current")
        assert f"(../../{tool['page']})" in row[3]
        assert (ROOT / tool["page"]).is_file()

    counts = Counter(tool["section"] for tool in tools)
    for section, count in counts.items():
        assert f"| {sections[section]} | {count} |" in catalog
    for filename in ("README_EN.md", "README_ZH-CN.md"):
        assert "(docs/guides/module-catalog.md)" in read(filename)
    assert f"{len(tools)} entries" in read("README_EN.md")
    assert f"{len(tools)} 个入口" in read("README_ZH-CN.md")


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
    assert "-m pytest -q tests" in tester.read_text(encoding="utf-8")


def test_codespaces_uses_the_existing_main_application():
    import json
    import shlex

    # The checked-in devcontainer file permits full-line JSON comments.
    config_text = read(".devcontainer/devcontainer.json")
    config = json.loads("\n".join(
        line for line in config_text.splitlines()
        if not line.lstrip().startswith("//")
    ))
    for name in config["customizations"]["codespaces"]["openFiles"]:
        assert (ROOT / name).is_file(), f"Codespaces opens a missing file: {name}"
    command = shlex.split(config["postAttachCommand"]["server"])
    assert command[:2] == ["streamlit", "run"]
    assert command[2] == "hello.py"
    assert (ROOT / command[2]).is_file()


def test_generated_output_and_dependency_folders_are_ignored():
    ignore = read(".gitignore")
    for pattern in ("outputs/", "node_modules/", ".next/", ".next-build/"):
        assert pattern in ignore


def test_independent_subprojects_have_required_readmes():
    for name in ("Deepself", "zhongshengshi", "codex-grok-builder", "115-ai-organizer"):
        readme = ROOT / name / "README.md"
        assert readme.is_file(), f"{name} is missing README.md"
    assert (ROOT / "115-ai-organizer" / "进度.md").is_file()


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
