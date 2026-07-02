# REQ-005-02: 统一 CommandResult 定义

- **父需求**: REQ-005
- **日期**: 2026-07-03
- **状态**: 已完成

## 设计概述

`agent/dispatcher.py` 中定义了一个本地 `@dataclass CommandResult`，与 `plugins/base.py` 中的 `CommandResult` 结构完全相同。移除 dispatcher 中的重复定义，改为从 `plugins.base` 统一导入。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| EzWinCommand-server/agent/dispatcher.py | 修改 | 删除本地 CommandResult dataclass，改用 `from plugins.base import CommandResult` |

## 实现要点

- `plugins/base.py` 中的 `CommandResult` 为项目权威定义，包含 `success: bool` 和 `message: str` 两个字段
- dispatcher 本地版本字段与类型完全一致，无任何差异
- 修改后 dispatcher.py 中所有 `CommandResult(...)` 构造调用保持不变，仅导入来源变更
- 该变更不影响任何外部调用者
