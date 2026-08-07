"""OLED 护屏插件。"""
from __future__ import annotations

import logging
from typing import Any

from agent.display_power import DisplayPower, DisplayPowerController
from plugins.base import BasePlugin, CommandResult

logger = logging.getLogger(__name__)


class OledSaverPlugin(BasePlugin):
    """通过 Windows 原生消息关闭或恢复显示器，不改变系统运行状态。"""

    name: str = "oled_saver"
    label: str = "OLED 护屏"
    description: str = "关闭显示器显示，不影响 Windows、音频和网络运行"
    version: str = "1.0.0"

    def __init__(self, controller: DisplayPower | None = None) -> None:
        self.controller: DisplayPower = controller or DisplayPowerController()

    def get_sub_actions(self) -> list[dict[str, Any]]:
        return [
            {"id": "turn_off", "label": "进入护屏"},
            {"id": "turn_on", "label": "恢复显示"},
        ]

    def execute(self, params: dict[str, Any]) -> CommandResult:
        sub_action = params.get("sub_action")
        if sub_action == "turn_off":
            action = self.controller.turn_off
            success_message = "已进入护屏"
        elif sub_action == "turn_on":
            action = self.controller.turn_on
            success_message = "已恢复显示"
        else:
            logger.warning("收到无效的 OLED 护屏操作：sub_action=%s", sub_action)
            return CommandResult(False, "无效的护屏操作")

        try:
            success = action()
        except Exception:
            logger.exception("OLED 护屏操作异常：sub_action=%s", sub_action)
            return CommandResult(False, "护屏操作失败")
        if not success:
            logger.error("OLED 护屏操作失败：sub_action=%s", sub_action)
            return CommandResult(False, "护屏操作失败")
        return CommandResult(True, success_message)
