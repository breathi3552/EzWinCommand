"""防火墙自动配置。

在 Server 启动时检测并添加 Windows 防火墙入站规则，
确保局域网设备可以访问 EzWinCommand 服务。
"""
import logging
import subprocess
import ctypes


logger = logging.getLogger(__name__)

RULE_NAME_PREFIX = "EzWinCommand"


def _rule_name(port: int) -> str:
    """按端口生成防火墙规则名。"""
    return f"{RULE_NAME_PREFIX} {port}"


def _run_netsh(args: list[str]) -> tuple[bool, str]:
    """执行 netsh 命令，返回 (成功, 输出)。

    显式使用 mbcs 编码（Windows 当前 ANSI 代码页），
    配合 errors="replace" 防止 netsh 中文输出中的异常字节导致崩溃。
    """
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", *args],
            capture_output=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False, "命令超时"
    except FileNotFoundError:
        return False, "netsh 不可用"

    # 安全解码：优先 mbcs（GBK），失败则用 replace
    stdout = ""
    if result.stdout:
        try:
            stdout = result.stdout.decode("mbcs", errors="replace").strip()
        except LookupError:
            stdout = result.stdout.decode("utf-8", errors="replace").strip()

    stderr = ""
    if result.stderr:
        try:
            stderr = result.stderr.decode("mbcs", errors="replace").strip()
        except LookupError:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()

    output = stdout or stderr
    return result.returncode == 0, output


def _request_elevated_netsh(args: list[str]) -> bool:
    """通过 UAC 提权执行 netsh，成功发起返回 True。"""
    parameters = subprocess.list2cmdline(["advfirewall", "firewall", *args])
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        "netsh",
        parameters,
        None,
        0,
    )
    return result > 32


def _looks_like_elevation_error(output: str) -> bool:
    """判断 netsh 输出是否表示缺少管理员权限。"""
    lowered = output.lower()
    return (
        "提升" in output
        or "管理员" in output
        or "access is denied" in lowered
        or "requires elevation" in lowered
    )


def rule_exists(port: int) -> bool:
    """检查指定端口对应的防火墙规则是否已存在。"""
    rule_name = _rule_name(port)
    ok, _ = _run_netsh(["show", "rule", f"name={rule_name}"])
    return ok


def add_rule(port: int) -> bool:
    """添加或更新允许指定端口的入站 TCP 规则。成功返回 True。

    普通权限下 netsh 会失败；此时发起 UAC 提权执行同一条规则同步命令。
    """
    rule_name = _rule_name(port)
    if rule_exists(port):
        operation = "同步"
        args = [
            "set", "rule",
            f"name={rule_name}",
            "new",
            "enable=yes",
            "dir=in",
            "action=allow",
            "protocol=tcp",
            f"localport={port}",
            "profile=any",
        ]
    else:
        operation = "添加"
        args = [
            "add", "rule",
            f"name={rule_name}",
            "dir=in",
            "action=allow",
            "protocol=tcp",
            f"localport={port}",
            "profile=any",
            "enable=yes",
        ]

    ok, output = _run_netsh(args)
    if ok:
        logger.info("已%s防火墙规则: %s (端口 %d)", operation, rule_name, port)
        return True

    logger.warning("%s防火墙规则失败: %s", operation, output)
    if _looks_like_elevation_error(output):
        if _request_elevated_netsh(args):
            logger.warning(
                "已请求管理员权限%s防火墙规则: %s (端口 %d)；请在授权后重新检查手机端访问",
                operation, rule_name, port,
            )
        else:
            logger.warning("用户取消或系统拒绝管理员权限请求")

    logger.warning(
        "请以管理员身份运行本程序，或手动执行：\n"
        "  netsh advfirewall firewall add rule name=\"%s\" "
        "dir=in action=allow protocol=tcp localport=%d profile=any enable=yes",
        rule_name, port,
    )
    return False
