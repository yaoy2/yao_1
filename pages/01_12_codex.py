import json
import os
import sys
from pathlib import Path

import streamlit as st


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.ui_theme import render_home_link


ROOT = Path(__file__).resolve().parents[1]
CURRENT_PATH = ROOT / "data" / "codex_radar_current.json"
HISTORY_PATH = ROOT / "data" / "codex_radar_history.json"


st.set_page_config(page_title="Codex雷达", page_icon="📡", layout="wide")


STATUS_LABELS = {
    "normal": "正常",
    "watch": "观察",
    "high_probability": "高概率",
    "open": "窗口开启",
    "closed": "窗口关闭",
}


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def status_label(status):
    return STATUS_LABELS.get(status, status or "未知")


def status_class(status):
    if status in {"open", "high_probability"}:
        return "hot"
    if status in {"watch", "closed"}:
        return "watch"
    return "normal"


def apply_style():
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.7rem !important;
            padding-bottom: 1.5rem !important;
        }
        .radar-hero {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            gap: 1.2rem;
            margin-bottom: 1rem;
        }
        .radar-kicker {
            color: #475467;
            font-size: .82rem;
            font-weight: 800;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: .45rem;
        }
        .radar-title {
            margin: 0;
            color: #182230;
            font-size: 2.2rem;
            line-height: 1.12;
            font-weight: 850;
            letter-spacing: 0;
        }
        .radar-subtitle {
            margin: .45rem 0 0;
            color: #667085;
            font-size: .96rem;
            line-height: 1.7;
        }
        .radar-pill-row {
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-end;
            gap: .55rem;
        }
        .radar-pill {
            min-width: 104px;
            padding: .62rem .7rem;
            border: 1px solid rgba(24,34,48,.1);
            border-radius: 8px;
            background: rgba(255,255,255,.84);
            text-align: center;
            box-shadow: 0 10px 26px rgba(24,34,48,.07);
        }
        .radar-pill b {
            display: block;
            color: #182230;
            font-size: 1.2rem;
        }
        .radar-pill span {
            color: #667085;
            font-size: .76rem;
        }
        .status-banner {
            border: 1px solid rgba(24,34,48,.1);
            border-radius: 8px;
            background: #fff;
            padding: .85rem 1rem;
            margin-bottom: .85rem;
        }
        .status-banner.hot { border-color: rgba(180,35,24,.25); background: #fff7f5; }
        .status-banner.watch { border-color: rgba(181,71,8,.22); background: #fffcf5; }
        .status-banner.normal { border-color: rgba(6,118,71,.18); background: #f6fef9; }
        .status-banner b {
            color: #182230;
            margin-right: .5rem;
        }
        .status-banner span {
            color: #667085;
        }
        .signal-card {
            border: 1px solid rgba(24,34,48,.1);
            border-radius: 8px;
            background: rgba(255,255,255,.86);
            padding: .72rem .82rem;
            margin-bottom: .55rem;
        }
        .signal-title {
            margin: 0 0 .25rem;
            color: #182230;
            font-weight: 800;
            font-size: .95rem;
            line-height: 1.35;
        }
        .signal-meta {
            color: #667085;
            font-size: .76rem;
            margin-bottom: .25rem;
        }
        .signal-summary {
            color: #475467;
            font-size: .84rem;
            line-height: 1.55;
            margin: 0;
        }
        div[data-testid="stExpander"] details {
            border-radius: 8px !important;
            border-color: rgba(24,34,48,.1) !important;
        }
        @media (max-width: 980px) {
            .radar-hero {
                flex-direction: column;
                align-items: flex-start;
            }
            .radar-pill-row {
                justify-content: flex-start;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_signal(signal):
    title = signal.get("title") or "未命名信号"
    url = signal.get("url") or ""
    source = signal.get("source_name") or signal.get("source_id") or "未知来源"
    observed = signal.get("observed_at") or ""
    summary = signal.get("summary") or ""
    if url:
        title_html = f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
    else:
        title_html = title
    st.markdown(
        f"""
        <div class="signal-card">
          <p class="signal-title">{title_html}</p>
          <div class="signal-meta">{source} · {observed}</div>
          <p class="signal-summary">{summary}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


apply_style()
render_home_link()

state = load_json(
    CURRENT_PATH,
    {
        "status": "normal",
        "probability_24h": 5,
        "probability_48h": 13,
        "reason": "暂未读取到 Codex 雷达状态。",
        "checked_at": "--",
        "signals": [],
    },
)
history = load_json(HISTORY_PATH, [])

st.markdown(
    f"""
    <div class="radar-hero">
      <div>
        <div class="radar-kicker">Codex Radar Lite</div>
        <h1 class="radar-title">Codex雷达</h1>
        <p class="radar-subtitle">每小时观察公开信号；高概率、窗口开启或窗口关闭时通过钉钉机器人提醒。</p>
      </div>
      <div class="radar-pill-row">
        <div class="radar-pill"><b>{state.get("probability_24h", 0)}%</b><span>24小时</span></div>
        <div class="radar-pill"><b>{state.get("probability_48h", 0)}%</b><span>48小时</span></div>
        <div class="radar-pill"><b>{status_label(state.get("status"))}</b><span>当前状态</span></div>
      </div>
    </div>
    <div class="status-banner {status_class(state.get("status"))}">
      <b>{status_label(state.get("status"))}</b>
      <span>{state.get("reason", "")}</span>
    </div>
    """,
    unsafe_allow_html=True,
)

left, right = st.columns([1.5, 1], gap="medium")

with left:
    st.subheader("关键证据")
    signals = state.get("signals") or []
    if signals:
        for signal in signals[:10]:
            render_signal(signal)
    else:
        st.info("暂时没有关键证据，等待 GitHub Actions 下一轮采集。")

with right:
    st.subheader("运行状态")
    st.caption(f"最近检查：{state.get('checked_at', '--')}")
    st.caption(f"推送级别：{state.get('alert_level', 'silent')}")
    st.caption("定时任务：GitHub Actions 每小时运行一次")
    st.caption("推送渠道：钉钉机器人")

    with st.expander("最近窗口记录", expanded=False):
        if history:
            for item in history[:8]:
                st.markdown(
                    f"- **{status_label(item.get('status'))}** · {item.get('checked_at', '--')} · "
                    f"24h {item.get('probability_24h', 0)}%"
                )
        else:
            st.caption("暂无历史窗口记录。")

    with st.expander("明天需要配置什么", expanded=False):
        st.markdown(
            """
            在 GitHub 仓库 Secrets 里填写：

            - `DINGTALK_WEBHOOK`
            - `DINGTALK_SECRET`，只有机器人启用加签时才需要
            """
        )
