# REQ-010-01 测试记录

## 问题记录

| ID | 问题描述 | 严重程度 | 状态 | 修复 commit | 日期 |
|---|---|---|---|---|---|
| T-001 | Reviewer 发现 PC 管理面板因 localhost 放行被移除而无法调用 `/api/*` | 严重 | 已修复 | `d428fde` | 2026-07-06 |
| T-002 | Reviewer 发现 localhost 判定缺少 `::ffff:127.0.0.1` | 一般 | 已修复 | `d428fde` | 2026-07-06 |
| T-003 | Reviewer 发现 `refresh_pairing_code` docstring 误称由中间件保证 localhost 限制 | 轻微 | 已修复 | `d428fde` | 2026-07-06 |

## 验证记录

| 项目 | 结果 | 日期 |
|---|---|---|
| Python 编译 `python -m compileall -q EzWinCommand-server` | 通过 | 2026-07-06 |
| localhost `/api/pairing-code` 返回 `code` | 通过 | 2026-07-06 |
| 远端 `/api/pairing-code` 不返回 `code` | 通过 | 2026-07-06 |
| 远端未授权 `/api/status` 返回 401 | 通过 | 2026-07-06 |
| localhost `/api/status` 可访问 | 通过 | 2026-07-06 |
