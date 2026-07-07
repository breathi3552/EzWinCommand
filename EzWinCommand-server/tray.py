"""Windows 系统托盘模块。

在任务栏通知区域显示 EzWinCommand Server 图标，提供右键菜单（状态、退出）。
优先加载自定义图标，失败时回退系统默认图标。
"""
import logging
import threading
from pathlib import Path
from typing import Callable

import win32api
import win32con
import win32gui

logger = logging.getLogger(__name__)

# 托盘回调消息 ID
WM_TRAY = win32con.WM_USER + 1
# 菜单项 ID
ID_EXIT = 1001
ID_STATUS = 1002
ID_OPEN_WEB = 1003


def _load_icon(icon_path: str | Path | None = None) -> int:
    """加载自定义 .ico，失败时回退到系统默认图标。

    优先使用 LR_LOADFROMFILE 从文件加载 32×32 自定义图标；
    若文件不存在或加载失败，回退到系统 IDI_APPLICATION。
    """
    if icon_path:
        try:
            icon_str = str(icon_path)
            return win32gui.LoadImage(
                0,
                icon_str,
                win32con.IMAGE_ICON,
                0, 0,
                win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE,
            )
        except Exception:
            logger.warning("自定义图标 %s 加载失败，回退到系统默认图标", icon_path)
    return win32gui.LoadImage(
        0,
        win32con.IDI_APPLICATION,
        win32con.IMAGE_ICON,
        16, 16,
        win32con.LR_SHARED,
    )

class SystemTray:
    """Windows 系统托盘。

    在独立守护线程中运行 Windows 消息循环，不阻塞调用方线程。

    Usage::

        tray = SystemTray(on_exit=lambda: sys.exit(0))
        tray.start()
        # ... 运行主逻辑 ...
        tray.stop()
    """

    _instances: dict[int, "SystemTray"] = {}

    def __init__(
        self,
        on_exit: Callable[[], None],
        tooltip: str = "EzWinCommand Server",
        web_url: str = "http://127.0.0.1:8080",
        icon_path: str | Path | None = None,
    ) -> None:
        self._on_exit = on_exit
        self._tooltip = tooltip
        self._web_url = web_url
        self._icon_path = icon_path
        self._hwnd: int | None = None
        self._nid: tuple | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()

    # ── 公开 API ──────────────────────────────────────

    def start(self) -> None:
        """在守护线程中启动托盘消息循环。"""
        self._thread = threading.Thread(target=self._run, daemon=True, name="tray")
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("托盘线程启动超时")
        logger.info("系统托盘已启动")

    def stop(self) -> None:
        """销毁托盘图标并退出消息循环。"""
        if self._hwnd is None:
            return
        logger.info("正在关闭系统托盘...")
        self._delete_tray()
        win32gui.PostMessage(self._hwnd, win32con.WM_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._hwnd = None
        logger.info("系统托盘已关闭")

    def update_tooltip(self, text: str) -> None:
        """更新托盘悬停提示文字。"""
        self._tooltip = text
        if self._hwnd and self._nid:
            nid = list(self._nid)
            nid[4] = text  # szTip
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, tuple(nid))

    # ── 内部实现 ──────────────────────────────────────

    def _run(self) -> None:
        """线程入口：创建窗口 → 添加图标 → 消息循环。"""
        self._register_class()
        self._create_window()
        self._add_tray_icon()
        self._ready.set()
        win32gui.PumpMessages()
        # PumpMessages 返回 = 收到 WM_QUIT，托盘已销毁
        logger.info("托盘消息循环退出")
        self._on_exit()

    def _register_class(self) -> None:
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wnd_proc  # type: ignore[assignment]
        wc.lpszClassName = "EzWinCommandTray"
        wc.hInstance = win32api.GetModuleHandle(None)
        win32gui.RegisterClass(wc)

    def _create_window(self) -> None:
        self._hwnd = win32gui.CreateWindow(
            "EzWinCommandTray",
            "EzWinCommand",
            win32con.WS_POPUP,
            0, 0, 1, 1,
            0, 0,
            win32api.GetModuleHandle(None),
            None,
        )
        SystemTray._instances[self._hwnd] = self

    def _add_tray_icon(self) -> None:
        hicon = _load_icon(self._icon_path)
        self._nid = (
            self._hwnd,
            0,  # uid
            win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
            WM_TRAY,
            hicon,
            self._tooltip,
        )
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, self._nid)

    def _delete_tray(self) -> None:
        if self._nid:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, self._nid)
            self._nid = None
        if self._hwnd:
            SystemTray._instances.pop(self._hwnd, None)
            try:
                win32gui.DestroyWindow(self._hwnd)
            except Exception:
                pass

    def _show_menu(self) -> None:
        menu = win32gui.CreatePopupMenu()
        try:
            # 标题行（灰色，不可点击）
            win32gui.AppendMenu(
                menu, win32con.MF_STRING | win32con.MF_GRAYED,
                ID_STATUS, "EzWinCommand Server",
            )
            win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
            win32gui.AppendMenu(menu, win32con.MF_STRING, ID_OPEN_WEB, "打开 Web 管理(&O)")
            win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
            win32gui.AppendMenu(menu, win32con.MF_STRING, ID_EXIT, "退出(&X)")

            pos = win32gui.GetCursorPos()
            # TrackPopupMenu 要求当前线程窗口在前台
            win32gui.SetForegroundWindow(self._hwnd)
            win32gui.TrackPopupMenu(
                menu,
                win32con.TPM_LEFTALIGN | win32con.TPM_BOTTOMALIGN,
                pos[0], pos[1],
                0, self._hwnd, None,
            )
            # 结束菜单追踪
            win32gui.PostMessage(self._hwnd, win32con.WM_NULL, 0, 0)
        finally:
            win32gui.DestroyMenu(menu)

    # ── 消息处理 ──────────────────────────────────────

    @staticmethod
    def _wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        """窗口过程（C 回调，必须是 static）。"""
        instance = SystemTray._instances.get(hwnd)
        if instance is not None:
            return instance._handle_msg(hwnd, msg, wparam, lparam)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _handle_msg(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_TRAY:
            # 双击托盘图标 → 打开 Web 管理面板
            if lparam == win32con.WM_LBUTTONDBLCLK:
                import os
                os.startfile(self._web_url)
                return 0
            if lparam == win32con.WM_RBUTTONUP:
                self._show_menu()
            return 0

        if msg == win32con.WM_COMMAND:
            if wparam == ID_OPEN_WEB:
                import os
                os.startfile(self._web_url)
                return 0
            if wparam == ID_EXIT:
                self._delete_tray()
                win32gui.PostQuitMessage(0)
                return 0

        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
