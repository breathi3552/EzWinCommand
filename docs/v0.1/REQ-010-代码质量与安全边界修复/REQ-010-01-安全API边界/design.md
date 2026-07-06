# REQ-010-01: 安全 API 边界

- **父需求**: REQ-010
- **日期**: 2026-07-06
- **状态**: 已完成

## 设计概述

修复配对码和状态接口的安全边界：真实配对码只允许 localhost / TestClient 获取，局域网设备只能获知是否存在可输入的配对码；系统状态迁移到 `/api/status` 并纳入鉴权中间件；命令和授权请求改为 Pydantic 模型。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `EzWinCommand-server/agent/api.py` | 修改 | 新增请求模型、`/api/status`、配对码响应分流、refresh 本机检查 |
| `EzWinCommand-server/agent/auth.py` | 修改 | 统一本机判断，保留 localhost 管理面板放行 |

## 接口契约

### 导出

```python
def is_local_host(host: str) -> bool: ...

class CommandRequest(BaseModel):
    action: str
    params: dict[str, Any]

class AuthorizeRequest(BaseModel):
    token: str
    name: str
```

HTTP 契约：

| 端点 | 契约 |
|---|---|
| `GET /api/pairing-code` | localhost 含 `code`；非 localhost 不含 `code` |
| `POST /api/pairing-code/refresh` | 仅 localhost 可用 |
| `GET /api/status` | localhost 或 Bearer 授权可用，远端未授权 401 |
| `POST /api/command` | 请求体由 `CommandRequest` 校验 |
| `POST /api/authorize` | 请求体由 `AuthorizeRequest` 校验 |

### 依赖

| 依赖子需求 | 需要的接口 |
|---|---|
| REQ-010-02 | `/api/pairing-code` 的 `has_code` / `expires_in` 契约、`/api/status` 鉴权契约 |

## 实现要点

- `_WHITELIST_PATHS` 只放行配对、授权与健康检查入口。
- localhost / TestClient 请求仍由中间件放行，保证 PC 管理面板无需设备 key。
- 本机判定包含 `127.0.0.1`、`::1`、`::ffff:127.0.0.1`、`localhost`、`testclient`。
- refresh 端点虽在白名单中，但 handler 内部使用 `_is_local_client()` 再次限制。

## 完成定义

- [x] `design.md` 与代码一致
- [x] 接口契约全部履行
- [x] Reviewer 审批通过
- [x] Test 测试通过，无未关闭的 `test-records` 条目
- [x] 父需求 `se-analysis.md` 状态已同步
