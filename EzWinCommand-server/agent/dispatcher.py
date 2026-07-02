"""命令分发器。

API 不直接执行命令，而是通过 Dispatcher 分发到对应插件。
"""
from dataclasses import dataclass, field
from typing import Any

from plugins.loader import PluginLoader


@dataclass
class CommandResult:
    success: bool
    message: str = ""
    data: dict[str, Any] | None = None


class Dispatcher:
    """注册插件并分发命令。"""

    def __init__(self) -> None:
        self._loader = PluginLoader()

    def discover_plugins(self, plugin_dir: str = "plugins") -> None:
        """扫描并加载插件目录。"""
        self._loader.discover(plugin_dir)

    def execute(self, action: str, params: dict[str, Any] | None = None) -> CommandResult:
        """分发命令到对应插件。

        Args:
            action: 插件注册名（如 "calculator", "volume"）。
            params: 插件所需的参数字典。

        Returns:
            CommandResult，success 为 False 时 message 包含错误描述。
        """
        plugin = self._loader.get(action)
        if plugin is None:
            return CommandResult(success=False, message=f"未知命令: {action}")

        try:
            return plugin.execute(params or {})
        except Exception as exc:
            return CommandResult(success=False, message=f"插件执行异常: {exc}")

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
