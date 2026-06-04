from __future__ import annotations

import argparse
from pathlib import Path

from .collectors import collect_all
from .config import load_rules, load_sources
from .feed import write_feed
from .notifiers import send_dingtalk, should_push
from .rules import evaluate
from .storage import load_history, load_previous_state, save_outputs, update_history


def run(config_dir: Path, data_dir: Path, dry_run: bool = False) -> int:
    previous = load_previous_state(data_dir)
    history = load_history(data_dir)
    sources = load_sources(config_dir)
    rules = load_rules(config_dir)
    signals = collect_all(sources)
    state = evaluate(signals, rules, history)
    history = update_history(history, state)

    if not dry_run:
        save_outputs(data_dir, state, history)
        write_feed(data_dir / "codex_radar_feed.xml", state)
        if should_push(previous, state):
            send_dingtalk(state)

    print(f"{state.status} 24h={state.probability_24h}% 48h={state.probability_48h}% {state.reason}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Codex Radar Lite.")
    parser.add_argument("--config-dir", default="config", type=Path)
    parser.add_argument("--data-dir", default="data", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return run(args.config_dir, args.data_dir, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())

