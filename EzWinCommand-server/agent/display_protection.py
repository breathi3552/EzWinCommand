"""Windows OLED 护屏流程与键鼠 Raw Input 监听。"""
from __future__ import annotations

import ctypes
import logging
import os
import threading
from collections.abc import Callable
from ctypes import wintypes
from typing import Protocol

from .display_power import DisplayPower, DisplayPowerController

logger = logging.getLogger(__name__)

DISPLAY_PROTECTION_DELAY_SECONDS = 60.0

WM_INPUT = 0x00FF
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_QUIT = 0x0012
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001
RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1
RID_INPUT = 0x10000003
ERROR_CLASS_ALREADY_EXISTS = 1410
HWND_MESSAGE = -3
_RAW_INPUT_WINDOW_CLASS = "EzWinCommand.RawInput"
_RAW_INPUT_START_TIMEOUT_SECONDS = 5.0
_RAW_INPUT_STOP_TIMEOUT_SECONDS = 5.0


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
    """键盘和鼠标 Raw Input 监听器的最小接口。"""

    def start(self, on_input: Callable[[], None]) -> bool:
        """开始监听，返回是否成功。"""
        ...

    def stop(self) -> bool:
        """停止监听并释放线程和窗口，返回是否已经退出。"""
        ...


class DisplayProtection(Protocol):
    """护屏流程的最小接口。"""

    def arm(self) -> bool:
        """启动一次性延时护屏流程。"""
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


class WindowsRawInputMonitor:
    """使用 message-only window 接收键盘和鼠标 Raw Input。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._class_name = f"{_RAW_INPUT_WINDOW_CLASS}.{id(self):x}"
        self._thread: threading.Thread | None = None
        self._window: wintypes.HWND | None = None
        self._on_input: Callable[[], None] | None = None
        self._stop_event = threading.Event()
        self._ready = threading.Event()
        self._started = False
        self._wnd_proc: Callable[..., int] | None = None

    def start(self, on_input: Callable[[], None]) -> bool:
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
            self._on_input = on_input
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
                self._on_input = None
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
        if header.dwType not in (RIM_TYPEMOUSE, RIM_TYPEKEYBOARD):
            return
        callback = self._on_input
        if callback is None:
            return
        try:
            callback()
        except Exception:
            logger.exception("处理 OLED 护屏 Raw Input 事件失败")

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


def _threading_timer(interval: float, callback: Callable[[], None]) -> TimerHandle:
    timer = threading.Timer(interval, callback)
    timer.daemon = True
    return timer


class DisplayProtectionController:
    """管理一次性延时关屏与输入取消的线程安全生命周期。"""

    def __init__(
        self,
        power: DisplayPower | None = None,
        input_monitor: RawInputMonitor | None = None,
        timer_factory: TimerFactory | None = None,
    ) -> None:
        self._power = power or DisplayPowerController()
        self._input_monitor = input_monitor or WindowsRawInputMonitor()
        self._timer_factory = timer_factory or _threading_timer
        self._lock = threading.RLock()
        self._arm_lock = threading.Lock()
        self._generation = 0
        self._timer: TimerHandle | None = None
        self._monitor_active = False
        self._monitor_stop_pending = False
        self._closed = False

    def arm(self) -> bool:
        """取消旧流程后启动一次性 60 秒定时器和键鼠监听。"""
        with self._arm_lock:
            with self._lock:
                self._closed = False
                self._generation += 1
                generation = self._generation
                old_timer = self._timer
                self._timer = None
                monitor_needs_stop = self._monitor_active or self._monitor_stop_pending
                self._monitor_active = False
                self._monitor_stop_pending = monitor_needs_stop

            self._cancel_timer(old_timer)
            if monitor_needs_stop and not self._stop_monitor():
                logger.error("OLED 护屏启动失败：旧 Raw Input 监听仍在运行")
                return False

            with self._lock:
                if generation != self._generation or self._closed:
                    return False

            try:
                started = self._input_monitor.start(
                    lambda: self._on_input(generation),
                )
            except Exception:
                logger.exception("OLED 护屏 Raw Input 监听启动异常")
                started = False
            if not started:
                logger.error("OLED 护屏启动失败：无法监听键盘和鼠标输入")
                self._stop_monitor()
                self._deactivate(generation)
                return False

            with self._lock:
                if generation != self._generation or self._closed:
                    stale = True
                    timer = None
                else:
                    stale = False
                    self._monitor_active = True
                    self._monitor_stop_pending = False
                    try:
                        timer = self._timer_factory(
                            DISPLAY_PROTECTION_DELAY_SECONDS,
                            lambda: self._on_timer(generation),
                        )
                    except Exception:
                        logger.exception("OLED 护屏定时器创建异常")
                        timer = None
                    self._timer = timer

            if stale:
                self._stop_monitor()
                return False
            if timer is None:
                self._deactivate(generation)
                return False

            try:
                timer.start()
            except Exception:
                logger.exception("OLED 护屏定时器启动异常")
                self._deactivate(generation)
                return False
            return True

    def close(self) -> None:
        """取消定时器并停止 Raw Input，不主动恢复或关闭显示器。"""
        with self._arm_lock:
            with self._lock:
                self._closed = True
                self._generation += 1
                timer = self._timer
                self._timer = None
                monitor_needs_stop = self._monitor_active or self._monitor_stop_pending
                self._monitor_active = False
                self._monitor_stop_pending = monitor_needs_stop
            self._cancel_timer(timer)
            if monitor_needs_stop:
                self._stop_monitor()

    def _on_input(self, generation: int) -> None:
        """在本次流程收到键盘或鼠标输入后彻底退出。"""
        with self._lock:
            if generation != self._generation or self._closed:
                return
            self._generation += 1
            timer = self._timer
            self._timer = None
            self._monitor_active = False
            self._monitor_stop_pending = True
        self._cancel_timer(timer)
        self._stop_monitor()

    def _on_timer(self, generation: int) -> None:
        """定时器到期时只尝试一次关闭显示器。"""
        stop_monitor = False
        with self._lock:
            if generation != self._generation or self._closed or self._timer is None:
                return
            self._timer = None
            try:
                success = self._power.turn_off()
            except Exception:
                logger.exception("OLED 护屏定时关闭显示器异常")
                success = False
            if not success:
                logger.error("OLED 护屏定时关闭显示器失败")
                self._generation += 1
                stop_monitor = True
                self._monitor_active = False
                self._monitor_stop_pending = True
        if stop_monitor:
            self._stop_monitor()

    def _deactivate(self, generation: int) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._generation += 1
            timer = self._timer
            self._timer = None
            monitor_needs_stop = self._monitor_active or self._monitor_stop_pending
            self._monitor_active = False
            self._monitor_stop_pending = monitor_needs_stop
        self._cancel_timer(timer)
        if monitor_needs_stop:
            self._stop_monitor()

    @staticmethod
    def _cancel_timer(timer: TimerHandle | None) -> None:
        if timer is None:
            return
        try:
            timer.cancel()
        except Exception:
            logger.exception("OLED 护屏定时器取消异常")

    def _stop_monitor(self) -> bool:
        try:
            stopped = self._input_monitor.stop()
        except Exception:
            logger.exception("OLED 护屏 Raw Input 监听停止异常")
            with self._lock:
                self._monitor_stop_pending = True
            return False
        if not stopped:
            logger.debug("OLED 护屏 Raw Input 监听线程仍在运行，保留停止重试状态")
            with self._lock:
                self._monitor_stop_pending = True
            return False
        with self._lock:
            self._monitor_stop_pending = False
        return True
