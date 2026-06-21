# CLI 启动方式设计文档

**日期**: 2026-06-20  
**项目**: MFABD2-cli  
**场景**: 无头服务器（腾讯云 Linux + Redroid），不依赖 MFAAvalonia 图形界面

---

## 目标

为 interface.json 中的每个 UI 功能提供对等的命令行启动方式，使任务可在无 GUI 的服务器上自动化运行。

---

## 架构

### 方案选型

采用**纯 Python CLI + maa Python SDK controller 模式 + agent 子进程**：

- `cli.py` 使用 maa Python SDK 的 controller 模式（AdbController + Resource + Tasker）
- Tasker 按 interface.json 的 `agent` 配置自动拉起 `agent/main.py` 子进程（socket 连接）
- `agent/main.py` 代码**零改动**，行为与 maafw 驱动时完全一致

### 文件结构

```
MFABD2-cli/
├── cli.py          ← 新增，唯一改动
├── agent/
│   └── main.py     ← 不动
└── assets/
    └── interface.json
```

### 运行流程

```
cli.py
 1. 解析命令行参数
 2. 读 assets/interface.json
 3. 确定任务列表 + 每个任务的 pipeline_override
 4. 合并所有 pipeline_override
 5. 初始化 maa SDK：
      AdbController(adb_address)
      Resource(resource_paths) + apply pipeline_override
      Tasker(controller, resource)
 6. Tasker 自动拉起 agent/main.py（与 interface.json agent 配置一致）
 7. 按顺序 tasker.run_task(entry) 执行每个任务
```

---

## 命令接口

```bash
# 跑预设（最常用，服务器主路径）
python cli.py --preset "日常-尽快完成" --adb 127.0.0.1:5555

# 跑单个任务
python cli.py --task "[执行]快速狩猎扫荡" --adb 127.0.0.1:5555

# 跑多个任务 + 覆盖选项
python cli.py \
  --task "[执行]快速狩猎扫荡" \
  --task "[领取]领取邮件" \
  --option "圣石洞穴属性=补短" \
  --adb 127.0.0.1:5555

# 查看所有可用任务、预设、选项
python cli.py --list
```

### 参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--preset NAME` | — | 跑 interface.json 里的预设，含任务列表和默认选项 |
| `--task NAME` | — | 按任务名指定，可重复多次，按顺序执行 |
| `--option KEY=VALUE` | — | 覆盖选项，KEY 是选项名，VALUE 是 case 名；可重复多次 |
| `--adb ADDRESS` | `127.0.0.1:5555` | ADB 地址 |
| `--resource PATH` | `assets/resource/base` | 资源目录（dev 模式默认值） |
| `--list` | — | 打印所有可用任务、预设、选项后退出 |

---

## pipeline_override 合并逻辑

interface.json 中每个 option case 包含 `pipeline_override` dict。CLI 按以下优先级从低到高合并：

1. 各 option 的第一个 case（基础默认值）
2. `--preset` 里指定的 option 值
3. `--option` 命令行参数（最高优先级）

合并方式：deep merge，后者覆盖前者。

```python
# 伪代码
override = {}
for node_name, node_patch in merged_pipeline_override.items():
    override[node_name] = deep_merge(override.get(node_name, {}), node_patch)
resource.override_pipeline(override)
```

---

## 输出格式

```
[2026-06-20 10:32:01] [MFABD2-CLI] ADB 连接: 127.0.0.1:5555
[2026-06-20 10:32:02] [MFABD2-CLI] 资源加载完成
[2026-06-20 10:32:02] [MFABD2-CLI] 已解析选项: 圣石洞穴属性=补短, 竞技场战斗倍数=40倍
[2026-06-20 10:32:02] [MFABD2-CLI] 任务队列 (3): [执行]快速狩猎扫荡 → [执行]竞技场 → [领取]领取邮件
[2026-06-20 10:32:02] [MFABD2-CLI] 运行中: [执行]快速狩猎扫荡
[2026-06-20 10:32:45] [MFABD2-CLI] ✓ 完成 (43s): [执行]快速狩猎扫荡
[2026-06-20 10:45:11] [MFABD2-CLI] 全部完成，耗时 13m09s
```

每行带时间戳；选项解析结果在任务开始前打印，便于事后审计。

---

## 错误处理

| 情况 | 行为 |
|---|---|
| 任务名不存在 | 立即报错退出，列出可用任务名 |
| option key/value 不合法 | 立即报错退出 |
| ADB 连接失败 | 报错退出（maa SDK 抛出） |
| 单个任务执行失败 | 打印错误，继续跑下一个任务 |

### 退出码

| 退出码 | 含义 |
|---|---|
| `0` | 全部成功 |
| `1` | 参数错误 |
| `2` | 有任务执行失败 |

---

## 不在范围内

- log 文件输出（服务器上重定向 stdout 即可）
- Win32 PC 客户端控制器支持（服务器场景仅 ADB）
- checkbox 类型 option 的多选支持（暂不实现，后续扩展）
