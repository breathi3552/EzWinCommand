"""EzWinCommand wire protocol facts."""
from __future__ import annotations

PROTOCOL_VERSION = 2
PROTOCOL_HEADER = "X-EzWinCommand-Protocol"


def protocol_mismatch_detail() -> str:
    """返回不泄露运行状态的协议拒绝提示。"""
    return "协议版本不兼容，请升级客户端。"
