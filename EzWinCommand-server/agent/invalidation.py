"""设备关系撤销后的窄失效 seam 与生产 projection 组合。"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeviceRevoked:
    """设备授权已移除的非敏感事实。"""

    device_id: str


class DeviceInvalidationHub:
    """按固定顺序驱动设备撤销的两个生产 projection。"""

    def __init__(
        self,
        local_publish: Callable[[frozenset[str]], None],
        media_revoke: Callable[[DeviceRevoked], None],
    ) -> None:
        self._local_publish: Callable[[frozenset[str]], None] = local_publish
        self._media_revoke: Callable[[DeviceRevoked], None] = media_revoke

    def publish(self, event: DeviceRevoked) -> None:
        """先终止目标媒体流，再通知本机管理页重新读取权威状态。"""
        self._media_revoke(event)
        self._local_publish(frozenset({"devices"}))
