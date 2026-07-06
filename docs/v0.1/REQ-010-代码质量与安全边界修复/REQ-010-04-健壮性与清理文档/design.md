# REQ-010-04: 健壮性与清理文档

- **父需求**: REQ-010
- **日期**: 2026-07-06
- **状态**: 已完成

## 设计概述

降低鉴权热路径 IO，清理无效配置和低价值代码，确保 README.md 与 plan.md 反映当前 API 契约。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `EzWinCommand-server/agent/device_store.py` | 修改 | 支持 `Path`、schema 兜底、`last_seen` 写入节流 |
| `EzWinCommand-server/config.py` | 修改 | 删除未使用 `BEARER_TOKEN` |
| `EzWinCommand-server/.env.example` | 修改 | 删除未使用 `BEARER_TOKEN` 示例 |
| `EzWinCommand-server/plugins/base.py` | 修改 | 格式清理 |
| `EzWinCommand-server/plugins/loader.py` | 修改 | 删除未使用 import |
| `README.md` | 修改 | 同步 API、配对、安全、限制说明 |
| `plan.md` | 修改 | 与 README 同步 |

## 接口契约

### 导出

```python
class DeviceStore:
    def __init__(self, path: str | Path = "agent/devices.json") -> None: ...
```

行为契约：

- 设备文件缺失时创建空结构。
- 旧/损坏 schema 至少兜底为 `{"devices": {}}`，避免启动直接崩溃。
- `touch()` 对同一设备 30 秒内不重复落盘。

### 依赖

| 依赖子需求 | 需要的接口 |
|---|---|
| REQ-010-01 | 当前鉴权调用 `DeviceStore.touch()` |
| REQ-010-02 | README/plan 需与前后端 API 契约一致 |

## 实现要点

- 删除 `config.BEARER_TOKEN`，避免用户误以为设置静态 token 会启用鉴权。
- `.env.example` 只保留 `HOST` / `PORT`。
- README/plan 明确：外部设备不回显配对码，`/api/status` 为鉴权端点，`/api/pairing-code/refresh` 仅 localhost 可用。
- README/plan 记录 `BEARER_TOKEN` 已移除。

## 完成定义

- [x] `design.md` 与代码一致
- [x] 接口契约全部履行
- [x] Reviewer 审批通过
- [x] Test 测试通过，无未关闭的 `test-records` 条目
- [x] 父需求 `se-analysis.md` 状态已同步
