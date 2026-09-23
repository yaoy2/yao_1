# Project status / 项目状态

As of 2026-09-23. [Project home](../../README.md) · [Roadmap](roadmap.md)

## Scope

YaoYao (`yaoy2/yao_1`) is an independently maintained collection of tools shaped by administrative and teaching work. Its primary application uses Python and Streamlit. The repository also contains independent projects and reusable skills with their own setup requirements.

The code includes tests for calculation, parsing, workbook exports, persistence, conflict handling, and page behavior. The presence of tests does not establish that every environment, service connection, or workflow has been validated.

## Current limits

- Windows setup is documented; current code requires Python 3.11+ because it uses `tomllib`. A full compatibility matrix has not been established.
- The notice editor retains institution-specific defaults and a template-specific notice number.
- Grading adjustments remain visible, but some issues are warnings rather than export blockers. Numeric-input diagnostics need further improvement.
- Mail collection, optional model review, GitHub backup, and phone transfer need their own accounts or running local components. A public clone does not provision them.
- Some modules are read-only showcases; eight catalog entries are retired.
- No verified active-user or download figures are published here, and no funding-program eligibility or approval is claimed.

## Licensing

The repository currently has **no standalone root LICENSE**. Public source visibility should not be read as blanket permission to use, modify, or redistribute all contents.

Before selecting a repository-wide license, the maintainer needs to confirm the scope of code they can authorize, preserve existing third-party terms, and distinguish reusable code from business records and private material.

Known bundled third-party material:

| Path | Source and existing terms |
| --- | --- |
| `assets/awesome-design-md/` | [Pinned upstream source](../../assets/awesome-design-md/SOURCE.md), [MIT license](../../assets/awesome-design-md/LICENSE). |

This is an inventory entry, not a claim that the whole repository has completed a legal review. Choosing a license requires a separate maintainer decision. See [GitHub's licensing guide](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository) for the distinction between public code and licensed reuse.

中文：目前没有覆盖全库的根许可证。第三方素材保留原许可；业务记录和私密材料不应随代码授权。许可选定之前，不将项目描述为已经完成完整开源授权。

## Evidence to inspect

- [Homepage registrations](../../hello.py) and the [module catalog](module-catalog.md).
- [Assessment rules](../../utils/grade_workbench.py), [export logic](../../utils/grade_workbench_export.py), and [regression tests](../../tests/test_grade_workbench.py).
- [Offline grading demo](../../scripts/demo_grade_workbench.py), including saved-file verification.
- [Single-file editor tests](../../tests/test_email_notice_standalone_html.py).
- [Task conflict and retry tests](../../tests/test_todo_chat.py).
- [Commit history](https://github.com/yaoy2/yao_1/commits/main/) and [change log](../../CHANGELOG_EN.md).

Application or project summaries should draw on these inspectable artifacts and distinguish implemented capabilities from the roadmap.
