# REQ-010 SE 分析：代码质量与安全边界修复

- **日期**: 2026-07-06
- **状态**: 已完成

## 问题概述

全量代码审查发现以下主要风险：

1. `/api/pairing-code` 对未授权局域网设备返回真实配对码，削弱配对安全边界。
2. `/status` 位于非 `/api/*` 路径，不受鉴权中间件保护。
3. 外部设备本地 key 失效后仍进入 dashboard，401/403 静默失败。
4. 插件发现和 `devices.json` 使用相对路径，依赖当前工作目录。
5. 防火墙规则名固定 8080，托盘 URL 硬编码 8080。
6. API 请求体未建模，非法输入缺少稳定 4xx 契约。
7. `last_seen` 每次鉴权同步写盘，热路径 IO 过重。
8. `BEARER_TOKEN` 是未使用配置，容易误导部署者。

## 方案拆分

| 子需求 | 目标 | 依赖 | 状态 |
|---|---|---|---|
| REQ-010-01 | 修复配对码泄露、状态接口鉴权、请求模型 | 无 | 已完成 |
| REQ-010-02 | 修复前端配对角色、失效 key 恢复、错误反馈 | REQ-010-01 API 契约 | 已完成 |
| REQ-010-03 | 修复 CWD 路径、端口化防火墙、托盘 URL | 无 | 已完成 |
| REQ-010-04 | 节流设备写入、删除死配置、同步文档 | REQ-010-01/02/03 | 已完成 |

## 接口契约

### 配对码状态

`GET /api/pairing-code`

- localhost / TestClient：

```json
{
  "has_code": true,
  "has_devices": true,
  "expires_in": 299,
  "code": "abcd"
}
```

- 非 localhost：

```json
{
  "has_code": true,
  "has_devices": true,
  "expires_in": 299
}
```

非 localhost 不得返回真实 `code`。

### 状态接口

`GET /api/status`

- localhost：中间件放行。
- 已授权设备：Bearer key 放行。
- 未授权远端：401。

### 前端会话

- 外部页面只用 `has_code` 判断是否进入配对输入页。
- 外部页面不展示配对码正文。
- 401/403 清除 `localStorage.ez_device_key` 并回到配对/等待流程。

### 路径与端口

- 插件目录和设备存储路径基于 `app.py` 所在目录。
- 防火墙规则名包含实际端口。
- 托盘 URL 由 `config.PORT` 注入。

## 环境差异分析

| 差异 | 风险 | 决策 |
|---|---|---|
| 从仓库根目录运行 vs 从 server 目录运行 | 相对路径导致插件为空、设备文件分裂 | 使用 `BASE_DIR = Path(__file__).resolve().parent` |
| TestClient / localhost / IPv4-mapped IPv6 | 本机请求识别不一致 | 统一 `is_local_host()`，包含 `::ffff:127.0.0.1` |
| Windows 防火墙端口变更 | 旧规则名误判已放行 | 规则名按端口生成 |
| 托盘打开 Web | 修改 PORT 后仍打开 8080 | `SystemTray(web_url=...)` 注入 |
| 真实 Windows 托盘/防火墙 | Agent 环境难以完整验证 | 列入集成验证清单 |

## 验收结果

- Reviewer 初次/复审发现问题后已修复。
- 最终 Reviewer 通过。
- Tester 通过。
- 实现 commit：`d428fde`。

## 集成验证清单

以下项目依赖真实 Windows 用户环境，未由自动化完整覆盖：

1. 以管理员身份启动服务时，防火墙规则 `EzWinCommand {PORT}` 正确创建。
2. 修改 `.env` 中 `PORT` 后，托盘“打开 Web 管理”跳转到新端口。
3. 双击 `start_daemon.pyw` 后服务无控制台启动，托盘可见。
4. 通过托盘退出时服务进程退出。
