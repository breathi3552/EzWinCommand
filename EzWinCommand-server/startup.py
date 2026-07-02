"""开机自启动管理：注册表 Run 键读写。"""
import logging
import sys
import winreg
from pathlib import Path

logger = logging.getLogger(__name__)

# Run 键路径
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "EzWinCommandAgent"


def _get_command() -> str:
    """构建开机启动命令行：pythonw.exe <start_daemon.pyw 绝对路径>"""
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    app_path = (Path(__file__).parent / "start_daemon.pyw").resolve()
    return f'"{pythonw}" "{app_path}"'


def is_installed() -> bool:
    """检查是否已注册开机自启。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY)
        try:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


def install() -> None:
    """注册开机自启动。"""
    cmd = _get_command()
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, RUN_KEY,
        0, winreg.KEY_WRITE,
    )
    winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
    winreg.CloseKey(key)
    logger.info("已注册开机自启动: %s", cmd)


def uninstall() -> None:
    """注销开机自启动。"""
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, RUN_KEY,
        0, winreg.KEY_SET_VALUE,
    )
    try:
        winreg.DeleteValue(key, VALUE_NAME)
        logger.info("已注销开机自启动")
    except FileNotFoundError:
        logger.info("开机自启动未注册，无需注销")
    finally:
        winreg.CloseKey(key)
