"""Demo 插件：音量控制。

通过模拟键盘多媒体按键来控制系统音量。
需要 pywin32。
"""
from typing import Any

from plugins.base import BasePlugin, CommandResult


class VolumePlugin(BasePlugin):
    name = "volume"
    label = "音量控制"

    def get_sub_actions(self) -> list[dict[str, str]]:
        return [
            {"id": "up",   "label": "+"},
            {"id": "down", "label": "-"},
            {"id": "mute", "label": "静音"},
        ]

    VK_VOLUME_MUTE = 0xAD
    VK_VOLUME_DOWN = 0xAE
    VK_VOLUME_UP = 0xAF
    KEYEVENTF_KEYUP = 0x0002

    def execute(self, params: dict[str, Any]) -> CommandResult:
        sub_action = params.get("sub_action", "up")

        if sub_action == "up":
            return self._send_key(self.VK_VOLUME_UP, "音量+")
        elif sub_action == "down":
            return self._send_key(self.VK_VOLUME_DOWN, "音量-")
        elif sub_action == "mute":
            return self._send_key(self.VK_VOLUME_MUTE, "静音切换")
        else:
            return CommandResult(success=False, message=f"未知操作: {sub_action}")

    @staticmethod
    def _send_key(vk_code: int, label: str) -> CommandResult:
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, VolumePlugin.KEYEVENTF_KEYUP, 0)
            return CommandResult(success=True, message=label)
        except Exception as exc:
            return CommandResult(success=False, message=f"音量控制失败: {exc}")
