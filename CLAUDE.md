# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MFABD2 是基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 构建的《棕色尘埃2》全流程自动化助手。此仓库同时包含：
- **GUI 模式**：由 MaaFramework 的 UI（MFAA/MFAWPF）驱动，Agent 作为子进程启动
- **CLI 模式**（`feat/cli` 分支）：`cli.py` 直接调度 MAA SDK，无需 GUI

## Commands

```bash
# 安装依赖（开发模式，首次运行会自动创建 venv）
pip install -r requirements.txt

# CLI 使用
python cli.py --list                          # 列出所有任务、预设、选项
python cli.py --task "任务名"                 # 运行单个任务
python cli.py --task "任务A" --task "任务B"   # 按顺序运行多个任务
python cli.py --preset "预设名"               # 运行预设任务组
python cli.py --adb 127.0.0.1:16384 --task "..." # 指定 ADB 地址（MuMu 0号默认 16384）
python cli.py --option "KEY=VALUE" --task "..." # 覆盖选项

# 启用 git commit 辅助 hook
git config core.hooksPath scripts/hooks
```

## Architecture

### 执行流程（CLI 模式）

```
cli.py
  ├── 读取 assets/interface.json → 解析任务/预设/选项定义
  ├── 构建 pipeline_override（合并各选项的 case.pipeline_override）
  ├── 启动 AgentServer 子进程 → agent/main.py <socket_id>
  ├── AdbController → 连接模拟器
  ├── Resource → 加载 assets/resource/base/pipeline/*.json
  ├── 应用 pipeline_override
  └── Tasker → 按序执行任务 entry 节点
```

### 目录结构关键路径

| 路径 | 用途 |
|------|------|
| `cli.py` | CLI 入口，参数解析与 MAA 调度 |
| `agent/main.py` | Agent 子进程入口，注册 Custom Action/Recognition |
| `agent/action/pipeline_manager.py` | 影子账本（Shadow Ledger）动态 Pipeline 管理 |
| `agent/recognition/counter.py` | 内存计数器（CheckTag / UpdateTag / ResetTag） |
| `agent/utils/persistent_store.py` | 多账号存档系统（原子写入 + 自动备份） |
| `assets/interface.json` | 任务、选项、预设的完整定义（GUI 与 CLI 共用） |
| `assets/resource/base/pipeline/` | 主体 Pipeline JSON（支持 JSON-with-comments） |
| `assets/resource/pc/pipeline/` | PC 客户端专属 Pipeline 覆写 |
| `runtimes/<rid>/native/` | 发布模式下的 MaaFramework 原生 DLL |

### 运行模式判断

`agent/main.py` 通过 `requirements.txt` 是否存在判断模式：
- **开发模式**（存在 `requirements.txt`）：使用 venv 自动管理，Python 库自带 DLL
- **发布模式**（无 `requirements.txt`）：从 `runtimes/<rid>/native/` 注入 DLL 路径

### 影子账本机制（Pipeline 动态修改）

`pipeline_manager.py` 实现运行时 Pipeline 热改写，所有 Custom Action 均通过 `context.override_pipeline()` 注入：

- **PatchNode** / **PatchBatch**：修改单个或多个节点，自动记录 origin 备份
- **PatchByRegex**：正则批量覆写，支持 `$box`（当前识别框坐标）、`$self`（节点名）、`$caller` 占位符
- **RestoreNode** / **RestoreBatch** / **ResetAll**：从影子账本还原节点
- **RunTask**：运行子任务，支持临时参数注入（不污染全局）

所有动作均支持 `reset_tags` 旁作用（顺手清零计数器）。

### 存档系统

`PersistentStore` 自动选择模式：
- **全局模式**：`%APPDATA%/MFABD2/` (Windows)
- **绿色便携模式**：项目根目录（当根目录已有 `agent_save_data*.json` 时自动触发）

多账号通过 `switch_account(id)` 切换，文件名格式为 `agent_save_data_<id>.json`。

### interface.json 结构

```json
{
  "controller": [...],   // ADB / Win32 控制器定义
  "resource": [...],     // 资源包路径（base / pc）
  "task": [...],         // 任务列表，每项含 name / entry / option[]
  "option": {...},       // 选项字典，每项含 cases[].pipeline_override
  "preset": [...]        // 预设组，引用 task + 默认 option 值
}
```

CLI 解析时，任务的 `pipeline_override` = 各 option 首个 case 的 override（深度合并），再由 `--option` 参数覆写指定 case。

## requirements.txt 版本标记

`requirements.txt` 中有两个特殊注释行由 CI 读取：

```
# MFAA_TAG=v2.x.x        ← 资源包版本（CI 据此下载资源）
# maa==x.x.x             ← pip 包版本（需与 Tag 对应的 Core 版本一致）
```

修改时两者须同步，否则 CI 会报错。
