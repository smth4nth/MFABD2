import json
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

INTERFACE_PATH = Path("assets/interface.json")


def test_deep_merge_nested():
    from cli import deep_merge
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"d": 99, "e": 4}}
    assert deep_merge(base, override) == {"a": 1, "b": {"c": 2, "d": 99, "e": 4}}


def test_deep_merge_leaf_override():
    from cli import deep_merge
    base = {"Node": {"enabled": True}}
    override = {"Node": {"enabled": False}}
    assert deep_merge(base, override) == {"Node": {"enabled": False}}


def test_resolve_option_override_valid():
    from cli import resolve_option_override, load_interface
    interface = load_interface(INTERFACE_PATH)
    override = resolve_option_override(interface, "圣石洞穴属性", "火")
    assert "QuickHunt_StoneSelect_Fire" in override
    assert override["QuickHunt_StoneSelect_Fire"]["enabled"] is True


def test_resolve_option_override_invalid_case():
    from cli import resolve_option_override, load_interface
    interface = load_interface(INTERFACE_PATH)
    with pytest.raises(ValueError, match="没有值"):
        resolve_option_override(interface, "圣石洞穴属性", "不存在")


def test_resolve_option_override_invalid_option():
    from cli import resolve_option_override, load_interface
    interface = load_interface(INTERFACE_PATH)
    with pytest.raises(ValueError, match="不存在"):
        resolve_option_override(interface, "不存在的选项", "any")


def test_resolve_tasks_single():
    from cli import resolve_tasks, load_interface
    interface = load_interface(INTERFACE_PATH)
    runs = resolve_tasks(interface, ["[领取]领取邮件"], {})
    assert len(runs) == 1
    assert runs[0]["entry"] == "Mail_HomePage"
    assert isinstance(runs[0]["pipeline_override"], dict)


def test_resolve_tasks_ordering():
    from cli import resolve_tasks, load_interface
    interface = load_interface(INTERFACE_PATH)
    names = ["[领取]领取邮件", "[领取]通行证奖励"]
    runs = resolve_tasks(interface, names, {})
    assert [r["name"] for r in runs] == names


def test_resolve_tasks_unknown():
    from cli import resolve_tasks, load_interface
    interface = load_interface(INTERFACE_PATH)
    with pytest.raises(ValueError, match="不存在"):
        resolve_tasks(interface, ["不存在的任务"], {})


def test_resolve_tasks_with_option():
    from cli import resolve_tasks, load_interface
    interface = load_interface(INTERFACE_PATH)
    runs = resolve_tasks(interface, ["[执行]快速狩猎扫荡"], {"圣石洞穴属性": "火"})
    assert runs[0]["pipeline_override"]["QuickHunt_StoneSelect_Fire"]["enabled"] is True


def test_resolve_preset_daily_fast():
    from cli import resolve_preset, load_interface
    interface = load_interface(INTERFACE_PATH)
    runs = resolve_preset(interface, "日常-尽快完成", {})
    assert len(runs) > 0
    entries = [r["entry"] for r in runs]
    assert "StartGame_Start" in entries
    # [执行]肉鸽塔每日快速战斗 is disabled in this preset
    assert not any(r["entry"] == "Redemption_HomePage" for r in runs)


def test_resolve_preset_unknown():
    from cli import resolve_preset, load_interface
    interface = load_interface(INTERFACE_PATH)
    with pytest.raises(ValueError, match="不存在"):
        resolve_preset(interface, "不存在的预设", {})


def test_resolve_preset_cli_option_overrides_preset():
    from cli import resolve_preset, load_interface
    interface = load_interface(INTERFACE_PATH)
    runs = resolve_preset(interface, "日常-尽快完成", {"圣石洞穴属性": "火"})
    hunt = next((r for r in runs if r["name"] == "[执行]快速狩猎扫荡"), None)
    assert hunt is not None
    assert hunt["pipeline_override"]["QuickHunt_StoneSelect_Fire"]["enabled"] is True


def test_merge_all_overrides_no_conflict():
    from cli import merge_all_overrides
    runs = [
        {"name": "A", "entry": "A", "pipeline_override": {"Node1": {"enabled": False}}},
        {"name": "B", "entry": "B", "pipeline_override": {"Node2": {"target": [1, 2]}}},
    ]
    merged = merge_all_overrides(runs)
    assert merged == {"Node1": {"enabled": False}, "Node2": {"target": [1, 2]}}


def test_merge_all_overrides_conflict_last_wins():
    from cli import merge_all_overrides
    runs = [
        {"name": "A", "entry": "A", "pipeline_override": {"Node": {"enabled": True}}},
        {"name": "B", "entry": "B", "pipeline_override": {"Node": {"enabled": False}}},
    ]
    merged = merge_all_overrides(runs)
    assert merged["Node"]["enabled"] is False


def test_parse_options_valid():
    from cli import parse_options
    result = parse_options(["圣石洞穴属性=补短", "竞技场战斗倍数=40倍"])
    assert result == {"圣石洞穴属性": "补短", "竞技场战斗倍数": "40倍"}


def test_parse_options_invalid_format():
    from cli import parse_options
    with pytest.raises(ValueError, match="格式错误"):
        parse_options(["圣石洞穴属性"])  # 缺少 =


def test_build_parser_preset():
    from cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["--preset", "日常-尽快完成"])
    assert args.preset == "日常-尽快完成"
    assert args.tasks is None


def test_build_parser_tasks():
    from cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["--task", "[领取]领取邮件", "--task", "[领取]通行证奖励"])
    assert args.tasks == ["[领取]领取邮件", "[领取]通行证奖励"]
    assert args.preset is None


def test_build_parser_defaults():
    from cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["--preset", "日常-尽快完成"])
    assert args.adb == "127.0.0.1:5555"
    assert args.options == []
    assert args.list_all is False
