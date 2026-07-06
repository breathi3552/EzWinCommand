"""防火墙自动配置。

在 Server 启动时检测并添加 Windows 防火墙入站规则，
确保局域网设备可以访问 EzWinCommand 服务。
"""
import logging
import subprocess

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


def rule_exists(port: int) -> bool:
    """检查指定端口对应的防火墙规则是否已存在。"""
    rule_name = _rule_name(port)
    ok, output = _run_netsh(["show", "rule", f"name={rule_name}"])
    return ok and rule_name in output and f"{port}" in output


def add_rule(port: int) -> bool:
    """添加允许指定端口的入站 TCP 规则。成功返回 True。"""
    rule_name = _rule_name(port)
    if rule_exists(port):
        logger.info("防火墙规则已存在: %s", rule_name)
        return True

    ok, output = _run_netsh([
        "add", "rule",
        f"name={rule_name}",
        "dir=in",
        "action=allow",
        "protocol=tcp",
        f"localport={port}",
    ])

    if ok:
        logger.info("已自动添加防火墙规则: %s (端口 %d)", rule_name, port)
        return True
    else:
        logger.warning("自动添加防火墙规则失败: %s", output)
        logger.warning(
            "请以管理员身份运行本程序，或手动执行：\n"
            "  netsh advfirewall firewall add rule name=\"%s\" "
            "dir=in action=allow protocol=tcp localport=%d",
            rule_name, port,
        )
        return False
