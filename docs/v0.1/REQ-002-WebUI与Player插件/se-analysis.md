# REQ-002 SE 分析

## 现状分析

- 当前 `GET /api/actions` 仅返回插件名列表（`list[str]`），前端只知道有哪些插件注册，但不知道每个插件是否支持子操作。
- Web UI 对所有插件一视同仁地渲染单个按钮，将插件名直接展示在按钮上，用户体验较差——volume 的 +/−/静音只能靠一个按钮糊过去。
- 缺乏统一的子操作抽象：volume 插件内部虽然区分了 up/down/mute，但通过硬编码的 `params` 字段传递，前端无从得知。
- 没有「人类可读名称」概念，前端展示的是 Python `name` 属性（如 `"volume"`）。

## 方案设计

### 核心思路

在 BasePlugin 层引入子操作声明能力，向下传导到 Dispatcher → API → 前端，形成一条完整的子操作链路。

### 详细方案

1. **BasePlugin 新增 `get_sub_actions()` 方法**
   - 返回 `list[dict[str, str]]`，每个元素包含 `id`（子操作标识符）和 `label`（显示文本）。
   - 默认返回空列表，表示「简单触发型」插件（如 calculator），无子操作。
   - 有子操作的插件（如 volume、player）覆写该方法返回操作列表。

2. **BasePlugin 新增 `label` 类属性**
   - 人类可读的插件名称，默认为空字符串。
   - Dispatcher 输出时，若 `label` 为空则回退到 `name`。

3. **Dispatcher `list_actions()` 返回结构化数据**
   - 从 `list[str]` 升级为 `list[dict[str, Any]]`。
   - 每个元素包含 `name`、`label`、`sub_actions` 三个字段。

4. **API `GET /api/actions` 透传结构化数据**
   - API 层无需额外处理，Dispatcher 返回什么就输出什么。

5. **Web UI 根据 `sub_actions` 渲染**
   - `sub_actions` 为空 → 渲染单个按钮，点击发送 `{ action: name }`。
   - `sub_actions` 非空 → 渲染按钮组，每个子操作独立一个按钮，点击发送 `{ action: name, params: { sub_action: id } }`。
   - 使用卡片式布局（`.plugin-card`），每个插件独立成卡，标题显示 `label`。

6. **Player 插件设计**
   - 新增 `player.py`，继承 `BasePlugin`。
   - 定义三个子操作：`play_pause`（播放/暂停）、`prev`（上一曲）、`next`（下一曲）。
   - 使用 `ctypes.windll.user32.keybd_event` 发送虚拟多媒体键（`VK_MEDIA_PLAY_PAUSE` / `VK_MEDIA_NEXT_TRACK` / `VK_MEDIA_PREV_TRACK`），与 volume 插件共享同一 `keybd_event` 模式。
   - 通过 `params.sub_action` 分派具体操作。

### 拆分需求编号

| 编号 | 标题 | 说明 |
|---|---|---|
| REQ-002-01 | BasePlugin 扩展 get_sub_actions() 和 label 属性 | 基类 API 扩展 |
| REQ-002-02 | Dispatcher list_actions() 返回结构化插件信息 | 分发层改造 |
| REQ-002-03 | GET /api/actions 返回结构化 JSON | API 层适配 |
| REQ-002-04 | Web UI 改造支持子操作按钮组 | 前端渲染逻辑 |
| REQ-002-05 | Player 媒体控制插件 | 新插件开发 |

### 依赖关系

```
REQ-002-01 (BasePlugin 扩展)
  ├── REQ-002-02 (Dispatcher 改造)
  │     └── REQ-002-03 (API 适配)
  │           └── REQ-002-04 (Web UI 改造)
  └── REQ-002-05 (Player 插件)
```

REQ-002-01 是基础依赖，所有上层改造都依赖它。REQ-002-05（Player 插件）与 02–04 并行，只需 01 完成即可。
