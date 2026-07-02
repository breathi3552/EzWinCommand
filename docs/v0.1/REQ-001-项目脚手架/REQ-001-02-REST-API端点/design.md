# REQ-001-02: REST API 端点

- **父需求**: REQ-001
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

在 `agent/api.py` 中定义 REST API 路由，提供健康检查、统一命令入口和系统状态查询三个端点。所有命令执行通过 Dispatcher 分发，API 层不直接操作业务逻辑。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| EzWinCommand-server/agent/api.py | 新增 | API 路由定义 |
| EzWinCommand-server/agent/__init__.py | 新增 | agent 包初始化 |

## 实现要点

### 路由结构

| 方法 | 路径 | 函数 | 说明 |
|---|---|---|---|
| GET | `/ping` | `ping()` | 健康检查，返回 `{"status": "ok"}` |
| GET | `/status` | `get_status()` | 系统状态快照（CPU、内存） |
| POST | `/api/command` | `execute_command()` | 统一命令入口 |
| GET | `/api/actions` | `list_actions()` | 列出所有可用 action |

### GET /ping

- 无参数，返回固定的 `{"status": "ok"}`
- 用于客户端和服务监控检测 Agent 是否存活

### GET /status

- 通过 `psutil` 采集实时系统状态：
  - `cpu_percent` — 调用 `psutil.cpu_percent(interval=0.1)` 获取瞬时 CPU 使用率
  - `memory` — 调用 `psutil.virtual_memory()._asdict()` 获取完整内存信息（含 percent 字段）
- 设计为可扩展，后续可通过插件化状态采集增强

### POST /api/command

- 请求体 JSON 格式：`{"action": "插件名", "params": {...}}`
- 从 `request.app.state.dispatcher` 获取 Dispatcher 单例
- 调用 `dispatcher.execute(action, params)` 分发命令
- 返回 `{"success": bool, "message": str, "data": dict | None}`

### 辅助函数

- `_get_dispatcher(request: Request) -> Dispatcher` — 从 FastAPI `app.state` 中获取 Dispatcher 实例，避免全局变量

### 路由注册

- 在 `agent/api.py` 中创建 `APIRouter()` 实例 `router`
- 在 `app.py` 中通过 `app.include_router(api_router)` 注册
