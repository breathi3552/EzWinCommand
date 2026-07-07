"""命令分发器。

API 不直接执行命令，而是通过 Dispatcher 分发到对应插件。
"""
from pathlib import Path
import logging
import json
from typing import Any


from plugins.base import CommandResult
from plugins.loader import PluginLoader
logger = logging.getLogger(__name__)



class Dispatcher:
    """注册插件并分发命令。"""

    def __init__(self, plugins_json_path: str | Path | None = None) -> None:
        self._plugins_json_path = Path(plugins_json_path) if plugins_json_path else None
        self._enabled: dict[str, bool] = {}

        # 加载启用状态文件
        if self._plugins_json_path and self._plugins_json_path.is_file():
            try:
                data = json.loads(self._plugins_json_path.read_text(encoding="utf-8"))
                raw = data.get("plugins", {}) if isinstance(data, dict) else {}
                self._enabled = {
                    k: v.get("enabled", True) if isinstance(v, dict) else bool(v)
                    for k, v in raw.items()
                }
            except Exception as exc:
                logger.warning("读取插件启用状态文件失败，将全部启用: %s", exc)

        self._loader = PluginLoader(enabled=self._enabled)

    def _save_enabled_state(self) -> None:
        """将当前启用状态写回 JSON 文件。"""
        if not self._plugins_json_path:
            return
        data = {
            "version": 1,
            "plugins": {
                name: {"enabled": self._enabled.get(name, True)}
                for name in list(self._loader.plugins.keys())
            },
        }
        try:
            self._plugins_json_path.parent.mkdir(parents=True, exist_ok=True)
            self._plugins_json_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("保存插件启用状态失败: %s", exc)

    def discover_plugins(
        self,
        plugin_dir: str | Path = "plugins",
        package: str = "plugins",
    ) -> None:
        """扫描并加载插件目录。"""
        self._loader.discover(plugin_dir, package=package)

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

        if not self._loader.is_enabled(action):
            return CommandResult(success=False, message=f"插件已禁用: {action}")

        try:
            return plugin.execute(params or {})
        except Exception as exc:
            return CommandResult(success=False, message=f"插件执行异常: {exc}")

    def list_plugins(self, include_disabled: bool = True) -> list[dict[str, Any]]:
        """返回所有已注册插件的完整信息。

        Args:
            include_disabled: 若为 False，仅返回已启用且无加载错误的插件。

        Returns:
            插件信息列表，每项包含 metadata、子操作、启用状态、加载错误等。
        """
        result: list[dict[str, Any]] = []
        for name, plugin in self._loader.plugins.items():
            enabled = self._loader.is_enabled(name)
            if not include_disabled and not enabled:
                continue

            metadata = plugin.get_metadata()
            result.append({
                **metadata,
                "enabled": enabled,
                "builtin": True,
                "sub_actions": plugin.get_sub_actions(),
                "load_error": None,
            })

        # 包含有加载错误但无插件实例的记录
        if include_disabled:
            for err in self._loader.errors:
                result.append({
                    "name": err["name"],
                    "label": err["name"],
                    "description": "",
                    "version": "",
                    "enabled": False,
                    "builtin": False,
                    "sub_actions": [],
                    "load_error": err.get("error", "未知加载错误"),
                })

        return result

    def list_actions(self) -> list[dict[str, Any]]:
        """返回所有已启用且无加载错误的插件信息（用于 `/api/actions` API）。"""
        return self.list_plugins(include_disabled=False)

    def set_plugin_enabled(self, name: str, enabled: bool) -> bool:
        """设置指定插件的启用状态。

        Returns:
            True 如果插件存在；False 如果插件名未知。
        """
        if name not in self._loader.plugins:
            return False
        self._loader.set_enabled(name, enabled)
        self._save_enabled_state()
        return True
