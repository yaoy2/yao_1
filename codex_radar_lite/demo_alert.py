from __future__ import annotations

from .models import RadarState, Signal, isoformat
from .notifiers import send_dingtalk


def build_demo_state() -> RadarState:
    checked_at = isoformat()
    return RadarState(
        status="high_probability",
        probability_24h=72,
        probability_48h=86,
        reason="Codex 使用限额与恢复信号同时升温，进入高概率观察窗口。",
        checked_at=checked_at,
        alert_level="push",
        signals=[
            Signal(
                source_id="demo_openai_status",
                source_name="OpenAI Status Incidents",
                title="Codex usage limits may reset for affected users",
                summary="OpenAI is investigating Codex usage limit pressure and related subscription credit impacts.",
                url="https://status.openai.com/",
                observed_at=checked_at,
                weight=40,
                tags=["codex", "usage limit"],
            ),
            Signal(
                source_id="demo_radar_rule",
                source_name="Codex Radar Rule",
                title="Rate limit and quota keywords crossed the high-probability threshold",
                summary="Multiple Codex limit keywords appeared close together, so the radar raised the alert level.",
                url="https://github.com/yaoy2/yao_1/actions/workflows/codex-radar.yml",
                observed_at=checked_at,
                weight=25,
                tags=["rate limit", "quota"],
            ),
        ],
    )


def main() -> int:
    result = send_dingtalk(build_demo_state())
    print(f"demo_alert:{result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

