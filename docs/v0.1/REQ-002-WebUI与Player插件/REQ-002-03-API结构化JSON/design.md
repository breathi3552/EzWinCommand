# REQ-002-03: GET /api/actions 返回结构化 JSON

- **父需求**: REQ-002
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

`GET /api/actions` 端点无需修改代码逻辑——Dispatcher 已经返回结构化数据，API 层直接透传即可。本需求验证该端点能正确输出新的 JSON 结构。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `EzWinCommand-server/agent/api.py` | 不变 | 端点逻辑无需修改，透明透传 Dispatcher 输出 |

## 实现要点

### API 响应格式

**改造前：**
```json
{
  "actions": ["calculator", "volume"]
}
```

**改造后：**
```json
{
  "actions": [
    {
      "name": "calculator",
      "label": "计算器",
      "sub_actions": []
    },
    {
      "name": "volume",
      "label": "音量控制",
      "sub_actions": [
        { "id": "up",   "label": "+" },
        { "id": "down", "label": "-" },
        { "id": "mute", "label": "静音" }
      ]
    }
  ]
}
```

### 关键点

- API 代码零改动：`list_actions()` 端点只是调用 `dispatcher.list_actions()` 并包装为 `{"actions": ...}`，Dispatcher 返回什么就序列化什么。
- 向后兼容：旧前端如果只用到 `actions[i]` 的名称，需要同步改造。但本次迭代中 REQ-002-04 会同时完成前端改造，不存在过渡期兼容问题。
- `POST /api/command` 端点也涉及相关修正：`ce8a5a4` commit 修复了 `CommandResult.__dict__` → `to_dict()` 的序列化问题，确保 `CommandResult` 能正确序列化为 JSON。
