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

    def __init__(self) -> None:
        self.plugins: dict[str, BasePlugin] = {}

    def discover(self, plugin_dir: str | Path, package: str = "plugins") -> None:
        """扫描 plugin_dir 目录，加载所有合法插件。

        plugin_dir 可为绝对 Path；package 用于构造 import 路径，避免依赖当前工作目录。
        """
        root = Path(plugin_dir)
        if not root.is_dir():
            logger.warning("插件目录不存在: %s", root)
            return

        for py_file in root.glob("*.py"):
            if py_file.name.startswith("_"):
                continue  # 跳过 __init__.py 和私有模块

            module_path = f"{package}.{py_file.stem}"
            try:
                module = importlib.import_module(module_path)
            except Exception:
                logger.exception("加载插件模块失败: %s", module_path)
                continue

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if not isinstance(attr, type) or not issubclass(attr, BasePlugin):
                    continue
                if attr is BasePlugin:
                    continue

                plugin: BasePlugin = attr()
                if not plugin.name:
                    logger.warning("插件 %s 未设置 name，已跳过", attr_name)
                    continue
                if plugin.name in self.plugins:
                    logger.warning("插件名冲突: %s，后加载的覆盖先加载的", plugin.name)

                self.plugins[plugin.name] = plugin
                logger.info("已加载插件: %s (%s)", plugin.name, attr_name)

    def get(self, name: str) -> BasePlugin | None:
        """按名称获取插件实例。"""
        return self.plugins.get(name)
