# REQ-002: Web UI 交互增强与 Player 媒体控制插件

- **日期**: 2026-07-02
- **版本**: v0.1
- **状态**: 已完成

## 原始需求

扩展 Web UI 交互能力，新增 Player 媒体控制插件，API 支持子操作信息。

具体目标：

1. **插件子操作支持** — BasePlugin 需要能声明自身支持哪些子操作（如音量控制的 +/−/静音），前端根据子操作列表决定渲染单按钮还是按钮组。
2. **API 结构化返回** — GET /api/actions 当前只返回插件名列表，需升级为包含 `name`、`label`、`sub_actions` 的结构化数组。
3. **Web UI 改造** — 前端解析新的 API 响应，为有子操作的插件渲染按钮组，无子操作的保持单按钮行为。
4. **Player 插件** — 新增媒体控制插件，支持播放/暂停、上一曲、下一曲，复用 volume 插件的 `keybd_event` 模式。

## 拆分需求列表

| 编号 | 标题 | 状态 |
|---|---|---|
| REQ-002-01 | BasePlugin 扩展 get_sub_actions() 和 label 属性 | 已完成 |
| REQ-002-02 | Dispatcher list_actions() 返回结构化插件信息 | 已完成 |
| REQ-002-03 | GET /api/actions 返回结构化 JSON | 已完成 |
| REQ-002-04 | Web UI 改造支持子操作按钮组 | 已完成 |
| REQ-002-05 | Player 媒体控制插件 | 已完成 |

## 相关 Commits

| Commit | 描述 |
|---|---|
| `b689e60` | feat: 扩展 BasePlugin 支持子操作，Dispatcher 返回结构化插件信息 |
| `1bff447` | feat: 新增 player 媒体控制插件 |
| `c949992` | feat: Web UI 改造支持子操作按钮组 |
| `ce8a5a4` | fix: 修复 CommandResult 序列化问题，calculator 添加中文 label |
