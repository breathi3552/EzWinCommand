"""OLED 护屏插件。"""
from __future__ import annotations

import logging
from typing import Any

from agent.display_protection import DisplayProtection, DisplayProtectionController
from plugins.base import BasePlugin, CommandResult

logger = logging.getLogger(__name__)


class OledSaverPlugin(BasePlugin):
    """启动一次性延时护屏流程，不改变其他系统运行状态。"""

    name: str = "oled_saver"
    label: str = "OLED 护屏"
    description: str = "等待 60 秒后关闭显示器，键盘或鼠标输入会取消护屏"
    version: str = "1.1.0"

    def __init__(self, controller: DisplayProtection | None = None) -> None:
        self.controller: DisplayProtection = controller or DisplayProtectionController()

    def get_sub_actions(self) -> list[dict[str, Any]]:
        return [{"id": "turn_off", "label": "进入护屏"}]

    def execute(self, params: dict[str, Any]) -> CommandResult:
        if params.get("sub_action") != "turn_off":
            logger.warning(
                "收到无效的 OLED 护屏操作：sub_action=%s",
                params.get("sub_action"),
            )
            return CommandResult(False, "无效的护屏操作")

        try:
            success = self.controller.arm()
        except Exception:
            logger.exception("OLED 护屏启动异常")
            return CommandResult(False, "护屏操作失败")
        if not success:
            logger.error("OLED 护屏启动失败")
            return CommandResult(False, "护屏操作失败")
        return CommandResult(True, "已启动护屏，60 秒后关闭显示器")

    def close(self) -> None:
        """释放本插件的定时器和 Raw Input 监听。"""
        try:
            self.controller.close()
        except Exception:
            logger.exception("关闭 OLED 护屏资源失败")
