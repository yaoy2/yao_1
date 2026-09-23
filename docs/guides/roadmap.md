# Roadmap / 迭代路线图

[Project home](../../README.md) · [Contributing](../../CONTRIBUTING.md) · [Project status](project-status.md)

The priority is to make a small set of useful workflows easier for another person to run and verify. These are development directions, not release dates or promises of funding eligibility.

## Available now

- A single-file notice editor with Python and JavaScript parsing checks.
- An assessment workbench that keeps original scores and adjustment layers inspectable.
- A fictional grading demo that exports a workbook and checks the saved result.
- A documented module catalog, contribution guide, and issue/PR templates.

## Next improvements

| Priority | Work | What completion should demonstrate |
| --- | --- | --- |
| 1 | **Configurable notice templates** | Institution, signing-unit options, number prefix, and year can be configured; existing defaults remain compatible and Python/JavaScript tests agree. |
| 1 | **Clearer grading-input diagnostics** | Invalid numeric input is reported with a field/row explanation instead of being silently normalized to a default; exports preserve the original input for review. |
| 1 | **Repository licensing scope** | The maintainer selects reuse terms for code they can license, records third-party notices, and explicitly separates business records and private material. |
| 2 | **Reproducible first-run setup** | Document tested Python/Windows combinations and actionable dependency errors; verify a fresh environment with the offline demo. |
| 2 | **More fictional workflow examples** | Add mail and backup-conflict examples that run without live accounts, private messages, or network writes. |
| 2 | **Automated contribution checks** | Establish a maintainer-approved CI configuration for relevant tests and documentation checks; publish a build badge only after real checks exist. |

## 中文说明

近期优先解决“他人能否独立上手并复核结果”：机构模板可以配置、输入错误能定位、安装环境能复现、开源授权有明确边界。现有功能不因写入路线图而重新算作新增成果；上表项目完成后应附实际验证，再更新状态。

Potential Codex support would be useful for these bounded maintenance tasks: debugging reproducible failures, expanding regression cases, improving setup instructions, and reviewing export behavior. This is an intended use of support, not a claim that an application has been accepted.
