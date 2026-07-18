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


def test_mdns_rule_is_private_local_subnet_udp_only(monkeypatch) -> None:
    calls = []

    def fake_run(args):
        calls.append(args)
        return (False, "no rule") if args[0] == "show" else (True, "ok")

    monkeypatch.setattr(firewall, "_run_netsh", fake_run)

    assert firewall.add_mdns_rule() is True
    added = calls[-1]
    assert "protocol=udp" in added
    assert "localport=5353" in added
    assert "profile=private" in added
    assert "remoteip=localsubnet" in added
    assert "profile=any" not in added


def test_business_rule_is_private_local_subnet_tcp_only(monkeypatch) -> None:
    calls = []

    def fake_run(args):
        calls.append(args)
        if args[0] == "show":
            return False, "no rule"
        return True, "ok"

    monkeypatch.setattr(firewall, "_run_netsh", fake_run)

    assert firewall.add_rule(64756) is True
    added = calls[-1]
    assert "protocol=tcp" in added
    assert "localport=64756" in added
    assert "profile=private" in added
    assert "remoteip=localsubnet" in added
    assert "profile=any" not in added
