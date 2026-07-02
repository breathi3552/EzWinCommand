"""防火墙自动配置。

在 Server 启动时检测并添加 Windows 防火墙入站规则，
确保局域网设备可以访问 EzWinCommand 服务。
"""
import logging
import subprocess

logger = logging.getLogger(__name__)

RULE_NAME = "EzWinCommand 8080"


def _run_netsh(args: list[str]) -> tuple[bool, str]:
    """执行 netsh 命令，返回 (成功, 输出)。"""
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", *args],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "命令超时"
    except FileNotFoundError:
        return False, "netsh 不可用"


def rule_exists() -> bool:
    """检查防火墙规则是否已存在。"""
    ok, output = _run_netsh(["show", "rule", f"name={RULE_NAME}"])
    return ok and RULE_NAME in output


def add_rule(port: int) -> bool:
    """添加允许指定端口的入站 TCP 规则。成功返回 True。"""
    if rule_exists():
        logger.info("防火墙规则已存在: %s", RULE_NAME)
        return True

    ok, output = _run_netsh([
        "add", "rule",
        f"name={RULE_NAME}",
        "dir=in",
        "action=allow",
        "protocol=tcp",
        f"localport={port}",
    ])

    if ok:
        logger.info("已自动添加防火墙规则: %s (端口 %d)", RULE_NAME, port)
        return True
    else:
        logger.warning("自动添加防火墙规则失败: %s", output)
        logger.warning(
            "请以管理员身份运行本程序，或手动执行：\n"
            "  netsh advfirewall firewall add rule name=\"%s\" "
            "dir=in action=allow protocol=tcp localport=%d",
            RULE_NAME, port,
        )
        return False
