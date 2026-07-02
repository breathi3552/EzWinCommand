"""媒体播放控制插件。

通过模拟多媒体键盘按键来控制系统媒体播放。
"""
from typing import Any

from plugins.base import BasePlugin, CommandResult


class PlayerPlugin(BasePlugin):
    name = "player"
    label = "媒体控制"

    # 虚拟键码
    VK_MEDIA_PLAY_PAUSE = 0xB3
    VK_MEDIA_NEXT_TRACK  = 0xB0
    VK_MEDIA_PREV_TRACK  = 0xB1
    KEYEVENTF_KEYUP      = 0x0002

    def get_sub_actions(self) -> list[dict[str, str]]:
        return [
            {"id": "play_pause", "label": "播放/暂停"},
            {"id": "prev",       "label": "上一曲"},
            {"id": "next",       "label": "下一曲"},
        ]

    def execute(self, params: dict[str, Any]) -> CommandResult:
        sub_action = params.get("sub_action", "play_pause")

        mapping: dict[str, tuple[int, str]] = {
            "play_pause": (self.VK_MEDIA_PLAY_PAUSE, "播放/暂停"),
            "next":       (self.VK_MEDIA_NEXT_TRACK,  "下一曲"),
            "prev":       (self.VK_MEDIA_PREV_TRACK,  "上一曲"),
        }

        if sub_action not in mapping:
            return CommandResult(success=False, message=f"未知操作: {sub_action}")

        vk_code, label = mapping[sub_action]
        return self._send_key(vk_code, label)

    @staticmethod
    def _send_key(vk_code: int, label: str) -> CommandResult:
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(
                vk_code, 0, PlayerPlugin.KEYEVENTF_KEYUP, 0
            )
            return CommandResult(success=True, message=label)
        except Exception as exc:
            return CommandResult(success=False, message=f"媒体控制失败: {exc}")
