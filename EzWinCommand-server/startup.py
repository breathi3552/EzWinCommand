"""开机自启动管理：注册表 Run 键读写。"""
import logging
import sys
import winreg
from pathlib import Path

logger = logging.getLogger(__name__)

# Run 键路径
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "EzWinCommandServer"
LEGACY_VALUE_NAMES = ("EzWinCommandAgent",)


def _get_command() -> str:
    """构建开机启动命令行：pythonw.exe <start_daemon.pyw 绝对路径>"""
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    app_path = (Path(__file__).parent / "start_daemon.pyw").resolve()
    return f'"{pythonw}" "{app_path}"'


def is_installed() -> bool:
    """检查是否已注册开机自启（兼容旧 Agent 注册名）。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
        try:
            for value_name in (VALUE_NAME, *LEGACY_VALUE_NAMES):
                try:
                    winreg.QueryValueEx(key, value_name)
                    return True
                except FileNotFoundError:
                    continue
            return False
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


def install() -> None:
    """注册开机自启动，并清理旧 Agent 注册名避免双启动。"""
    cmd = _get_command()
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, RUN_KEY,
        0, winreg.KEY_WRITE,
    )
    for legacy_name in LEGACY_VALUE_NAMES:
        try:
            winreg.DeleteValue(key, legacy_name)
        except FileNotFoundError:
            pass
    winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
    winreg.CloseKey(key)
    logger.info("已注册开机自启动: %s", cmd)


def uninstall() -> None:
    """注销开机自启动（同时清理旧 Agent 注册名）。"""
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, RUN_KEY,
        0, winreg.KEY_SET_VALUE,
    )
    removed = False
    try:
        for value_name in (VALUE_NAME, *LEGACY_VALUE_NAMES):
            try:
                winreg.DeleteValue(key, value_name)
                removed = True
            except FileNotFoundError:
                continue
        if removed:
            logger.info("已注销开机自启动")
        else:
            logger.info("开机自启动未注册，无需注销")
    finally:
        winreg.CloseKey(key)
