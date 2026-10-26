"""M31：QQ 归档机器人的公开项目展示，不连接私有接收服务。"""

import streamlit as st

from utils.ui_theme import render_home_link


st.set_page_config(page_title="M31 · QQ 归档机器人", page_icon="🤖", layout="wide")
render_home_link()

st.markdown(
    """
    <style>
      .m31-overview { color: var(--colors-ink); }
      .m31-intro {
        display: flex; flex-wrap: wrap; align-items: center;
        justify-content: space-between; gap: .4rem .8rem;
        padding: .65rem .85rem; margin-bottom: .65rem;
        border: 1px solid var(--colors-hairline);
        border-radius: var(--rounded-lg); background: var(--colors-canvas-parchment);
      }
      .m31-intro p { margin: 0; font-size: .9rem; line-height: 1.5; }
      .m31-badges { display: flex; flex-wrap: wrap; gap: .3rem; }
      .m31-badge {
        padding: .2rem .45rem; border-radius: 6px;
        color: var(--colors-primary); background: var(--colors-primary-soft);
        font-size: .73rem; font-weight: 600;
      }
      .m31-flow {
        display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: .5rem; margin-bottom: .65rem;
      }
      .m31-step {
        padding: .6rem .75rem; border: 1px solid var(--colors-hairline);
        border-radius: var(--rounded-lg); background: var(--colors-canvas);
      }
      .m31-step b { display: block; font-size: .88rem; margin-bottom: .15rem; }
      .m31-step p { margin: 0; color: var(--colors-ink-muted-48); font-size: .8rem; line-height: 1.45; }
      .m31-features { display: grid; grid-template-columns: 1fr 1fr; gap: .45rem .8rem; }
      .m31-feature {
        display: grid; grid-template-columns: 5.4rem minmax(0, 1fr);
        gap: .5rem; padding: .55rem .7rem;
        border-bottom: 1px solid var(--colors-hairline); font-size: .86rem; line-height: 1.5;
      }
      .m31-feature b { color: var(--colors-primary); }
      .m31-feature span { color: var(--colors-ink-muted-48); }
      @media (max-width: 900px) { .m31-flow { grid-template-columns: 1fr 1fr; } }
      @media (max-width: 620px) { .m31-features { grid-template-columns: 1fr; } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("M31 · QQ 归档机器人")
st.caption("项目展示 · 验收记录截至 2026-10-26 · 非实时运行状态")

st.markdown(
    """
    <div class="m31-overview">
      <div class="m31-intro">
        <p><b>把群聊留下来，需要时再整理。</b><br>按群保存新消息与附件，用指令查找资料、生成带来源的 AI 摘要。</p>
        <div class="m31-badges">
          <span class="m31-badge">单群基础归档已验收</span>
          <span class="m31-badge">AI 已接入</span>
          <span class="m31-badge">群内 AI 回复待验收</span>
        </div>
      </div>
      <div class="m31-flow" aria-label="QQ 归档与 AI 整理流程">
        <div class="m31-step"><b>① QQ 群 · 接收</b><p>逐群启用归档，接收平台推送的新消息。</p></div>
        <div class="m31-step"><b>② L 电脑 · 保存</b><p>保留原文、时间和来源，下载图片与文件。</p></div>
        <div class="m31-step"><b>③ DeepSeek Flash · 理解</b><p>群内发送“整理今天”，分析本群当天材料。</p></div>
        <div class="m31-step"><b>④ 群回复与本地报告</b><p>整理摘要、决定、待办和待确认问题，附来源索引。</p></div>
      </div>
      <div class="m31-features">
        <div class="m31-feature"><b>普通发言</b><span>已启用群的新消息无需 @ 即可归档；按群、按日期分开保存，重复事件去重。</span></div>
        <div class="m31-feature"><b>图片与文档</b><span>保存 QQ 推送的附件；AI 可读取常见图片、DOCX、XLSX、文字型 PDF 和文本文件。</span></div>
        <div class="m31-feature"><b>查找资料</b><span>按关键词查消息，列出本群文件，查看归档状态；查询限定在当前群。</span></div>
        <div class="m31-feature"><b>按需理解</b><span>手动触发 AI，提取摘要、决定和待办；未明确的负责人、期限保留为待确认。</span></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("### 在 QQ 群里怎么用")
st.markdown(
    """
先为目标群启用归档并允许接收群内全部消息。发指令时，需在 QQ 中真正选中 **@机器人**。

| 指令 | 用途 |
| --- | --- |
| `归档状态` | 查看本群的消息、附件保存情况。 |
| `文件列表` | 列出本群已归档的文件。 |
| `查找 关键词` | 查找本群消息，保留时间和来源线索。 |
| `整理今天` | 为已配置 AI 的群生成当天 AI 报告，附消息与附件来源；先回复处理提示，再回复摘要。 |

L 电脑需要保持开机、联网且接收程序正在运行。当前尚未启用登录自动启动。
    """
)

with st.expander("保存在哪里，大概怎么实现"):
    st.markdown(
        """
**保存位置：** L 上指定的 GoogleDrive 同步目录，按群和日期组织。

```text
归档根目录/
├─ 聊天记录/各群/日期        原始记录与可阅读的聊天文本
├─ 群文件/各群/日期          图片、文档及文件索引
└─ 整理结果/各群/日期        资料索引、AI 理解报告及结构化结果
```

**处理过程：** QQ 官方接口推送消息 → L 上的 Python 接收程序按授权群保存、去重并下载附件
→ 收到“整理今天”后提取文档文字、准备图片 → 将本群当天材料发送给 DeepSeek Flash
→ 校验来源索引，保存完整报告，并向群内回复精简摘要。内容未变化时复用已有 AI 结果。

接收程序保留 QQ 实际提供的来源信息；AI 报告用消息、附件索引回查出处。
已启用 AI 的群需单独配置，新增归档群不会自动送去分析。
接收程序使用 L 本机的加密配置，群聊和附件不进入公开代码仓库。

**本页的作用：** 展示项目能力与使用方法，不读取群聊、不持有密钥，也不启动或控制 L 上的服务。
GoogleDrive 的另一台电脑是否已同步到最新资料，仍需在该电脑上回读确认。
        """
    )

with st.expander("验收进度与当前限制"):
    st.markdown(
        """
| 范围 | 已确认的结果 |
| --- | --- |
| 单群普通归档 | 普通消息、图片和测试文件已保存；新增附件自动下载已通过。 |
| 四项群内指令 | AI 接入前的状态、文件列表、查找、资料整理回复已实测通过，含合并发送指令。 |
| AI 理解 | 已部署；不含真实群内容的文字与图片模型实测通过，**群内 AI 回复待验收**。 |
| 其他成员与多群 | 程序按授权群处理发言并隔离资料；另一成员发言、第二个群仍待实测。 |
| 持续运行与同步 | 登录自启未启用，D 电脑同步回读待验收。 |

- **转发聊天记录：** 只能处理 QQ 实际推送的正文与附件。合并转发卡片里的全部聊天，不能保证完整获取。
- **文档阅读：** 支持 DOCX 正文和表格、XLSX 单元格、可提取文字的 PDF，以及常见文本格式；图片支持 PNG、JPEG、WebP。
- **未支持的理解：** 扫描 PDF 的 OCR、文档内嵌图片、旧版 Office 格式和 PPT；这些文件可在平台提供附件时保存，不代表已读懂内容。
- **处理范围：** 不补抓启用前的历史记录；AI 分析设有消息、文件、图片和长度上限，报告会说明跳过或截断的材料。
- **待办用途：** 报告中的待办用于人工核对，尚未自动写入 M14，也不会自动执行群内要求。

[项目说明与交接记录](https://github.com/yaoy2/yao_1/blob/main/QQ_ROBOT_HANDOFF.md)
        """
    )
