# REQ-001-03: Dispatcher 分发器

- **父需求**: REQ-001
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

实现命令分发器 `Dispatcher`，作为 API 层与插件层之间的中间层。API 不直接执行命令，而是通过 Dispatcher 根据 action 名称查找对应插件并调用其 `execute()` 方法。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| EzWinCommand-server/agent/dispatcher.py | 新增 | Dispatcher 分发器实现 |

## 实现要点

### Dispatcher 类

```python
class Dispatcher:
    def __init__(self) -> None:
        self._loader = PluginLoader()

    def discover_plugins(self, plugin_dir: str = "plugins") -> None
    def execute(self, action: str, params: dict | None = None) -> CommandResult
    def list_actions(self) -> list[dict[str, Any]]
```

### discover_plugins(plugin_dir)

- 委托 `PluginLoader.discover(plugin_dir)` 完成插件扫描与加载
- 在 `app.py` 启动时调用，传入 `"plugins"` 目录路径

### execute(action, params)

1. 调用 `self._loader.get(action)` 按名称查找插件实例
2. 未找到 → 返回 `CommandResult(success=False, message="未知命令: {action}")`
3. 调用 `plugin.execute(params or {})` 执行插件逻辑
4. 捕获任意异常 → 返回 `CommandResult(success=False, message="插件执行异常: {exc}")`

### list_actions()

- 遍历 `self._loader.plugins` 中所有已注册插件
- 每个插件返回结构化信息：
  ```python
  {
      "name": plugin.name,
      "label": getattr(plugin, "label", None) or plugin.name,
      "sub_actions": plugin.get_sub_actions(),
  }
  ```
- 供 Web UI 和客户端动态渲染控制按钮

### 启动集成

- 在 `app.py` 中创建 `Dispatcher` 单例
- 存入 `app.state.dispatcher`，API 路由通过 `Request.app.state` 访问
- 启动时立即调用 `discover_plugins()`，加载完毕打印已加载插件数量和名称
