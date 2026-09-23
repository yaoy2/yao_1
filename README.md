# YaoYao · Tools for academic work

![YaoYao project overview: prepare, review, and reuse academic work](docs/assets/project-overview.svg)

**English** · [简体中文](README_ZH-CN.md)

[Get started](docs/guides/getting-started.md) · [Module catalog](docs/guides/module-catalog.md) · [Contribute](CONTRIBUTING.md) · [Roadmap](docs/guides/roadmap.md) · [Change log](CHANGELOG_EN.md)

A Python and Streamlit toolbox shaped by everyday work in higher education. It brings notice preparation, teaching assessment, task management, and knowledge capture into one workspace, with reviewable outputs and documented data boundaries.

Maintained by [yaoy2](https://github.com/yaoy2). The repository name remains `yao_1`; existing launchers and module IDs are unchanged.

## Three workflows to explore

| Workflow | What you can inspect | Start here |
| --- | --- | --- |
| **Review teaching assessments** | Keep original group scores, individual coefficients, and adjustments separate; validate inputs and export an Excel review workbook. | [Offline demo](docs/guides/getting-started.md#run-the-offline-grading-demo) · [Calculation and export tests](tests/test_grade_workbench.py) |
| **Prepare a structured notice** | Parse a Chinese notice into fields, review its layout, and export HTML from a single browser file. | [First notice walkthrough](docs/guides/first-notice.md) · [Standalone editor](assets/email_notice_editor.html) |
| **Track work across sessions** | Capture deadlines and notes, retain completed tasks through soft archiving, and merge configured GitHub backups. | [M14 / M10 in the catalog](docs/guides/module-catalog.md) · [Conflict and retry tests](tests/test_todo_chat.py) |

The grading workbench supports human review; it does not replace the person approving results. The notice editor still has institution-specific defaults. Account-backed workflows require their own configuration.

## Start small

**Try a single file.** Download [`email_notice_editor.html`](assets/email_notice_editor.html) and open it in a desktop browser. It needs no Python service, API key, or external JavaScript library. Follow the [walkthrough](docs/guides/first-notice.md) with fictional content and review the institution fields before export.

**Explore the Python project.** Windows launchers are provided. Current code requires Python 3.11 or newer; a broad operating-system and Python-version support matrix has not yet been established.

```powershell
git clone https://github.com/yaoy2/yao_1.git
cd yao_1
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/demo_grade_workbench.py --output-dir outputs/demo-grade
```

The demo uses only fictional records, produces a review workbook, then reads it back to check the calculated results. It needs no credentials and does not read application records. Choose a fresh output directory when rerunning it.

For the full toolbox, use `首次安装.bat`, then `启动YaoYao工具箱.bat`. The [getting-started guide](docs/guides/getting-started.md) explains dependencies, the demo, and feature-specific setup. The [hosted toolbox](https://whatsup.streamlit.app/) is a maintainer deployment; account-backed features are not a shared public sandbox.

## What is in the repository?

The current catalog has **24 entries: Administration 7, Teaching 2, Personal 7, and archived 8**. Sixteen entries are in current sections. Some are read-only guides or showcases; this is not a count of independent applications.

| Area | Examples | Boundary |
| --- | --- | --- |
| Administration | Notice editor, schedule browser, mail workbench, phone transfer | Some modules require local workers, credentials, or a paired receiver. |
| Teaching | Assessment workbench and its guide | Original scores and adjustment layers remain separately inspectable. |
| Personal | Notes, palettes, concept fables, development showcases | Features have distinct storage and backup rules. |
| Archived | Retired tools, including M20 Ding2026 and the former grading workflow | Retained for history; not recommended entry points. |

See the [complete module catalog](docs/guides/module-catalog.md) for every ID, entry point, and status. [`hello.py`](hello.py) is the registration source; the documentation check compares the catalog against it.

```text
hello.py / pages/    Streamlit entry points
utils/              Calculation, parsing, storage, and export logic
assets/             Browser tools and attributed static resources
tests/              Main-application regression tests
scripts/            Demo and maintenance entry points
docs/               Setup, architecture, roadmap, and history
```

The [repository map](docs/repository-structure.md) documents the full layout, including independent projects and data directories.

<details>
<summary>Independent projects and reusable skills</summary>

These projects have their own setup and data boundaries. Cloning the main repository does not start them.

| Project | Purpose and status | Guide |
| --- | --- | --- |
| Deepself | Personal-expression research and a reply tool; original posts and private reports stay local. | [README](Deepself/README.md) |
| Zhongshengshi | Paused Next.js multi-model roundtable proof of concept. | [README](zhongshengshi/README.md) |
| Codex → Grok Builder | Task-scoped coding handoffs with explicit execution boundaries. | [English guide](codex-grok-builder/README_EN.md) |
| GPT Planner · Luna Executor | Planning and execution routes selected for the task. | [English guide](gpt-planner-luna-executor/README_EN.md) |
| 115 AI Organizer | Cloud-file inventory and reviewed organization; execution has its own approval requirements. | [README](115-ai-organizer/README.md) |

The [personal skills collection](personal-skills/README_EN.md) includes presentation creation, comment-photo filtering, and storage analysis. Skills must be installed separately; pulling this repository does not update installed copies.

</details>

## Engineering and data boundaries

- **Inspectable results:** assessment exports retain original values and adjustment layers. Missing adjustment reasons produce warnings; not every warning blocks export.
- **Separate runtimes:** Streamlit Cloud, local workers, and independent projects do not share a local filesystem.
- **Explicit external services:** AI rewriting, mail review, GitHub backup, and file transfer require their own configuration. Their data flows are described in the [storage and services guide](docs/guides/storage-and-services.md).
- **Preserved working records:** application databases and backups are business records. The offline demo uses separate synthetic data and refuses to overwrite its existing result.

## Verification and contribution

Run the main application's documented test scope:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
```

For a quick contribution check:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_project_docs_and_setup.py tests/test_grade_workbench.py tests/test_grade_workbench_demo.py tests/test_email_notice_standalone_html.py
```

Independent projects use their own test entry points. Tests that execute the notice editor's JavaScript need Node.js and report a skip if it is unavailable. Maintainer checks use unit tests, pure-function checks, and existing Streamlit AppTest coverage; repository rules prohibit launching a local Streamlit service merely for preview.

[CONTRIBUTING.md](CONTRIBUTING.md) explains where changes belong, how to submit a reproducible issue, and what to verify. The [roadmap](docs/guides/roadmap.md) focuses on portable examples, configurable institutional defaults, input diagnostics, and reproducible setup.

## Project status and licensing

This is an independently maintained, evolving project. The [status note](docs/guides/project-status.md) distinguishes implemented functionality, current limitations, and licensing work still to be decided. No adoption figures or funding-program eligibility are claimed.

**Source is public, but no repository-wide open-source license has been selected.** Reuse permissions need to be established before treating the whole repository as open source. Third-party assets retain their own [source attribution](assets/awesome-design-md/SOURCE.md) and [MIT license](assets/awesome-design-md/LICENSE). Business records and private material are outside the intended reusable-code scope.

[Documentation index](docs/README.md) · [English change log](CHANGELOG_EN.md) · [中文更新日志](CHANGELOG_ZH-CN.md)
