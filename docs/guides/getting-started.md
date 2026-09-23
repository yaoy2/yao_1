# Get started / 快速开始

[Project home](../../README.md) · [中文首页](../../README_ZH-CN.md) · [Module catalog](module-catalog.md)

Start with an offline example before configuring a mailbox, model provider, GitHub backup, or file receiver. Both paths below work with fictional content.

## Use the standalone notice editor

1. Open [email_notice_editor.html](../../assets/email_notice_editor.html) on GitHub, choose **Download raw file**, and save it locally.
2. Open the saved HTML in a desktop browser.
3. Follow [Your first notice](first-notice.md). The current template includes institution-specific fields; review them before exporting.

There is no backend or API key for this file. Export creates a local HTML download; it does not send an email.

## Set up the Python environment

The documented launchers target Windows. Use Git and Python 3.11 or newer; current code imports `tomllib`. Dependency resolution needs network access. This minimum is not a claim that every supported Python/OS combination has been tested.

From PowerShell:

```powershell
git clone https://github.com/yaoy2/yao_1.git
cd yao_1
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Alternatively, double-click `首次安装.bat` from the repository. Always run later commands from that repository's root using its virtual-environment Python.

## Run the offline grading demo

```powershell
.\.venv\Scripts\python.exe scripts/demo_grade_workbench.py --output-dir outputs/demo-grade
```

The script creates a small, explicitly fictional class, applies the existing calculation and validation rules, and exports a review workbook. It then reopens the file and checks source scores, coefficients, adjustments, and final results.

- It does not start Streamlit, contact external services, or read application databases.
- Output belongs in a separate demo directory. Existing results are not overwritten.
- A failed verification returns a nonzero exit code. Preserve the error when reporting it.
- Open the generated workbook to inspect how raw inputs lead to the final score.

中文：这是可独立执行的虚构成绩示例，不需要学生名单、邮箱、API Key 或真实业务环境。演示结束后会重新读取 Excel 进行核验；再次运行请选择新的输出目录。

## Open the full toolbox

After installation, double-click `启动YaoYao工具箱.bat`. Start with M15 (notice editing) or read M18 before creating a formal M17 grading task.

For maintainer verification, follow `AGENTS.md`: do not launch a local Streamlit service merely for a screenshot or preview. Use tests and pure-function checks instead.

The [hosted toolbox](https://whatsup.streamlit.app/) uses a separate runtime and storage. Do not enter private records into a deployment you do not administer.

## Configure only the workflow you need

| Workflow | Additional setup |
| --- | --- |
| M15 standalone editor / grading demo | None beyond the selected local runtime. |
| M17 formal grading tasks | A local task directory and source files; follow M18. |
| M08 / M11 / M14 | Shared-access configuration and their respective local storage. |
| Optional GitHub backup | Your own destination repository, branch, and credential, configured outside source code. Explicitly set `GITHUB_BACKUP_REPO` and `GITHUB_BACKUP_BRANCH`; see [destination settings](storage-and-services.md). |
| M24 mail workbench | An authenticated local mail worker and separate review configuration; see [mail guide](mail-jev.md). |
| M25 phone transfer | A paired receiver, running desktop receiving page, and the configured transfer service. It is not available from a clone alone. |
| WeChat archiving | Installed Edge and the separate local archiving window; see [archiving guide](wechat-archiver.md). |

Details about external calls and recovery: [Storage and services](storage-and-services.md).

## Check the setup

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_project_docs_and_setup.py tests/test_grade_workbench.py tests/test_grade_workbench_demo.py tests/test_email_notice_standalone_html.py
```

Run `python -m pytest -q tests` with the same virtual environment for the full main-application suite. Independent projects are not included in that scope. Node.js is optional for running the JavaScript parser check; without it that test is skipped.

If a dependency is missing, confirm which Python executable is running and rerun the environment's requirements installation. Report the failing test and environment; do not treat a partial run as a complete pass.
