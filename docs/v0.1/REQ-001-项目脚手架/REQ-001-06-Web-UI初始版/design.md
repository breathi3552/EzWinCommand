# REQ-001-06: Web UI 初始版本

- **父需求**: REQ-001
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

实现纯静态 Web 控制面板，包含 `index.html`、`style.css`、`app.js` 三个文件。通过 FastAPI 的 `StaticFiles` 挂载到服务根路径 `/`，无需额外前端构建步骤。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| EzWinCommand-server/web/index.html | 新增 | 主页面结构 |
| EzWinCommand-server/web/static/style.css | 新增 | 样式表 |
| EzWinCommand-server/web/static/app.js | 新增 | 前端逻辑 |

## 实现要点

### index.html — 页面结构

- 语言 `zh-CN`，viewport 适配移动端
- 引用 `/static/style.css` 和 `/static/app.js`
- 三个区块：
  - `<h1>` 标题 "EzWinCommand"
  - `<div id="status">` 系统状态显示区（CPU、内存）
  - `<div id="actions">` 动态控制按钮区（由 JS 渲染）

### style.css — 暗色主题

- 全局 Box-Sizing 重置
- 暗色背景 `#1a1a2e`，浅色文字 `#e0e0e0`
- 最大宽度 480px 居中，适配手机竖屏
- 系统状态区域：深蓝色卡片 + flex 均匀分布
- 插件卡片：带边框圆角，标题灰色小字
- 按钮：蓝色背景 `#0f3460`，hover 变亮，active 变暗
- 按钮组 `btn-group`：flex 横向排列，支持换行

### app.js — 前端逻辑

**状态轮询** — `loadStatus()`：
- `fetch("/status")` 获取系统状态 JSON
- 更新 `#cpu` 和 `#memory` 元素的文本内容
- 每 5 秒通过 `setInterval` 轮询一次
- 网络错误静默忽略

**动态按钮渲染** — `loadActions()`：
- `fetch("/api/actions")` 获取插件列表
- 遍历插件，为每个创建 `.plugin-card` 卡片
- 简单触发型（`sub_actions` 为空）：渲染单个按钮
- 子操作型（`sub_actions` 非空）：渲染 `.btn-group` 按钮组
- 点击按钮调用 `sendCommand(name, params)`

**命令发送** — `sendCommand(action, params)`：
- `POST /api/command`，body 为 `{"action": "...", "params": {...}}`
- 结果打印到 console（console.log / console.error）

### 静态文件挂载

在 `app.py` 中：
```python
web_dir = Path(__file__).parent / "web"
if web_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="webui")
```

- `html=True` 启用自动 `index.html` 查找
- 挂载到根路径 `/`，访问 `http://host:port/` 即显示控制面板
