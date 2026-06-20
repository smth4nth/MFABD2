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
