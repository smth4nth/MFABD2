# -*- coding: utf-8 -*-
import json
import sys
import subprocess
import argparse
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [MFABD2-CLI] {msg}", flush=True)


def load_interface(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def resolve_option_override(interface: dict, option_name: str, case_name: str) -> dict:
    option = interface["option"].get(option_name)
    if not option:
        raise ValueError(f"选项 '{option_name}' 不存在")
    for case in option.get("cases", []):
        if case["name"] == case_name:
            return case.get("pipeline_override", {})
    valid = [c["name"] for c in option.get("cases", [])]
    raise ValueError(f"选项 '{option_name}' 没有值 '{case_name}'，可用值: {valid}")


def build_task_override(interface: dict, task: dict, extra_options: dict) -> dict:
    override = {}
    for opt_name in task.get("option", []):
        option = interface["option"].get(opt_name, {})
        cases = option.get("cases", [])
        if cases:
            override = deep_merge(override, cases[0].get("pipeline_override", {}))
    for opt_name, case_name in extra_options.items():
        if opt_name in task.get("option", []):
            opt_override = resolve_option_override(interface, opt_name, case_name)
            override = deep_merge(override, opt_override)
    return override


def resolve_tasks(interface: dict, task_names: list, options: dict) -> list:
    task_map = {t["name"]: t for t in interface["task"]}
    result = []
    for name in task_names:
        task = task_map.get(name)
        if not task:
            valid_names = "\n".join(f"  {n}" for n in task_map)
            raise ValueError(f"任务 '{name}' 不存在。\n可用任务:\n{valid_names}")
        result.append({
            "name": name,
            "entry": task["entry"],
            "pipeline_override": build_task_override(interface, task, options),
        })
    return result


def resolve_preset(interface: dict, preset_name: str, extra_options: dict) -> list:
    preset = next((p for p in interface.get("preset", []) if p["name"] == preset_name), None)
    if not preset:
        valid_names = "\n".join(f"  {p['name']}" for p in interface.get("preset", []))
        raise ValueError(f"预设 '{preset_name}' 不存在。\n可用预设:\n{valid_names}")
    task_map = {t["name"]: t for t in interface["task"]}
    result = []
    for pt in preset["task"]:
        if not pt.get("enabled", True):
            continue
        name = pt["name"]
        task = task_map.get(name)
        if not task:
            continue
        merged_options = {**pt.get("option", {}), **extra_options}
        result.append({
            "name": name,
            "entry": task["entry"],
            "pipeline_override": build_task_override(interface, task, merged_options),
        })
    return result


def merge_all_overrides(task_runs: list) -> dict:
    result = {}
    for run in task_runs:
        result = deep_merge(result, run["pipeline_override"])
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="MFABD2 CLI — 棕色尘埃2自动化助手命令行启动器",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--preset", metavar="NAME", help="跑预设任务组")
    group.add_argument(
        "--task", metavar="NAME", action="append", dest="tasks",
        help="跑指定任务（可重复多次）",
    )
    parser.add_argument(
        "--option", metavar="KEY=VALUE", action="append", dest="options",
        default=[], help="覆盖选项（可重复多次）",
    )
    parser.add_argument(
        "--adb", metavar="ADDRESS", default="127.0.0.1:5555",
        help="ADB 地址（默认: 127.0.0.1:5555）",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_all",
        help="列出所有可用任务、预设、选项后退出",
    )
    return parser


def parse_options(option_strings: list) -> dict:
    result = {}
    for s in option_strings:
        if "=" not in s:
            raise ValueError(f"--option 格式错误: '{s}'，应为 KEY=VALUE")
        key, _, value = s.partition("=")
        result[key.strip()] = value.strip()
    return result


def cmd_list(interface: dict) -> None:
    print("\n=== 可用任务 ===")
    for t in interface["task"]:
        checked = "Y" if t.get("default_check") else " "
        print(f"  [{checked}] {t['name']}")

    print("\n=== 可用预设 ===")
    for p in interface.get("preset", []):
        print(f"  {p['name']}")
        for pt in p["task"]:
            enabled = "Y" if pt.get("enabled", True) else "N"
            opts = pt.get("option", {})
            opt_str = ", ".join(f"{k}={v}" for k, v in opts.items()) if opts else ""
            suffix = f"  ({opt_str})" if opt_str else ""
            print(f"    [{enabled}] {pt['name']}{suffix}")

    print("\n=== 可用选项 ===")
    for name, opt in interface["option"].items():
        cases = [c["name"] for c in opt.get("cases", [])]
        opt_type = opt.get("type", "select")
        print(f"  {name} [{opt_type}]: {' | '.join(cases)}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    interface_path = PROJECT_ROOT / "assets" / "interface.json"
    if not interface_path.exists():
        interface_path = PROJECT_ROOT / "interface.json"
    interface = load_interface(interface_path)

    if args.list_all:
        cmd_list(interface)
        return 0

    if not args.preset and not args.tasks:
        parser.print_help()
        return 1

    try:
        options = parse_options(args.options)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    try:
        if args.preset:
            task_runs = resolve_preset(interface, args.preset, options)
        else:
            task_runs = resolve_tasks(interface, args.tasks, options)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    merged_override = merge_all_overrides(task_runs)

    if options:
        log(f"已解析选项: {', '.join(f'{k}={v}' for k, v in options.items())}")
    names = [r["name"] for r in task_runs]
    log(f"任务队列 ({len(names)}): {' → '.join(names)}")

    return _run_maa(args.adb, task_runs, merged_override)


def _run_maa(adb_address: str, task_runs: list, merged_override: dict) -> int:
    raise NotImplementedError("Task 3: maa SDK 集成尚未实现")


if __name__ == "__main__":
    sys.exit(main())
