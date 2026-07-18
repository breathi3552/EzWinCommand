from __future__ import annotations

import threading

from agent.auth import AuthManager
from agent.discovery import DiscoveryPublisher, SERVICE_TYPE
from agent.server_identity import ServerIdentity


class _Store:
    def add_device(self, name): return "key"
    def is_authorized(self, key): return True
    def touch(self, key): pass


def test_pairing_list_exposes_attempts_lock_recovers_and_terminal_retains(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("agent.auth.time.time", lambda: clock[0])
    manager = AuthManager(_Store(), "server")
    created = manager.create_pairing("Phone")
    pairing_id = created["pairing_id"]
    code = manager._pairings[pairing_id]["code"]

    for _ in range(5):
        assert manager.complete_pairing("server", pairing_id, "0000" if code != "0000" else "1111", "Phone") is None
    locked = manager.list_pairings(True)[0]
    assert locked["status"] == "locked"
    assert locked["remaining_attempts"] == 0
    assert locked["locked_until"] == 1030.0

    clock[0] = 1031.0
    recovered = manager.list_pairings(True)[0]
    assert recovered["status"] == "pending"
    assert recovered["remaining_attempts"] == 5
    assert recovered["locked_until"] is None

    assert manager.complete_pairing("server", pairing_id, code, "Phone") == "key"
    terminal = manager.list_pairings(True)[0]
    assert terminal["status"] == "consumed"
    assert "code" not in terminal
    clock[0] = 1092.0
    assert manager.list_pairings(True) == []


def test_pairing_list_orders_active_before_newest_terminal(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("agent.auth.time.time", lambda: clock[0])
    manager = AuthManager(_Store(), "server")
    old_active = manager.create_pairing("A")["pairing_id"]
    clock[0] += 1
    terminal = manager.create_pairing("B")["pairing_id"]
    manager.cancel_pairing(terminal)
    clock[0] += 1
    newest_active = manager.create_pairing("C")["pairing_id"]

    rows = manager.list_pairings()
    assert [row["pairing_id"] for row in rows] == [newest_active, old_active, terminal]


def test_mdns_publisher_registers_android_compatible_service(monkeypatch):
    identity = ServerIdentity(version=1, server_id="00000000-0000-4000-8000-000000000001", name="PC")
    captured = {}

    class FakeInfo:
        def __init__(self, service_type, name, *, addresses, port, properties, server):
            captured.update(
                service_type=service_type, name=name, addresses=addresses,
                port=port, properties=properties, server=server,
            )

    class FakeZeroconf:
        def register_service(self, info): captured["info"] = info

    monkeypatch.setattr("agent.discovery.ServiceInfo", FakeInfo)
    monkeypatch.setattr("agent.discovery.Zeroconf", FakeZeroconf)
    monkeypatch.setattr("agent.discovery._publishable_ipv4_addresses", lambda: [b"\xc0\xa8\x1f\x57"])
    publisher = DiscoveryPublisher(identity, 49123)

    assert publisher.start() is True
    assert captured["service_type"] == SERVICE_TYPE == "_ezwincommand._tcp.local."
    assert captured["name"].endswith("." + SERVICE_TYPE)
    assert captured["port"] == 49123
    assert set(captured["properties"]) == {b"ver", b"id", b"name"}
    assert captured["addresses"] == [b"\xc0\xa8\x1f\x57"]
    assert captured["server"] == "ezwincommand-00000000.local."


def test_mdns_publisher_rejects_missing_lan_address(monkeypatch):
    identity = ServerIdentity(version=1, server_id="00000000-0000-4000-8000-000000000001", name="PC")
    monkeypatch.setattr("agent.discovery._publishable_ipv4_addresses", lambda: [])
    publisher = DiscoveryPublisher(identity, 49123)

    assert publisher.start() is False
    assert publisher.registered is False


def test_mdns_close_returns_within_two_seconds_when_unregister_hangs(monkeypatch):
    identity = ServerIdentity(version=1, server_id="00000000-0000-4000-8000-000000000001", name="PC")
    publisher = DiscoveryPublisher(identity, 8080)
    entered = threading.Event()
    release = threading.Event()

    class HangingZeroconf:
        def unregister_service(self, service):
            entered.set(); release.wait(5)
        def close(self): pass

    publisher._zeroconf = HangingZeroconf()
    publisher._service = object()
    publisher._registered = True
    start = __import__("time").monotonic()
    publisher.close()
    elapsed = __import__("time").monotonic() - start
    release.set()

    assert entered.is_set()
    assert 1.8 <= elapsed < 2.5
    assert publisher.registered is False
