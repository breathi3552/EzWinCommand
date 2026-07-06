# REQ-010-02: 前端会话与配对流程

- **父需求**: REQ-010
- **日期**: 2026-07-06
- **状态**: 已完成

## 设计概述

修复外部配对页角色混乱和失效 key 后的 UI 卡死问题。外部页面不再展示配对码正文，只提示用户输入 PC 管理面板显示的 4 位配对码；统一 JSON fetch 处理 HTTP 错误，401/403 清除本地 key 并回到配对流程。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `EzWinCommand-server/web/index.html` | 修改 | 删除外部配对码展示节点，调整文案 |
| `EzWinCommand-server/web/static/app.js` | 修改 | 新增 `fetchJson` / `authFetchJson`，使用 `has_code`，改用 `/api/status` |
| `EzWinCommand-server/web/static/style.css` | 修改 | 删除死样式，增加错误/反馈样式 |

## 接口契约

### 导出

```javascript
async function fetchJson(url, options = {}, errorElementId = null)
async function authFetchJson(url, options = {}, errorElementId = "ext-error")
async function extReturnToPairing()
```

### 依赖

| 依赖子需求 | 需要的接口 |
|---|---|
| REQ-010-01 | `GET /api/pairing-code` 返回 `has_code`；`GET /api/status` 鉴权 |

## 实现要点

- PC 管理面板仍使用 localhost 放行访问 `/api/*`。
- 外部页面进入 dashboard 前先请求 `/api/status` 校验本地 key。
- `authFetchJson()` 遇到 401/403：清除 `localStorage.ez_device_key`、显示错误、回到配对/等待流程。
- 外部配对轮询只判断 `data.has_code`，不读取 `data.code`。
- 操作按钮渲染对 `plugin.sub_actions` 做数组兜底。
- 命令执行结果显示在页面反馈区，避免静默失败。

## 完成定义

- [x] `design.md` 与代码一致
- [x] 接口契约全部履行
- [x] Reviewer 审批通过
- [x] Test 测试通过，无未关闭的 `test-records` 条目
- [x] 父需求 `se-analysis.md` 状态已同步
