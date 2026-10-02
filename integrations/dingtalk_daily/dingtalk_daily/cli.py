"""CLI: configuration, local UI calibration, diagnosis, collection and replay."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from datetime import datetime
import json
from pathlib import Path
import sys

from .settings import CHINA, DEFAULT_CONFIG, defaults, load, output_path, safe_config_target, validate
from .storage import RunBusy, desktop_lock, finish_run, run_lock, start_run, write_json, write_text


def desktop_factory(config: dict):
    # Import lazily: report/replay/tests work without any Windows UI packages.
    from .desktop import DingTalkDesktop
    return DingTalkDesktop(config)


def _require_calibration(config: dict) -> None:
    if config.get("calibration_ok") is not True:
        raise ValueError("尚未完成 L 本机界面适配，请打开钉钉后运行 main.py calibrate。")


def _ready(config: dict, factory=None) -> dict:
    factory = factory or desktop_factory
    result = factory(config).doctor()
    if not isinstance(result, dict) or result.get("ready") is not True:
        raise ValueError("钉钉界面检查未通过，不能启用定时采集。")
    return result


def _prompt(label: str, current: str = "") -> str:
    value = input(f"{label}" + (f" [{current}]" if current else "") + "：").strip()
    return value or current


def configure(path: Path) -> int:
    path = safe_config_target(path)
    previous = load(path) if path.exists() else defaults()
    config = dict(previous)
    config["priority_contact"] = _prompt("指定联系人（完整名称）", config["priority_contact"])
    config["self_group"] = _prompt("只整理本人消息的群（完整名称）", config["self_group"])
    names = _prompt("本人显示姓名／群内别名，多个用逗号分隔", ",".join(config["self_names"]))
    config["self_names"] = list(dict.fromkeys(name.strip() for name in names.replace("，", ",").split(",") if name.strip()))
    config["output_dir"] = _prompt("结果保存在本机目录", config["output_dir"])
    if any(config[key] != previous[key] for key in ("priority_contact", "self_group", "self_names")):
        config["calibration_ok"] = False
    validate(config)
    write_json(path, config)
    print(f"本机配置已保存：{path}\n下一步：打开钉钉，运行 main.py calibrate。")
    return 0


def execute_run(config: dict, run_at: datetime, *, scheduled: bool = False,
                factory=None, replay: dict | None = None) -> tuple[int, Path | None]:
    """Run once, retain failed/partial results and never promote them to success."""
    from .core import build_report

    factory = factory or desktop_factory
    validate(config)
    if run_at.tzinfo is None or run_at.utcoffset() is None:
        raise ValueError("运行时间必须带时区。")
    run_at = run_at.astimezone(CHINA)
    output = output_path(config["output_dir"])
    with run_lock(output), (desktop_lock() if replay is None else nullcontext()):
        folder = start_run(output, run_at)
        status = {"started_at": run_at.isoformat(), "cutoff": run_at.isoformat()}
        try:
            if replay is None:
                if scheduled and run_at.hour != 22:
                    raise ValueError("定时入口仅在北京时间 22 点这一小时运行，不跨日补采。")
                _require_calibration(config)
                adapter = factory(config)
                readiness = adapter.doctor()
                if not isinstance(readiness, dict) or readiness.get("ready") is not True:
                    raise ValueError("钉钉界面未就绪。")
                capture = adapter.collect(run_at)
                # Desktop metadata cannot change the requested day or extend its cutoff.
                if capture.get("date") != run_at.date().isoformat():
                    raise ValueError("采集返回了其他日期，结果未写入。")
                if capture.get("cutoff") != run_at.isoformat():
                    raise ValueError("采集截止时间与运行开始时间不一致，结果未写入。")
            else:
                capture = replay
            report, markdown = build_report(capture, config, run_at)
            if report.get("status") not in ("complete", "partial"):
                raise ValueError("整理器返回了无法识别的状态。")
            if replay is not None:
                # Replayed fixtures must never qualify a machine for live operation.
                report["source_mode"] = "replay"
                markdown = "> 离线重放结果：未访问钉钉，不能证明桌面采集已成功。\n\n" + markdown
            else:
                report["source_mode"] = "desktop"
            # Only the strict scope-filtered report is persisted, never the raw capture.
            write_json(folder / "records.json", report)
            write_text(folder / "整理.md", markdown)
            state = "replay" if replay is not None else report["status"]
            status.update(status=state, report_status=report["status"],
                          finished_at=datetime.now(CHINA).isoformat(),
                          report="整理.md", records="records.json")
            finish_run(folder, status)
            return (0 if report["status"] == "complete" else 2), folder
        except Exception as exc:
            status.update(status="failed", finished_at=datetime.now(CHINA).isoformat(),
                          error_type=type(exc).__name__, message=str(exc))
            finish_run(folder, status)
            print(f"本次未完成，原因和恢复提示保存在：{folder / 'status.json'}", file=sys.stderr)
            return 1, folder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="钉钉当天聊天整理（仅本机、只读采集）")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="本机配置，默认项目内被 Git 忽略的 config.local.json")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("configure", help="填写本人和两个指定会话，保存本机配置")
    commands.add_parser("calibrate", help="首次在本机适配钉钉控件，并核验可读性")
    commands.add_parser("doctor", help="只读检查本机配置和钉钉控件，不采集聊天")
    commands.add_parser("inspect", help="将有界控件树保存到私人目录，供适配使用")
    run = commands.add_parser("run", help="整理今天到运行开始时间的记录")
    run.add_argument("--scheduled", action="store_true", help="用于 L 的每日 22:00 任务")
    replay = commands.add_parser("replay", help="离线整理采集 JSON；不访问钉钉")
    replay.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "configure":
            return configure(args.config)
        config = load(args.config)
        if args.command == "doctor":
            _require_calibration(config)
            with desktop_lock():
                _ready(config)
            print("钉钉控件检查通过。完整性仍以每次实际采集报告为准。")
            return 0
        if args.command == "inspect":
            with run_lock(output_path(config["output_dir"])), desktop_lock():
                tree = desktop_factory(config).inspect()
                target = output_path(config["output_dir"]) / "diagnostics" / (
                    datetime.now(CHINA).strftime("%Y%m%d-%H%M%S-%f") + ".json")
                write_json(target, tree)
            print(f"控件诊断保存在本机：{target}\n诊断可能含可见聊天文字，请勿提交到公开仓库。")
            return 0
        if args.command == "calibrate":
            with run_lock(output_path(config["output_dir"])), desktop_lock():
                # Invalidate readiness before any attempt, so a failed re-calibration
                # cannot leave an old scheduled profile marked as usable.
                config["calibration_ok"] = False
                write_json(safe_config_target(args.config), config)
                config["ui"] = desktop_factory(config).calibrate()
                # Preserve the observed profile for local repair even if the
                # subsequent readiness check fails. It remains disabled.
                write_json(safe_config_target(args.config), config)
                _ready(config)
                config["calibration_ok"] = True
                write_json(safe_config_target(args.config), config)
            print("本机界面适配已保存。先运行 main.py run 核验日报，再安装每日任务。")
            return 0
        if args.command == "replay":
            with args.input.open("r", encoding="utf-8-sig") as stream:
                capture = json.load(stream)
            when = datetime.fromisoformat(capture["cutoff"])
            code, folder = execute_run(config, when, replay=capture)
        else:
            code, folder = execute_run(config, datetime.now(CHINA), scheduled=args.scheduled)
        if folder:
            print(f"结果目录：{folder}")
            if code == 2:
                print("本次存在采集缺口，请查看整理.md；不计为完整日报。")
        return code
    except RunBusy as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (ValueError, OSError, ImportError, KeyError) as exc:
        print(f"未完成：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已中止。", file=sys.stderr)
        return 130
    except Exception as exc:
        # UI errors are expected to be actionable and contain no credentials.
        print(f"未完成（{type(exc).__name__}）：{exc}", file=sys.stderr)
        return 1
