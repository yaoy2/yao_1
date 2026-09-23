# Contributing to YaoYao

[Project overview](README.md) · [中文说明](README_ZH-CN.md) · [Roadmap](docs/guides/roadmap.md)

Useful contributions make a real administrative or teaching workflow easier to run, inspect, or maintain. Small reproducible fixes, clearer setup instructions, and tests with fictional data are good starting points.

中文：欢迎围绕具体工作问题贡献。先用虚构数据复现，说明改动前后行为，并附相关验证结果；首次上手见[快速开始](docs/guides/getting-started.md)。

## Before starting

Read [project status and licensing](docs/guides/project-status.md). A repository-wide open-source license has not yet been selected. Do not assume that public visibility grants unrestricted reuse, or submit material you do not have permission to share.

For a substantial feature, open an issue describing the user, problem, proposed result, and how success could be checked. For a small reproducible fix, a focused pull request is enough. Maintainer workflows and coding boundaries are in [AGENTS.md](AGENTS.md).

## Set up and run a safe example

Follow [getting started](docs/guides/getting-started.md). The [grading demo](scripts/demo_grade_workbench.py) provides fictional input and verifies an exported workbook without account configuration.

Never use student records, original mail, staff contact details, credentials, real backups, or private screenshots as public issue attachments or test fixtures. Replace them with the smallest fictional example that reproduces the behavior.

## Where changes belong

| Change | Location |
| --- | --- |
| Streamlit interaction | `pages/`; keep registration in `hello.py` consistent. |
| Calculation, parsing, validation, persistence | `utils/`; prefer logic that can be tested separately from the UI. |
| Main-application regression test | `tests/` with temporary directories and mocked external services. |
| Reusable maintenance or demo command | `scripts/`; document inputs, output locations, and side effects. |
| Current user/developer guide | `docs/guides/` and the [documentation index](docs/README.md). |
| Historical decision or event | `docs/history/`; keep it clearly historical. |
| Independent subproject | Its own directory, rules, dependencies, and tests. |

Preserve existing public entry points and module IDs unless the change specifically calls for a migration. A module catalog change must agree with `hello.py`.

## Verify a change

Use the narrowest meaningful test scope while developing, then run the relevant neighboring tests.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_grade_workbench.py tests/test_grade_workbench_demo.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_project_docs_and_setup.py
```

The full main-application command is `python -m pytest -q tests` using the project environment. Do not run unscoped root pytest: independent applications have separate import and dependency boundaries.

- Report the command, result, and any skipped checks or missing dependencies.
- Reopen exported files when changing an export; in-memory calculations alone do not establish that the saved artifact is correct.
- Use temporary paths; tests must not change real `data/`, backups, or credentials.
- Use existing AppTest or pure-function checks for UI logic. Do not start a local Streamlit server solely for preview.
- Changes to the standalone notice parser should check both Python and JavaScript behavior. The latter requires Node.js.

## Keep documentation reliable

`README.md` mirrors `README_EN.md`; `CHANGELOG.md` mirrors `CHANGELOG_EN.md`. Maintain the corresponding Chinese version when changing public setup, feature boundaries, or usage.

The [module catalog](docs/guides/module-catalog.md) is checked against the actual homepage registrations. Describe retired entries as retired and future work as planned. Do not present a read-only showcase as a live integration.

## Submit for review

Explain the concrete problem, resulting behavior, and relevant verification. Include a small fictional before/after example when it helps. Keep unrelated formatting, generated files, local configuration, and business data out of the diff.

AI-assisted contributions are welcome when the contributor understands the change, verifies it, and accurately reports limitations. External services must not receive private fixtures or credentials as part of a test.
