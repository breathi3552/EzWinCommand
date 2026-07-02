# REQ-002-02: Dispatcher list_actions() 返回结构化插件信息

- **父需求**: REQ-002
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

将 `Dispatcher.list_actions()` 的返回值从简单字符串列表升级为结构化字典列表，每个元素包含插件的 `name`、`label` 和 `sub_actions`，供 API 层和前端消费。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `EzWinCommand-server/agent/dispatcher.py` | 修改 | `list_actions()` 方法返回类型和实现改造 |

## 实现要点

### 改造前

```python
def list_actions(self) -> list[str]:
    """返回所有已注册的 action 名称。"""
    return list(self._loader.plugins.keys())
```

### 改造后

```python
def list_actions(self) -> list[dict[str, Any]]:
    """返回所有已注册插件的结构化信息。"""
    result: list[dict[str, Any]] = []
    for name, plugin in self._loader.plugins.items():
        result.append({
            "name": name,
            "label": getattr(plugin, "label", None) or name,
            "sub_actions": plugin.get_sub_actions(),
        })
    return result
```

### 关键决策

- **`label` 回退**：使用 `getattr(plugin, "label", None) or name`，当插件未设置 `label` 或者设置为空字符串时，自动回退到 `name`。这确保了向后兼容——已有的插件即使不设 `label`，前端也能看到可用的显示名称。
- **`sub_actions` 透传**：直接调用 `plugin.get_sub_actions()`，不在此层做任何过滤。简单触发型插件返回空列表 `[]`，前端据此判断渲染方式。
- **返回类型**：`list[dict[str, Any]]` → API 层可以直接序列化为 JSON 数组。
