"""Windows 原生显示器电源控制。

该模块只发送 ``SC_MONITORPOWER`` 系统消息，不调用 Sleep/Hibernate、DDC/CI
或输入设备 API。Windows 的显示器电源管理负责后续的唤醒行为。
"""
from __future__ import annotations

import ctypes
import logging
import os
from collections.abc import Callable
from ctypes import wintypes
from typing import Protocol

logger = logging.getLogger(__name__)

HWND_BROADCAST = 0xFFFF
WM_SYSCOMMAND = 0x0112
SC_MONITORPOWER = 0xF170
SMTO_ABORTIFHUNG = 0x0002
MONITOR_POWER_OFF = 2
MONITOR_POWER_ON = -1
_SEND_TIMEOUT_MS = 1000
_DWORD_PTR = ctypes.c_size_t


def _send_monitor_power_message(power_state: int, timeout_ms: int = _SEND_TIMEOUT_MS) -> bool:
    """向所有顶层窗口发送 Windows 显示器电源消息。"""
    if os.name != "nt":
        logger.error("显示器电源控制失败：当前平台不是 Windows")
        return False

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        send_message_timeout = user32.SendMessageTimeoutW
        send_message_timeout.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(_DWORD_PTR),
        ]
        send_message_timeout.restype = wintypes.LPARAM
        result = _DWORD_PTR()
        sent = bool(
            send_message_timeout(
                HWND_BROADCAST,
                WM_SYSCOMMAND,
                SC_MONITORPOWER,
                power_state,
                SMTO_ABORTIFHUNG,
                timeout_ms,
                ctypes.byref(result),
            )
        )
    except (AttributeError, OSError, TypeError, ctypes.ArgumentError):
        logger.exception("发送显示器电源消息失败：power_state=%s", power_state)
        return False

    if not sent:
        logger.error(
            "发送显示器电源消息失败：power_state=%s，Windows 错误码=%s",
            power_state,
            ctypes.get_last_error(),
        )
        return False
    return True


class DisplayPower(Protocol):
    """显示器电源控制器的内部接口。"""

    def turn_off(self) -> bool:
        """请求关闭显示器。"""
        ...

    def turn_on(self) -> bool:
        """请求恢复显示器。"""
        ...


class DisplayPowerController:
    """提供关闭和恢复显示器的最小接口。"""

    def __init__(self, send_message: Callable[[int], bool] | None = None) -> None:
        self._send_message: Callable[[int], bool] = send_message or _send_monitor_power_message

    def turn_off(self) -> bool:
        """请求 Windows 关闭活动显示器。"""
        return self._send_message(MONITOR_POWER_OFF)

    def turn_on(self) -> bool:
        """请求 Windows 恢复显示器。"""
        return self._send_message(MONITOR_POWER_ON)
