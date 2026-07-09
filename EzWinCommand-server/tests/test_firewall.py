from __future__ import annotations

from types import SimpleNamespace

from agent import firewall


def test_run_netsh_decodes_active_code_page_output(monkeypatch) -> None:
    message = "请求的操作需要提升(作为管理员运行)。"
    encoded = message.encode("gbk")

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout=b"", stderr=encoded)

    monkeypatch.setattr(firewall.subprocess, "run", fake_run)

    ok, output = firewall._run_netsh(["show", "rule", "name=EzWinCommand 8080"])

    assert ok is False
    assert output == message
    assert firewall._looks_like_elevation_error(output) is True
