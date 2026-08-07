"""Windows OLED 护屏流程与键鼠 Raw Input 监听。"""
from __future__ import annotations

import ctypes
import logging
import math
import os
import threading
import time
from collections.abc import Callable
from ctypes import wintypes
from typing import Protocol

from .display_power import DisplayPower, DisplayPowerController

logger = logging.getLogger(__name__)

INITIAL_PROTECTION_DELAY_SECONDS = 5.0
REPROTECTION_DELAY_SECONDS = 60.0

WM_INPUT = 0x00FF
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_QUIT = 0x0012
WM_COMMAND = 0x0111
WM_TIMER = 0x0113
WM_POWERBROADCAST = 0x0218
WM_APP = 0x8000
PBT_POWERSETTINGCHANGE = 0x8013
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001
RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1
RID_INPUT = 0x10000003
RI_KEY_BREAK = 0x0001
RI_KEY_E0 = 0x0002
RI_KEY_E1 = 0x0004
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
ERROR_CLASS_ALREADY_EXISTS = 1410
HWND_MESSAGE = -3
DEVICE_NOTIFY_WINDOW_HANDLE = 0
SW_HIDE = 0
SW_SHOW = 5
SM_CXSCREEN = 0
SM_CYSCREEN = 1
BN_CLICKED = 0
_COUNTDOWN_WINDOW_SHOW = WM_APP + 1
_COUNTDOWN_WINDOW_HIDE = WM_APP + 2
_COUNTDOWN_TIMER_ID = 1
_COUNTDOWN_MESSAGE_CONTROL_ID = 1001
_COUNTDOWN_VALUE_CONTROL_ID = 1002
_COUNTDOWN_CANCEL_CONTROL_ID = 1003
_COUNTDOWN_WINDOW_WIDTH = 320
_COUNTDOWN_WINDOW_HEIGHT = 190
_RAW_INPUT_WINDOW_CLASS = "EzWinCommand.RawInput"
_POWER_MONITOR_WINDOW_CLASS = "EzWinCommand.PowerMonitor"
_COUNTDOWN_WINDOW_CLASS = "EzWinCommand.Countdown"
_RAW_INPUT_START_TIMEOUT_SECONDS = 5.0
_RAW_INPUT_STOP_TIMEOUT_SECONDS = 5.0
_POWER_MONITOR_START_TIMEOUT_SECONDS = 5.0
_POWER_MONITOR_STOP_TIMEOUT_SECONDS = 5.0
_COUNTDOWN_WINDOW_START_TIMEOUT_SECONDS = 5.0
_COUNTDOWN_WINDOW_STOP_TIMEOUT_SECONDS = 5.0


class _GUID(ctypes.Structure):
    """对应 Windows GUID。"""

    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


GUID_MONITOR_POWER_ON = _GUID(
    0x02731015,
    0x4510,
    0x4526,
    (ctypes.c_ubyte * 8)(0x99, 0xE6, 0xE5, 0xA1, 0x7E, 0xBD, 0x1A, 0xEA),
)


class _PowerBroadcastSetting(ctypes.Structure):
    """对应 Windows POWERBROADCAST_SETTING 的固定头部。"""

    _fields_ = [
        ("PowerSetting", _GUID),
        ("DataLength", wintypes.DWORD),
        ("Data", ctypes.c_ubyte * 1),
    ]


class TimerHandle(Protocol):
    """一次性定时器的最小接口。"""

    def start(self) -> None:
        """启动定时器。"""
        ...

    def cancel(self) -> None:
        """取消定时器。"""
        ...


TimerFactory = Callable[[float, Callable[[], None]], TimerHandle]


class RawInputMonitor(Protocol):
    """键盘 Raw Input 监听器的最小接口。"""

    def start(self, on_key_down: Callable[[], None]) -> bool:
        """开始监听，只有键盘 Key Down 才调用回调。"""
        ...

    def stop(self) -> bool:
        """停止监听并释放线程和窗口，返回是否已经退出。"""
        ...


class DisplayPowerMonitor(Protocol):
    """显示器电源状态通知监听器的最小接口。"""

    def start(self, on_monitor_power_on: Callable[[], None]) -> bool:
        """开始监听显示器亮起通知，返回是否成功。"""
        ...

    def stop(self) -> bool:
        """停止监听并释放线程和窗口，返回是否已经退出。"""
        ...


class CountdownWindow(Protocol):
    """倒计时呈现窗口的最小接口。"""

    def show(self, seconds: int, on_cancel: Callable[[], None]) -> bool:
        """显示指定秒数的倒计时并绑定取消回调。"""
        ...

    def hide(self) -> None:
        """隐藏倒计时窗口但保留其窗口线程。"""
        ...

    def close(self) -> None:
        """关闭倒计时窗口并释放窗口线程。"""
        ...


class DisplayProtection(Protocol):
    """护屏流程的最小接口。"""

    def arm(self) -> bool:
        """启动 5 秒初始倒计时护屏流程。"""
        ...

    def close(self) -> None:
        """取消当前流程并释放监听资源。"""
        ...


class _RawInputDevice(ctypes.Structure):
    """对应 Win32 RAWINPUTDEVICE。"""

    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class _RawInputHeader(ctypes.Structure):
    """对应 Win32 RAWINPUTHEADER。"""

    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class _RawKeyboard(ctypes.Structure):
    """对应 RAWKEYBOARD。"""

    _fields_ = [
        ("MakeCode", wintypes.USHORT),
        ("Flags", wintypes.USHORT),
        ("Reserved", wintypes.USHORT),
        ("VKey", wintypes.USHORT),
        ("Message", wintypes.UINT),
        ("ExtraInformation", wintypes.ULONG),
    ]


class WindowsRawInputMonitor:
    """使用 message-only window 接收键盘和鼠标 Raw Input。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._class_name = f"{_RAW_INPUT_WINDOW_CLASS}.{id(self):x}"
        self._thread: threading.Thread | None = None
        self._window: wintypes.HWND | None = None
        self._on_key_down: Callable[[], None] | None = None
        self._pressed_keys: set[tuple[int, int, int]] = set()
        self._stop_event = threading.Event()
        self._ready = threading.Event()
        self._started = False
        self._wnd_proc: Callable[..., int] | None = None

    def start(self, on_key_down: Callable[[], None]) -> bool:
        """在后台线程创建隐藏窗口并注册键盘、鼠标 Raw Input。"""
        if os.name != "nt":
            logger.error("OLED 护屏 Raw Input 监听失败：当前平台不是 Windows")
            return False

        with self._lock:
            active = self._thread is not None and self._thread.is_alive()
        if active:
            self.stop()
            with self._lock:
                if self._thread is not None and self._thread.is_alive():
                    logger.error("OLED 护屏 Raw Input 旧监听线程未能退出")
                    return False

        with self._lock:
            self._thread = None
            self._window = None
            self._on_key_down = on_key_down
            self._pressed_keys.clear()
            self._stop_event.clear()
            self._ready.clear()
            self._started = False
            thread = threading.Thread(
                target=self._run,
                name="EzOledRawInput",
                daemon=True,
            )
            self._thread = thread
            thread.start()

        if not self._ready.wait(_RAW_INPUT_START_TIMEOUT_SECONDS):
            logger.error("OLED 护屏 Raw Input 监听启动超时")
            self.stop()
            return False

        with self._lock:
            thread = self._thread
            return self._started and bool(thread and thread.is_alive())

    def stop(self) -> bool:
        """请求消息循环退出，并等待后台线程自然结束。"""
        with self._lock:
            thread = self._thread
            window = self._window
            thread_id = thread.ident if thread is not None else None
            self._stop_event.set()

        if window is not None and os.name == "nt":
            user32 = None
            posted = False
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                post_message = user32.PostMessageW
                post_message.argtypes = [
                    wintypes.HWND,
                    wintypes.UINT,
                    wintypes.WPARAM,
                    wintypes.LPARAM,
                ]
                post_message.restype = wintypes.BOOL
                posted = bool(post_message(window, WM_CLOSE, 0, 0))
            except (AttributeError, OSError, TypeError, ctypes.ArgumentError):
                logger.exception("停止 OLED 护屏 Raw Input 监听失败")

            if not posted and thread_id is not None and user32 is not None:
                try:
                    post_thread_message = user32.PostThreadMessageW
                    post_thread_message.argtypes = [
                        wintypes.DWORD,
                        wintypes.UINT,
                        wintypes.WPARAM,
                        wintypes.LPARAM,
                    ]
                    post_thread_message.restype = wintypes.BOOL
                    if not post_thread_message(thread_id, WM_QUIT, 0, 0):
                        logger.error("停止 OLED 护屏 Raw Input 监听消息投递失败")
                except (AttributeError, OSError, TypeError, ctypes.ArgumentError):
                    logger.exception("停止 OLED 护屏 Raw Input 监听备用消息投递失败")

        if thread is not None and thread is not threading.current_thread():
            thread.join(_RAW_INPUT_STOP_TIMEOUT_SECONDS)
            if thread.is_alive():
                logger.error("OLED 护屏 Raw Input 监听线程未能及时退出")

        with self._lock:
            if thread is not None and thread is self._thread and not thread.is_alive():
                self._thread = None
            if self._thread is None:
                self._window = None
                self._on_key_down = None
                self._pressed_keys.clear()
                self._started = False
            return self._thread is None or not self._thread.is_alive()

    def _run(self) -> None:
        user32 = None
        kernel32 = None
        hinstance: wintypes.HINSTANCE | None = None
        class_name = self._class_name
        window: wintypes.HWND | None = None
        registered = False
        registered_class = False
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._configure_user32(user32)
            get_module_handle = kernel32.GetModuleHandleW
            get_module_handle.argtypes = [wintypes.LPCWSTR]
            get_module_handle.restype = wintypes.HMODULE
            hinstance = get_module_handle(None)
            if not hinstance:
                logger.error(
                    "创建 OLED 护屏 Raw Input 窗口失败：获取模块句柄错误码=%s",
                    ctypes.get_last_error(),
                )
                return

            with self._lock:
                wnd_proc = self._wnd_proc
            if wnd_proc is None:
                wnd_proc_type = ctypes.WINFUNCTYPE(
                    ctypes.c_ssize_t,
                    wintypes.HWND,
                    wintypes.UINT,
                    wintypes.WPARAM,
                    wintypes.LPARAM,
                )

                @wnd_proc_type
                def callback(hwnd, message, wparam, lparam):
                    return self._window_proc(user32, hwnd, message, wparam, lparam)

                with self._lock:
                    self._wnd_proc = callback
                    wnd_proc = callback

            assert wnd_proc is not None

            window_class = self._window_class(wnd_proc, hinstance, class_name)
            atom = user32.RegisterClassW(ctypes.byref(window_class))
            if atom:
                registered_class = True
            elif ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
                logger.error(
                    "创建 OLED 护屏 Raw Input 窗口失败：注册窗口类错误码=%s",
                    ctypes.get_last_error(),
                )
                return

            window = user32.CreateWindowExW(
                0,
                class_name,
                class_name,
                0,
                0,
                0,
                0,
                0,
                ctypes.c_void_p(HWND_MESSAGE),
                None,
                hinstance,
                None,
            )
            if not window:
                logger.error(
                    "创建 OLED 护屏 Raw Input 窗口失败：Windows 错误码=%s",
                    ctypes.get_last_error(),
                )
                return

            with self._lock:
                self._window = window

            devices = self._raw_input_devices(window)
            if not user32.RegisterRawInputDevices(
                devices,
                len(devices),
                ctypes.sizeof(_RawInputDevice),
            ):
                logger.error(
                    "注册 OLED 护屏键鼠 Raw Input 失败：Windows 错误码=%s",
                    ctypes.get_last_error(),
                )
                return
            registered = True

            with self._lock:
                should_stop = self._stop_event.is_set()
                self._started = not should_stop
            self._ready.set()
            if should_stop:
                user32.PostMessageW(window, WM_CLOSE, 0, 0)

            message = wintypes.MSG()
            while not self._stop_event.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except Exception:
            logger.exception("启动 OLED 护屏 Raw Input 监听失败")
        finally:
            if window is not None and user32 is not None:
                if registered:
                    try:
                        self._unregister_raw_input_devices(user32)
                    except Exception:
                        logger.exception("注销 OLED 护屏 Raw Input 失败")
                try:
                    user32.DestroyWindow(window)
                except Exception:
                    logger.exception("销毁 OLED 护屏 Raw Input 窗口失败")
            if registered_class and user32 is not None and hinstance is not None:
                try:
                    user32.UnregisterClassW(class_name, hinstance)
                except Exception:
                    logger.exception("注销 OLED 护屏 Raw Input 窗口类失败")
            with self._lock:
                self._window = None
                self._started = False
            self._ready.set()

    @staticmethod
    def _configure_user32(user32) -> None:
        user32.RegisterClassW.argtypes = [ctypes.c_void_p]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user32.UnregisterClassW.restype = wintypes.BOOL
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.RegisterRawInputDevices.argtypes = [
            ctypes.POINTER(_RawInputDevice),
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.RegisterRawInputDevices.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.restype = ctypes.c_int
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = wintypes.LPARAM
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        user32.PostQuitMessage.restype = None
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.GetRawInputData.argtypes = [
            wintypes.HANDLE,
            wintypes.UINT,
            wintypes.LPVOID,
            ctypes.POINTER(wintypes.UINT),
            wintypes.UINT,
        ]
        user32.GetRawInputData.restype = wintypes.UINT

    @staticmethod
    def _window_class(wnd_proc, hinstance, class_name: str):
        class WndClass(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        return WndClass(
            0,
            ctypes.cast(wnd_proc, ctypes.c_void_p),
            0,
            0,
            hinstance,
            None,
            None,
            None,
            None,
            class_name,
        )

    @staticmethod
    def _raw_input_devices(window):
        devices = (_RawInputDevice * 2)()
        devices[0] = _RawInputDevice(0x01, 0x06, RIDEV_INPUTSINK, window)
        devices[1] = _RawInputDevice(0x01, 0x02, RIDEV_INPUTSINK, window)
        return devices

    def _window_proc(self, user32, window, message, wparam, lparam):
        if message == WM_INPUT:
            self._handle_raw_input(user32, lparam)
            return user32.DefWindowProcW(window, message, wparam, lparam)
        if message == WM_CLOSE:
            user32.DestroyWindow(window)
            return 0
        if message == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(window, message, wparam, lparam)

    def _handle_raw_input(self, user32, raw_input_handle) -> None:
        size = wintypes.UINT(0)
        header_size = ctypes.sizeof(_RawInputHeader)
        result = user32.GetRawInputData(
            raw_input_handle,
            RID_INPUT,
            None,
            ctypes.byref(size),
            header_size,
        )
        if result == 0xFFFFFFFF or size.value < header_size:
            logger.error(
                "读取 OLED 护屏 Raw Input 失败：Windows 错误码=%s",
                ctypes.get_last_error(),
            )
            return

        buffer = (ctypes.c_ubyte * size.value)()
        result = user32.GetRawInputData(
            raw_input_handle,
            RID_INPUT,
            ctypes.byref(buffer),
            ctypes.byref(size),
            header_size,
        )
        if result == 0xFFFFFFFF or result < header_size:
            logger.error(
                "读取 OLED 护屏 Raw Input 失败：Windows 错误码=%s",
                ctypes.get_last_error(),
            )
            return

        header = _RawInputHeader.from_buffer_copy(buffer)
        if header.dwType != RIM_TYPEKEYBOARD:
            return
        keyboard_offset = ctypes.sizeof(_RawInputHeader)
        if size.value < keyboard_offset + ctypes.sizeof(_RawKeyboard):
            logger.error("读取 OLED 护屏键盘 Raw Input 失败：数据长度不足")
            return
        keyboard = _RawKeyboard.from_buffer_copy(buffer, keyboard_offset)
        key = (
            int(keyboard.MakeCode),
            int(keyboard.VKey),
            int(keyboard.Flags) & (RI_KEY_E0 | RI_KEY_E1),
        )
        with self._lock:
            if keyboard.Flags & RI_KEY_BREAK:
                self._pressed_keys.discard(key)
                return
            if keyboard.Message not in (WM_KEYDOWN, WM_SYSKEYDOWN):
                return
            if key in self._pressed_keys:
                return
            self._pressed_keys.add(key)
            callback = self._on_key_down
        if callback is None:
            return
        try:
            callback()
        except Exception:
            logger.exception("处理 OLED 护屏键盘 Key Down 事件失败")

    def _unregister_raw_input_devices(self, user32) -> None:
        devices = self._raw_input_devices(None)
        for device in devices:
            device.dwFlags = RIDEV_REMOVE
            device.hwndTarget = None
        if not user32.RegisterRawInputDevices(
            devices,
            len(devices),
            ctypes.sizeof(_RawInputDevice),
        ):
            logger.warning(
                "注销 OLED 护屏 Raw Input 失败：Windows 错误码=%s",
                ctypes.get_last_error(),
            )


class WindowsDisplayPowerMonitor:
    """使用隐藏窗口监听 GUID_MONITOR_POWER_ON。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._class_name = f"{_POWER_MONITOR_WINDOW_CLASS}.{id(self):x}"
        self._thread: threading.Thread | None = None
        self._window: wintypes.HWND | None = None
        self._notification: wintypes.HANDLE | None = None
        self._on_monitor_power_on: Callable[[], None] | None = None
        self._stop_event = threading.Event()
        self._ready = threading.Event()
        self._started = False
        self._wnd_proc: Callable[..., int] | None = None

    def start(self, on_monitor_power_on: Callable[[], None]) -> bool:
        """创建消息窗口并注册显示器电源状态通知。"""
        if os.name != "nt":
            logger.error("OLED 护屏显示器电源监听失败：当前平台不是 Windows")
            return False

        with self._lock:
            active = self._thread is not None and self._thread.is_alive()
        if active:
            self.stop()
            with self._lock:
                if self._thread is not None and self._thread.is_alive():
                    logger.error("OLED 护屏旧显示器电源监听线程未能退出")
                    return False

        with self._lock:
            self._thread = None
            self._window = None
            self._notification = None
            self._on_monitor_power_on = on_monitor_power_on
            self._stop_event.clear()
            self._ready.clear()
            self._started = False
            thread = threading.Thread(
                target=self._run,
                name="EzOledPowerMonitor",
                daemon=True,
            )
            self._thread = thread
            thread.start()

        if not self._ready.wait(_POWER_MONITOR_START_TIMEOUT_SECONDS):
            logger.error("OLED 护屏显示器电源监听启动超时")
            self.stop()
            return False

        with self._lock:
            thread = self._thread
            return self._started and bool(thread and thread.is_alive())

    def stop(self) -> bool:
        """请求消息循环退出，并等待后台线程自然结束。"""
        with self._lock:
            thread = self._thread
            window = self._window
            thread_id = thread.ident if thread is not None else None
            self._stop_event.set()

        if window is not None and os.name == "nt":
            user32 = None
            posted = False
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                post_message = user32.PostMessageW
                post_message.argtypes = [
                    wintypes.HWND,
                    wintypes.UINT,
                    wintypes.WPARAM,
                    wintypes.LPARAM,
                ]
                post_message.restype = wintypes.BOOL
                posted = bool(post_message(window, WM_CLOSE, 0, 0))
            except (AttributeError, OSError, TypeError, ctypes.ArgumentError):
                logger.exception("停止 OLED 护屏显示器电源监听失败")

            if not posted and thread_id is not None and user32 is not None:
                try:
                    post_thread_message = user32.PostThreadMessageW
                    post_thread_message.argtypes = [
                        wintypes.DWORD,
                        wintypes.UINT,
                        wintypes.WPARAM,
                        wintypes.LPARAM,
                    ]
                    post_thread_message.restype = wintypes.BOOL
                    if not post_thread_message(thread_id, WM_QUIT, 0, 0):
                        logger.error("停止 OLED 护屏显示器电源监听消息投递失败")
                except (AttributeError, OSError, TypeError, ctypes.ArgumentError):
                    logger.exception("停止 OLED 护屏显示器电源监听备用消息投递失败")

        if thread is not None and thread is not threading.current_thread():
            thread.join(_POWER_MONITOR_STOP_TIMEOUT_SECONDS)
            if thread.is_alive():
                logger.error("OLED 护屏显示器电源监听线程未能及时退出")

        with self._lock:
            if thread is not None and thread is self._thread and not thread.is_alive():
                self._thread = None
            if self._thread is None:
                self._window = None
                self._notification = None
                self._on_monitor_power_on = None
                self._started = False
            return self._thread is None or not self._thread.is_alive()

    def _run(self) -> None:
        user32 = None
        kernel32 = None
        hinstance: wintypes.HINSTANCE | None = None
        class_name = self._class_name
        window: wintypes.HWND | None = None
        notification: wintypes.HANDLE | None = None
        registered_class = False
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._configure_user32(user32)
            get_module_handle = kernel32.GetModuleHandleW
            get_module_handle.argtypes = [wintypes.LPCWSTR]
            get_module_handle.restype = wintypes.HMODULE
            hinstance = get_module_handle(None)
            if not hinstance:
                logger.error(
                    "创建 OLED 护屏电源监听窗口失败：获取模块句柄错误码=%s",
                    ctypes.get_last_error(),
                )
                return

            with self._lock:
                wnd_proc = self._wnd_proc
            if wnd_proc is None:
                wnd_proc_type = ctypes.WINFUNCTYPE(
                    ctypes.c_ssize_t,
                    wintypes.HWND,
                    wintypes.UINT,
                    wintypes.WPARAM,
                    wintypes.LPARAM,
                )

                @wnd_proc_type
                def callback(hwnd, message, wparam, lparam):
                    return self._window_proc(user32, hwnd, message, wparam, lparam)

                with self._lock:
                    self._wnd_proc = callback
                    wnd_proc = callback

            assert wnd_proc is not None
            window_class = self._window_class(wnd_proc, hinstance, class_name)
            atom = user32.RegisterClassW(ctypes.byref(window_class))
            if atom:
                registered_class = True
            elif ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
                logger.error(
                    "创建 OLED 护屏电源监听窗口失败：注册窗口类错误码=%s",
                    ctypes.get_last_error(),
                )
                return

            window = user32.CreateWindowExW(
                0,
                class_name,
                class_name,
                0,
                0,
                0,
                0,
                0,
                ctypes.c_void_p(HWND_MESSAGE),
                None,
                hinstance,
                None,
            )
            if not window:
                logger.error(
                    "创建 OLED 护屏电源监听窗口失败：Windows 错误码=%s",
                    ctypes.get_last_error(),
                )
                return

            with self._lock:
                self._window = window
            notification = user32.RegisterPowerSettingNotification(
                window,
                ctypes.byref(GUID_MONITOR_POWER_ON),
                DEVICE_NOTIFY_WINDOW_HANDLE,
            )
            if not notification:
                logger.error(
                    "注册 OLED 护屏显示器电源通知失败：Windows 错误码=%s",
                    ctypes.get_last_error(),
                )
                return

            with self._lock:
                self._notification = notification
                should_stop = self._stop_event.is_set()
                self._started = not should_stop
            self._ready.set()
            if should_stop:
                user32.PostMessageW(window, WM_CLOSE, 0, 0)

            message = wintypes.MSG()
            while not self._stop_event.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except Exception:
            logger.exception("启动 OLED 护屏显示器电源监听失败")
        finally:
            if notification is not None and user32 is not None:
                try:
                    user32.UnregisterPowerSettingNotification(notification)
                except Exception:
                    logger.exception("注销 OLED 护屏显示器电源通知失败")
            if window is not None and user32 is not None:
                try:
                    user32.DestroyWindow(window)
                except Exception:
                    logger.exception("销毁 OLED 护屏电源监听窗口失败")
            if registered_class and user32 is not None and hinstance is not None:
                try:
                    user32.UnregisterClassW(class_name, hinstance)
                except Exception:
                    logger.exception("注销 OLED 护屏电源监听窗口类失败")
            with self._lock:
                self._window = None
                self._notification = None
                self._started = False
            self._ready.set()

    @staticmethod
    def _configure_user32(user32) -> None:
        user32.RegisterClassW.argtypes = [ctypes.c_void_p]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user32.UnregisterClassW.restype = wintypes.BOOL
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.RegisterPowerSettingNotification.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(_GUID),
            wintypes.DWORD,
        ]
        user32.RegisterPowerSettingNotification.restype = wintypes.HANDLE
        user32.UnregisterPowerSettingNotification.argtypes = [wintypes.HANDLE]
        user32.UnregisterPowerSettingNotification.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.restype = ctypes.c_int
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = wintypes.LPARAM
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        user32.PostQuitMessage.restype = None
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t

    @staticmethod
    def _window_class(wnd_proc, hinstance, class_name: str):
        class WndClass(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        return WndClass(
            0,
            ctypes.cast(wnd_proc, ctypes.c_void_p),
            0,
            0,
            hinstance,
            None,
            None,
            None,
            None,
            class_name,
        )

    def _window_proc(self, user32, window, message, wparam, lparam):
        if message == WM_POWERBROADCAST and wparam == PBT_POWERSETTINGCHANGE:
            self._handle_power_setting_change(lparam)
            return 1
        if message == WM_CLOSE:
            user32.DestroyWindow(window)
            return 0
        if message == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(window, message, wparam, lparam)

    def _handle_power_setting_change(self, lparam) -> None:
        if not lparam:
            return
        try:
            setting = ctypes.cast(
                ctypes.c_void_p(lparam),
                ctypes.POINTER(_PowerBroadcastSetting),
            ).contents
        except (ValueError, TypeError, ctypes.ArgumentError):
            logger.exception("解析 OLED 护屏显示器电源通知失败")
            return
        if not self._same_guid(setting.PowerSetting, GUID_MONITOR_POWER_ON):
            return
        if setting.DataLength < 1 or not setting.Data[0]:
            return
        with self._lock:
            callback = self._on_monitor_power_on
        if callback is None:
            return
        try:
            callback()
        except Exception:
            logger.exception("处理 OLED 护屏显示器亮起通知失败")

    @staticmethod
    def _same_guid(left: _GUID, right: _GUID) -> bool:
        return (
            left.Data1 == right.Data1
            and left.Data2 == right.Data2
            and left.Data3 == right.Data3
            and bytes(left.Data4) == bytes(right.Data4)
        )


class WindowsCountdownWindow:
    """在当前 Windows 用户桌面显示可取消的护屏倒计时。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._class_name = f"{_COUNTDOWN_WINDOW_CLASS}.{id(self):x}"
        self._thread: threading.Thread | None = None
        self._window: wintypes.HWND | None = None
        self._message_control: wintypes.HWND | None = None
        self._value_control: wintypes.HWND | None = None
        self._cancel_control: wintypes.HWND | None = None
        self._on_cancel: Callable[[], None] | None = None
        self._deadline: float | None = None
        self._stop_event = threading.Event()
        self._ready = threading.Event()
        self._started = False
        self._wnd_proc: Callable[..., int] | None = None

    def show(self, seconds: int, on_cancel: Callable[[], None]) -> bool:
        """显示倒计时窗口；窗口计时只负责更新文字，不决定护屏状态。"""
        if os.name != "nt":
            logger.error("OLED 护屏倒计时窗口启动失败：当前平台不是 Windows")
            return False
        if seconds <= 0:
            logger.error("OLED 护屏倒计时窗口启动失败：倒计时必须为正数")
            return False
        if not self._ensure_thread():
            return False
        with self._lock:
            window = self._window
            self._on_cancel = on_cancel
        if window is None:
            return False
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._configure_user32(user32)
        return bool(
            user32.SendMessageW(
                window,
                _COUNTDOWN_WINDOW_SHOW,
                seconds,
                0,
            )
        )

    def hide(self) -> None:
        """隐藏窗口并取消仅用于显示文字的 UI 定时器。"""
        with self._lock:
            window = self._window
        if window is None or os.name != "nt":
            return
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._configure_user32(user32)
            user32.PostMessageW(window, _COUNTDOWN_WINDOW_HIDE, 0, 0)
        except (AttributeError, OSError, TypeError, ctypes.ArgumentError):
            logger.exception("隐藏 OLED 护屏倒计时窗口失败")

    def close(self) -> None:
        """关闭窗口线程。"""
        with self._lock:
            thread = self._thread
            window = self._window
            thread_id = thread.ident if thread is not None else None
            self._stop_event.set()
            self._on_cancel = None
        if window is not None and os.name == "nt":
            user32 = None
            posted = False
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                self._configure_user32(user32)
                posted = bool(user32.PostMessageW(window, WM_CLOSE, 0, 0))
            except (AttributeError, OSError, TypeError, ctypes.ArgumentError):
                logger.exception("关闭 OLED 护屏倒计时窗口失败")
            if not posted and thread_id is not None and user32 is not None:
                try:
                    user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
                except (AttributeError, OSError, TypeError, ctypes.ArgumentError):
                    logger.exception("关闭 OLED 护屏倒计时窗口备用消息投递失败")
        if thread is not None and thread is not threading.current_thread():
            thread.join(_COUNTDOWN_WINDOW_STOP_TIMEOUT_SECONDS)
            if thread.is_alive():
                logger.error("OLED 护屏倒计时窗口线程未能及时退出")
        with self._lock:
            if thread is not None and thread is self._thread and not thread.is_alive():
                self._thread = None
            if self._thread is None:
                self._window = None
                self._message_control = None
                self._value_control = None
                self._cancel_control = None
                self._deadline = None
                self._started = False

    def _ensure_thread(self) -> bool:
        with self._lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                return self._started and self._window is not None
            self._thread = None
            self._window = None
            self._message_control = None
            self._value_control = None
            self._cancel_control = None
            self._stop_event.clear()
            self._ready.clear()
            self._started = False
            thread = threading.Thread(
                target=self._run,
                name="EzOledCountdownWindow",
                daemon=True,
            )
            self._thread = thread
            thread.start()
        if not self._ready.wait(_COUNTDOWN_WINDOW_START_TIMEOUT_SECONDS):
            logger.error("OLED 护屏倒计时窗口启动超时")
            self.close()
            return False
        with self._lock:
            return self._started and self._window is not None

    def _run(self) -> None:
        user32 = None
        kernel32 = None
        hinstance: wintypes.HINSTANCE | None = None
        class_name = self._class_name
        window: wintypes.HWND | None = None
        registered_class = False
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._configure_user32(user32)
            get_module_handle = kernel32.GetModuleHandleW
            get_module_handle.argtypes = [wintypes.LPCWSTR]
            get_module_handle.restype = wintypes.HMODULE
            hinstance = get_module_handle(None)
            if not hinstance:
                logger.error(
                    "创建 OLED 护屏倒计时窗口失败：获取模块句柄错误码=%s",
                    ctypes.get_last_error(),
                )
                return

            with self._lock:
                wnd_proc = self._wnd_proc
            if wnd_proc is None:
                wnd_proc_type = ctypes.WINFUNCTYPE(
                    ctypes.c_ssize_t,
                    wintypes.HWND,
                    wintypes.UINT,
                    wintypes.WPARAM,
                    wintypes.LPARAM,
                )

                @wnd_proc_type
                def callback(hwnd, message, wparam, lparam):
                    return self._window_proc(user32, hwnd, message, wparam, lparam)

                with self._lock:
                    self._wnd_proc = callback
                    wnd_proc = callback

            assert wnd_proc is not None
            window_class = self._window_class(wnd_proc, hinstance, class_name)
            atom = user32.RegisterClassW(ctypes.byref(window_class))
            if atom:
                registered_class = True
            elif ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
                logger.error(
                    "创建 OLED 护屏倒计时窗口失败：注册窗口类错误码=%s",
                    ctypes.get_last_error(),
                )
                return

            screen_width = user32.GetSystemMetrics(SM_CXSCREEN)
            screen_height = user32.GetSystemMetrics(SM_CYSCREEN)
            x = max(0, (screen_width - _COUNTDOWN_WINDOW_WIDTH) // 2)
            y = max(0, (screen_height - _COUNTDOWN_WINDOW_HEIGHT) // 2)
            window = user32.CreateWindowExW(
                0x00000008 | 0x00000080,
                class_name,
                "OLED 护屏",
                0x00C00000 | 0x00080000,
                x,
                y,
                _COUNTDOWN_WINDOW_WIDTH,
                _COUNTDOWN_WINDOW_HEIGHT,
                None,
                None,
                hinstance,
                None,
            )
            if not window:
                logger.error(
                    "创建 OLED 护屏倒计时窗口失败：Windows 错误码=%s",
                    ctypes.get_last_error(),
                )
                return

            child_style = 0x40000000 | 0x10000000
            self._message_control = user32.CreateWindowExW(
                0,
                "STATIC",
                "",
                child_style | 0x00000001,
                20,
                18,
                280,
                30,
                window,
                ctypes.c_void_p(_COUNTDOWN_MESSAGE_CONTROL_ID),
                hinstance,
                None,
            )
            self._value_control = user32.CreateWindowExW(
                0,
                "STATIC",
                "",
                child_style | 0x00000001,
                20,
                52,
                280,
                55,
                window,
                ctypes.c_void_p(_COUNTDOWN_VALUE_CONTROL_ID),
                hinstance,
                None,
            )
            self._cancel_control = user32.CreateWindowExW(
                0,
                "BUTTON",
                "取消",
                child_style,
                105,
                120,
                110,
                32,
                window,
                ctypes.c_void_p(_COUNTDOWN_CANCEL_CONTROL_ID),
                hinstance,
                None,
            )
            if not (
                self._message_control
                and self._value_control
                and self._cancel_control
            ):
                logger.error("创建 OLED 护屏倒计时控件失败")
                return

            with self._lock:
                self._window = window
                should_stop = self._stop_event.is_set()
                self._started = not should_stop
            self._ready.set()
            if should_stop:
                user32.PostMessageW(window, WM_CLOSE, 0, 0)

            message = wintypes.MSG()
            while not self._stop_event.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except Exception:
            logger.exception("启动 OLED 护屏倒计时窗口失败")
        finally:
            if window is not None and user32 is not None:
                try:
                    user32.DestroyWindow(window)
                except Exception:
                    logger.exception("销毁 OLED 护屏倒计时窗口失败")
            if registered_class and user32 is not None and hinstance is not None:
                try:
                    user32.UnregisterClassW(class_name, hinstance)
                except Exception:
                    logger.exception("注销 OLED 护屏倒计时窗口类失败")
            with self._lock:
                self._window = None
                self._message_control = None
                self._value_control = None
                self._cancel_control = None
                self._deadline = None
                self._started = False
            self._ready.set()

    @staticmethod
    def _configure_user32(user32) -> None:
        user32.RegisterClassW.argtypes = [ctypes.c_void_p]
        user32.RegisterClassW.restype = wintypes.ATOM
        user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user32.UnregisterClassW.restype = wintypes.BOOL
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.restype = ctypes.c_int
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = wintypes.LPARAM
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        user32.PostQuitMessage.restype = None
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.SendMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.UpdateWindow.argtypes = [wintypes.HWND]
        user32.UpdateWindow.restype = wintypes.BOOL
        user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        user32.SetWindowTextW.restype = wintypes.BOOL
        user32.SetTimer.argtypes = [
            wintypes.HWND,
            ctypes.c_size_t,
            wintypes.UINT,
            ctypes.c_void_p,
        ]
        user32.SetTimer.restype = ctypes.c_size_t
        user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
        user32.KillTimer.restype = wintypes.BOOL

    @staticmethod
    def _window_class(wnd_proc, hinstance, class_name: str):
        class WndClass(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        return WndClass(
            0,
            ctypes.cast(wnd_proc, ctypes.c_void_p),
            0,
            0,
            hinstance,
            None,
            None,
            None,
            None,
            class_name,
        )

    def _window_proc(self, user32, window, message, wparam, lparam):
        if message == _COUNTDOWN_WINDOW_SHOW:
            seconds = max(1, int(wparam))
            self._deadline = time.monotonic() + seconds
            user32.SetWindowTextW(
                self._message_control,
                f"显示器将在 {seconds} 秒后关闭",
            )
            user32.SetWindowTextW(self._value_control, str(seconds))
            user32.SetTimer(window, _COUNTDOWN_TIMER_ID, 1000, None)
            user32.ShowWindow(window, SW_SHOW)
            user32.UpdateWindow(window)
            return 1
        if message == _COUNTDOWN_WINDOW_HIDE:
            self._hide_window(user32, window)
            return 1
        if message == WM_TIMER and wparam == _COUNTDOWN_TIMER_ID:
            self._update_countdown_text(user32, window)
            return 0
        if message == WM_COMMAND:
            control_id = int(wparam) & 0xFFFF
            notification_code = (int(wparam) >> 16) & 0xFFFF
            if control_id == _COUNTDOWN_CANCEL_CONTROL_ID and notification_code == BN_CLICKED:
                callback = self._on_cancel
                self._on_cancel = None
                self._hide_window(user32, window)
                if callback is not None:
                    callback()
                return 0
        if message == WM_CLOSE:
            callback = self._on_cancel
            self._hide_window(user32, window)
            if callback is not None:
                callback()
            user32.DestroyWindow(window)
            return 0
        if message == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(window, message, wparam, lparam)

    def _hide_window(self, user32, window) -> None:
        user32.KillTimer(window, _COUNTDOWN_TIMER_ID)
        self._deadline = None
        self._on_cancel = None
        user32.ShowWindow(window, SW_HIDE)

    def _update_countdown_text(self, user32, window) -> None:
        if self._deadline is None:
            user32.KillTimer(window, _COUNTDOWN_TIMER_ID)
            return
        seconds = max(0, math.ceil(self._deadline - time.monotonic()))
        user32.SetWindowTextW(self._value_control, str(seconds))
        if seconds == 0:
            user32.KillTimer(window, _COUNTDOWN_TIMER_ID)


def _threading_timer(interval: float, callback: Callable[[], None]) -> TimerHandle:
    timer = threading.Timer(interval, callback)
    timer.daemon = True
    return timer


class DisplayProtectionController:
    """管理初始倒计时、显示器唤醒后的循环护屏和取消生命周期。"""

    _STATE_IDLE = "idle"
    _STATE_INITIAL_COUNTDOWN = "initial_countdown"
    _STATE_WAITING_FOR_WAKE = "waiting_for_wake"
    _STATE_REPROTECTION_COUNTDOWN = "reprotection_countdown"
    _STATE_TURNING_OFF = "turning_off"

    def __init__(
        self,
        power: DisplayPower | None = None,
        input_monitor: RawInputMonitor | None = None,
        power_monitor: DisplayPowerMonitor | None = None,
        countdown_window: CountdownWindow | None = None,
        timer_factory: TimerFactory | None = None,
    ) -> None:
        self._power = power or DisplayPowerController()
        self._input_monitor = input_monitor or WindowsRawInputMonitor()
        self._power_monitor = power_monitor or WindowsDisplayPowerMonitor()
        self._countdown_window = countdown_window or WindowsCountdownWindow()
        self._timer_factory = timer_factory or _threading_timer
        self._lock = threading.RLock()
        self._arm_lock = threading.Lock()
        self._generation = 0
        self._timer_token = 0
        self._timer: TimerHandle | None = None
        self._input_active = False
        self._input_stop_pending = False
        self._power_monitor_active = False
        self._power_monitor_stop_pending = False
        self._state = self._STATE_IDLE
        self._closed = False

    def arm(self) -> bool:
        """取消旧流程后启动键盘监听、电源通知和 5 秒初始倒计时。"""
        with self._arm_lock:
            with self._lock:
                self._closed = False
                self._generation += 1
                generation = self._generation
                old_timer = self._timer
                self._timer = None
                self._timer_token += 1
                input_needs_stop = self._input_active or self._input_stop_pending
                power_needs_stop = (
                    self._power_monitor_active
                    or self._power_monitor_stop_pending
                )
                self._input_active = False
                self._input_stop_pending = input_needs_stop
                self._power_monitor_active = False
                self._power_monitor_stop_pending = power_needs_stop
                self._state = self._STATE_IDLE

            self._cancel_timer(old_timer)
            self._hide_window()
            if input_needs_stop and not self._stop_input_monitor():
                logger.error("OLED 护屏启动失败：旧 Raw Input 监听仍在运行")
                return False
            if power_needs_stop and not self._stop_power_monitor():
                logger.error("OLED 护屏启动失败：旧显示器电源监听仍在运行")
                return False

            with self._lock:
                if generation != self._generation or self._closed:
                    return False

            try:
                started = self._input_monitor.start(
                    lambda: self._on_key_down(generation),
                )
            except Exception:
                logger.exception("OLED 护屏 Raw Input 监听启动异常")
                started = False
            if not started:
                logger.error("OLED 护屏启动失败：无法监听键盘输入")
                self._stop_input_monitor()
                self._deactivate(generation)
                return False
            with self._lock:
                if generation != self._generation or self._closed:
                    stale = True
                else:
                    stale = False
                    self._input_active = True
                    self._input_stop_pending = False
            if stale:
                self._stop_input_monitor()
                return False

            try:
                started = self._power_monitor.start(
                    lambda: self._on_monitor_power_on(generation),
                )
            except Exception:
                logger.exception("OLED 护屏显示器电源监听启动异常")
                started = False
            if not started:
                logger.error("OLED 护屏启动失败：无法监听显示器电源状态")
                self._stop_power_monitor()
                self._deactivate(generation)
                return False
            with self._lock:
                if generation != self._generation or self._closed:
                    stale = True
                else:
                    stale = False
                    self._power_monitor_active = True
                    self._power_monitor_stop_pending = False
            if stale:
                self._stop_power_monitor()
                self._deactivate(generation)
                return False

            return self._start_countdown(
                generation,
                INITIAL_PROTECTION_DELAY_SECONDS,
                self._STATE_INITIAL_COUNTDOWN,
                self._STATE_IDLE,
            )

    def close(self) -> None:
        """取消当前流程并释放定时器、监听器和倒计时窗口。"""
        with self._arm_lock:
            with self._lock:
                self._closed = True
                self._generation += 1
                timer = self._timer
                self._timer = None
                self._timer_token += 1
                input_needs_stop = self._input_active or self._input_stop_pending
                power_needs_stop = (
                    self._power_monitor_active
                    or self._power_monitor_stop_pending
                )
                self._input_active = False
                self._input_stop_pending = input_needs_stop
                self._power_monitor_active = False
                self._power_monitor_stop_pending = power_needs_stop
                self._state = self._STATE_IDLE
            self._cancel_timer(timer)
            self._hide_window()
            if input_needs_stop:
                self._stop_input_monitor()
            if power_needs_stop:
                self._stop_power_monitor()
            try:
                self._countdown_window.close()
            except Exception:
                logger.exception("关闭 OLED 护屏倒计时窗口失败")

    def _on_key_down(self, generation: int) -> None:
        """任意键盘 Key Down 都结束整个护屏循环。"""
        with self._lock:
            if generation != self._generation or self._closed:
                return
            self._generation += 1
            timer = self._timer
            self._timer = None
            self._timer_token += 1
            input_needs_stop = self._input_active or self._input_stop_pending
            power_needs_stop = (
                self._power_monitor_active
                or self._power_monitor_stop_pending
            )
            self._input_active = False
            self._input_stop_pending = input_needs_stop
            self._power_monitor_active = False
            self._power_monitor_stop_pending = power_needs_stop
            self._state = self._STATE_IDLE
        self._cancel_timer(timer)
        self._hide_window()
        if input_needs_stop:
            self._stop_input_monitor()
        if power_needs_stop:
            self._stop_power_monitor()

    def _on_monitor_power_on(self, generation: int) -> None:
        """显示器在等待状态亮起后开始下一轮 60 秒倒计时。"""
        self._start_countdown(
            generation,
            REPROTECTION_DELAY_SECONDS,
            self._STATE_REPROTECTION_COUNTDOWN,
            self._STATE_WAITING_FOR_WAKE,
        )

    def _start_countdown(
        self,
        generation: int,
        seconds: float,
        state: str,
        expected_state: str,
    ) -> bool:
        with self._lock:
            if (
                generation != self._generation
                or self._closed
                or self._state != expected_state
                or self._timer is not None
            ):
                return False
            self._state = state
            self._timer_token += 1
            timer_token = self._timer_token
            try:
                timer = self._timer_factory(
                    seconds,
                    lambda: self._on_timer(generation, timer_token),
                )
            except Exception:
                logger.exception("OLED 护屏定时器创建异常")
                timer = None
            self._timer = timer

        if timer is None:
            self._deactivate(generation)
            return False
        try:
            shown = self._countdown_window.show(
                int(seconds),
                lambda: self._on_key_down(generation),
            )
        except Exception:
            logger.exception("OLED 护屏倒计时窗口显示异常")
            shown = False
        if not shown:
            logger.error("OLED 护屏启动失败：无法显示倒计时窗口")
            self._deactivate(generation)
            return False

        with self._lock:
            stale = (
                generation != self._generation
                or self._closed
                or self._timer is not timer
                or self._state != state
            )
        if stale:
            self._cancel_timer(timer)
            return False
        try:
            timer.start()
        except Exception:
            logger.exception("OLED 护屏定时器启动异常")
            self._deactivate(generation)
            return False
        return True

    def _on_timer(self, generation: int, timer_token: int) -> None:
        """倒计时到期后关闭显示器并进入等待亮起状态。"""
        with self._lock:
            if (
                generation != self._generation
                or self._closed
                or self._timer is None
                or self._timer_token != timer_token
            ):
                return
            self._timer = None
            self._timer_token += 1
            self._state = self._STATE_TURNING_OFF
        self._hide_window()
        try:
            success = self._power.turn_off()
        except Exception:
            logger.exception("OLED 护屏定时关闭显示器异常")
            success = False
        if not success:
            logger.error("OLED 护屏定时关闭显示器失败")
            self._deactivate(generation)
            return
        with self._lock:
            if generation == self._generation and not self._closed:
                self._state = self._STATE_WAITING_FOR_WAKE

    def _deactivate(self, generation: int) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._generation += 1
            timer = self._timer
            self._timer = None
            self._timer_token += 1
            input_needs_stop = self._input_active or self._input_stop_pending
            power_needs_stop = (
                self._power_monitor_active
                or self._power_monitor_stop_pending
            )
            self._input_active = False
            self._input_stop_pending = input_needs_stop
            self._power_monitor_active = False
            self._power_monitor_stop_pending = power_needs_stop
            self._state = self._STATE_IDLE
        self._cancel_timer(timer)
        self._hide_window()
        if input_needs_stop:
            self._stop_input_monitor()
        if power_needs_stop:
            self._stop_power_monitor()

    def _hide_window(self) -> None:
        try:
            self._countdown_window.hide()
        except Exception:
            logger.exception("隐藏 OLED 护屏倒计时窗口失败")

    @staticmethod
    def _cancel_timer(timer: TimerHandle | None) -> None:
        if timer is None:
            return
        try:
            timer.cancel()
        except Exception:
            logger.exception("OLED 护屏定时器取消异常")

    def _stop_input_monitor(self) -> bool:
        try:
            stopped = self._input_monitor.stop()
        except Exception:
            logger.exception("OLED 护屏 Raw Input 监听停止异常")
            with self._lock:
                self._input_stop_pending = True
            return False
        if not stopped:
            logger.debug("OLED 护屏 Raw Input 监听线程仍在运行，保留停止重试状态")
            with self._lock:
                self._input_stop_pending = True
            return False
        with self._lock:
            self._input_stop_pending = False
        return True

    def _stop_power_monitor(self) -> bool:
        try:
            stopped = self._power_monitor.stop()
        except Exception:
            logger.exception("OLED 护屏显示器电源监听停止异常")
            with self._lock:
                self._power_monitor_stop_pending = True
            return False
        if not stopped:
            logger.debug(
                "OLED 护屏显示器电源监听线程仍在运行，保留停止重试状态",
            )
            with self._lock:
                self._power_monitor_stop_pending = True
            return False
        with self._lock:
            self._power_monitor_stop_pending = False
        return True
