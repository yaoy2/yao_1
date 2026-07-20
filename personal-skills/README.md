# Personal Codex Skills

这里集中保存个人制作的 Codex Skills。它们维护在 `codex/personal-skills` 分支，不合并到在线 Streamlit 使用的 `main` 分支。

## Skills

| Skill | 用途 | 常用说法 |
|---|---|---|
| `save-xhs-comment-human-images` | 遍历小红书笔记评论区，放大判断图片，只保存以真实人物为主体的照片 | “保存小红书评论区真人照片/图片/图” |

## 使用方式

将目标 Skill 目录复制到 Codex 的个人 Skills 目录后，重新打开任务或刷新 Skill 列表即可使用。Windows 默认个人目录通常为：

```text
%CODEX_HOME%\skills\<skill-name>
```

本机当前使用的对应目录是：

```text
E:\codex\.codex\skills\<skill-name>
```

Skill 也可以通过 `$skill-name` 显式调用；启用隐式调用后，直接说出自然语言触发语即可。
