"""插件自动发现与加载。

遍历 plugin_dir 下的 .py 文件，动态导入 BasePlugin 子类并注册。
"""
import importlib
import logging
from pathlib import Path
from typing import Any

from plugins.base import BasePlugin

logger = logging.getLogger(__name__)


class PluginLoader:
    """管理插件的发现、加载与查找。"""

    def __init__(
        self,
        enabled: dict[str, bool] | None = None,
    ) -> None:
        self.plugins: dict[str, BasePlugin] = {}
        self._enabled: dict[str, bool] = enabled or {}
        self.errors: list[dict[str, str]] = []

    def discover(
        self,
        plugin_dir: str | Path,
        package: str = "plugins",
        exclude: set[str] | None = None,
    ) -> None:
        """扫描 plugin_dir 目录，加载所有合法插件。

        plugin_dir 可为绝对 Path；package 用于构造 import 路径，避免依赖当前工作目录。
        加载失败的模块记录到 self.errors，不中断后续加载。
        """
        root = Path(plugin_dir)
        if not root.is_dir():
            logger.warning("插件目录不存在: %s", root)
            return

        for py_file in root.glob("*.py"):
            if py_file.name.startswith("_"):
                continue  # 跳过 __init__.py 和私有模块
            if py_file.stem in (exclude or set()):
                continue

            module_path = f"{package}.{py_file.stem}"
            module_name = py_file.stem
            try:
                module = importlib.import_module(module_path)
            except Exception as exc:
                logger.exception("加载插件模块失败: %s", module_path)
                self.errors.append({
                    "name": module_name,
                    "error": f"模块导入失败: {exc}",
                })
                continue

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if not isinstance(attr, type) or not issubclass(attr, BasePlugin):
                    continue
                if attr is BasePlugin:
                    continue

                try:
                    plugin: BasePlugin = attr()
                except Exception as exc:
                    logger.exception("实例化插件失败: %s", attr_name)
                    self.errors.append({
                        "name": attr_name,
                        "error": f"实例化失败: {exc}",
                    })
                    continue

                self.register(plugin)

    def register(self, plugin: BasePlugin) -> None:
        """注册已构造插件，复用 discovery 的名称与冲突语义。"""
        if not plugin.name:
            logger.warning("插件 %s 未设置 name，已跳过", type(plugin).__name__)
            return
        if plugin.name in self.plugins:
            logger.warning("插件名冲突: %s，后加载的覆盖先加载的", plugin.name)
        self.plugins[plugin.name] = plugin
        logger.info("已加载插件: %s (%s)，enabled=%s", plugin.name, type(plugin).__name__, self.is_enabled(plugin.name))

    def get(self, name: str) -> BasePlugin | None:
        """按名称获取插件实例。"""
        return self.plugins.get(name)

    def is_enabled(self, name: str) -> bool:
        """检查插件是否启用。

        未在启用表中显式记录的插件默认启用。
        """
        entry = self._enabled.get(name)
        if entry is None:
            return True
        return entry

    def set_enabled(self, name: str, enabled: bool) -> None:
        """设置插件启用状态。"""
        self._enabled[name] = enabled
