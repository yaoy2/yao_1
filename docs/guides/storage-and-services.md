# Storage and external services / 存储与外部服务

[Project home](../../README.md) · [Getting started](getting-started.md)

## Storage, Recovery, and Another Computer

Streamlit Cloud and the local computer are separate runtime environments. The deployed app cannot read this computer's folders or environment variables. A `git pull` retrieves committed files; it does not restore ignored databases, credentials, or private material.

| Feature | Main storage | Recovery and migration |
| --- | --- | --- |
| M08 Budget | `data/budget.db`; `budget_ledger_backup.md/.xlsx` | An empty database can restore from the local Markdown backup; configured GitHub synchronization writes the Markdown backup remotely. |
| M10 Memos | `data/web_memos.db`; `web_memos_backup.md` | Supports backup restoration; configured synchronization merges remote records and protects existing remote content. |
| M14 Todos | `data/todos.db`; `todo_items_backup.md` | Supports backup restoration and remote-record merging when configured; completed items remain through soft archiving. |
| M11 Recorder | `data/ding_minutes.db`; `ding_minutes_cloud.json` | Local scanning stores source text and rewrites; the deployed page reads the cloud export and can synchronize remarks. Consult the migration guide first. |
| M17 Grading | `data/grade_workbench/tasks/<task-ID>/task.db` and task attachments | No automatic GitHub synchronization; retain the complete task directory when migrating and export review workbooks separately. |

`data/` contains business records, not disposable caches. Remote GitHub backups are the meeting point for dynamic data: synchronize before editing local backups, merge conflicts, and never overwrite current records with stale or empty files. Export important material regularly and keep an additional controlled backup.

## Credentials, External Services, and Local Boundaries

- **Shared password**: M08, M11, and M14 use Streamlit Secrets `budget_password` / `[budget].password`; local execution also accepts the `BUDGET_PASSWORD` environment variable.
- **AI rewriting**: Recorder accepts Secrets or local `DEEPSEEK_API_KEY`. Transcript content is sent to the configured API provider when rewriting is requested. Without a key, source text can be registered without generating an AI rewrite.
- **GitHub backup**: enabling `GITHUB_BACKUP_TOKEN` through Secrets or the local environment sends relevant backup content to the configured repository. A local save alone does not mean the data is backed up across computers.
- **Choose your own backup destination:** for a new deployment, explicitly set the environment variables `GITHUB_BACKUP_REPO` (`owner/repository`) and `GITHUB_BACKUP_BRANCH`, or the Streamlit Secrets keys `github_backup_repo` and `github_backup_branch`. Secrets take precedence over environment values. The current fallback is `yaoy2/yao_1` / `main`; providing only a token does not select your repository automatically. Configure a destination you control before enabling synchronization.
- **Local archiving**: WeChat retrieval accesses articles over the network and writes results to confirmed folders. GoogleDrive or similar sync clients may then upload those files. Check destinations before use; do not automatically fill sensitive paths.
- **Deepself**: submitted messages and the abstract style profile pass through the chosen model provider; the app does not read or upload private source posts.
- **Credential handling**: keep real keys in Secrets, environment variables, or the subproject's designated local credential location, never in source code, commits, or logs.


## Mail and phone transfer

- **M24 mail workbench:** a local worker collects and processes mail only after a request. The page exposes collected summaries and review controls; a clone alone does not configure accounts or start a collector. Optional Jev review sends new message text, extracted attachment text, and draft analysis to TypeSafe when enabled. Read [mail setup and data-flow notes](mail-jev.md) before enabling it.
- **M25 phone transfer:** a paired desktop receiver and transfer service are required. The receiving desktop page must remain open; delivery is confirmed after the receiver verifies the file. Temporary server copies and completed local files have different lifetimes. Follow the current page's pairing and delivery status instead of treating an upload click as successful delivery.
- **Offline grading demo:** reads fictional records defined in the script and writes only to its selected demo-output directory. It does not use application databases or configure external services.

## Reuse and business records

The repository contains code and existing operational data conventions. Cloning is not a clean-data deployment recipe. Use fictional fixtures for development and explicitly choose storage and backup destinations for your own deployment. Never add credentials or private business records to an issue, pull request, or demo.

Existing institution names, local paths, backup locations, and third-party assets do not become appropriate defaults for another organization automatically. See [project status and licensing](project-status.md) before reusing the repository.
