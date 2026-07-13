"""媒体插件；仅由 app 显式注册，不参与反射实例化。"""
from __future__ import annotations

from concurrent.futures import TimeoutError
from typing import Any

from media.service import MediaService
from plugins.base import BasePlugin, CommandResult


class MediaPlugin(BasePlugin):
    name = "media"
    label = "媒体"
    description = "控制系统当前媒体、主音量与默认音频设备"
    version = "1.0.0"

    def __init__(self, service: MediaService) -> None:
        self.service = service

    def get_sub_actions(self) -> list[dict[str, Any]]:
        return [
            {"id": "play_pause", "label": "播放/暂停"},
            {"id": "prev", "label": "上一首"},
            {"id": "next", "label": "下一首"},
        ]

    def execute(self, params: dict[str, Any]) -> CommandResult:
        sub_action = params.get("sub_action")
        if not isinstance(sub_action, str):
            return CommandResult(False, "无效的媒体操作")
        future = self.service.submit(
            sub_action,
            volume=params.get("volume"),
            endpoint_id=params.get("endpoint_id"),
        )
        try:
            return future.result(timeout=5.0)
        except TimeoutError:
            future.cancel()
            return CommandResult(False, "媒体服务响应超时")
