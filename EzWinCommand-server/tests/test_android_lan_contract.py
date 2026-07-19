from __future__ import annotations

from importlib import import_module

from fastapi.testclient import TestClient


app_module = import_module("app")
create_app = getattr(app_module, "create_app", lambda: app_module.app)


class _StubStore:
    def __init__(self) -> None:
        self._device_key = "device-abc123"
        self._devices = [
            {
                "key": self._device_key,
                "name": "Android Phone",
                "created_at": "2026-07-08T00:00:00Z",
                "last_seen": "2026-07-08T00:00:00Z",
            }
        ]
        self.touched: list[str] = []

    def add_device(self, name: str) -> str:
        return self._device_key

    def is_authorized(self, key: str) -> bool:
        return key == self._device_key

    def touch(self, key: str) -> None:
        self.touched.append(key)

    def list_devices(self) -> list[dict]:
        return list(self._devices)

    def has_any_device(self) -> bool:
        return True

    def remove_device(self, key: str) -> bool:
        return key == self._device_key

    def rename_device(self, key: str, name: str) -> bool:
        return key == self._device_key


class _StubDispatcher:
    def execute(self, action: str, params: dict) -> object:
        return type("Result", (), {"success": True, "message": f"executed:{action}", "data": {"action": action, "params": params}})()

    def list_actions(self) -> list[dict]:
        return [
            {"name": "media.play_pause", "label": "播放/暂停", "description": "切换媒体播放", "version": "1.0", "sub_actions": []},
        ]

    def list_plugins(self, include_disabled: bool = True) -> list[dict]:
        return []

    def set_plugin_enabled(self, plugin_name: str, enabled: bool) -> bool:
        return True


class _StubAuthManager:
    def __init__(self) -> None:
        self._pairing = {"pairing_id": "pair-1", "server_id": "server-1", "code": "1234"}
        self.authorized_keys: set[str] = set()
        self._device_key = "device-abc123"
    def create_pairing(self, device_name="Android"):
        return {"pairing_id": "pair-1", "server_id": "server-1", "expires_in": 300}
    def list_pairings(self, include_code=False):
        row = {"pairing_id":"pair-1", "server_id":"server-1", "device_name":"Android", "status":"pending", "expires_in":300, "lock_expires_in":0}
        if include_code: row["code"] = "1234"
        return [row]
    def complete_pairing(self, server_id, pairing_id, code, device_name):
        if (server_id, pairing_id, code) != ("server-1", "pair-1", "1234"):
            return None
        self.authorized_keys.add(self._device_key)
        return self._device_key
    def cancel_pairing(self, pairing_id): return pairing_id == "pair-1"
    def list_devices(self): return [{"key": self._device_key, "name": "Android Phone"}]
    def remove_device(self, key): return key == self._device_key
    def rename_device(self, key, name): return key == self._device_key
    def is_authorized(self, key): return key in self.authorized_keys
    def touch(self, key): return None



def _make_client() -> TestClient:
    app = create_app()
    app.state.dispatcher = _StubDispatcher()
    auth_middleware = next(middleware for middleware in app.user_middleware if middleware.cls.__name__ == "_AuthMiddleware")
    auth_manager = auth_middleware.cls.__call__.__closure__[0].cell_contents
    auth_manager.__class__ = _StubAuthManager
    _StubAuthManager.__init__(auth_manager)
    app.state.auth_manager = auth_manager
    return TestClient(app)



def _remote_request(client: TestClient, method: str, url: str, **kwargs):
    transport = client._transport
    old_client = getattr(transport, "client", None)
    transport.client = ("192.168.1.10", 54321)
    try:
        return client.request(method, url, **kwargs)
    finally:
        transport.client = old_client



def test_android_lan_ping_public() -> None:
    client = _make_client()

    response = client.get("/ping")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}




def test_remote_pairing_full_flow_and_strict_anonymous_boundary() -> None:
    client = _make_client()
    identity = _remote_request(client, "GET", "/api/identity")
    assert identity.status_code == 200
    assert {"server_id", "protocol_version", "display_name", "port"} <= identity.json().keys()

    created = _remote_request(client, "POST", "/api/pairings", json={"device_name": "Android Phone"})
    assert created.status_code == 201
    assert created.json()["pairing_id"] == "pair-1"

    wrong_code = _remote_request(client, "POST", "/api/pairings/pair-1/complete", json={
        "server_id": "server-1", "pairing_id": "pair-1", "code": "0000", "device_name": "Android Phone",
    })
    assert wrong_code.status_code == 403

    completed = _remote_request(client, "POST", "/api/pairings/pair-1/complete", json={
        "server_id": "server-1", "pairing_id": "pair-1", "code": "1234", "device_name": "Android Phone",
    })
    assert completed.status_code == 201
    device_key = completed.json()["device_key"]
    assert device_key == "device-abc123"

    actions = _remote_request(client, "GET", "/api/actions", headers={"Authorization": f"Bearer {device_key}"})
    assert actions.status_code == 200

    cancelled = _remote_request(client, "DELETE", "/api/pairings/pair-1")
    assert cancelled.status_code == 204

    for method, path in (
        ("GET", "/api/pairings/pair-1"),
        ("GET", "/api/pairings/pair-1/complete"),
        ("POST", "/api/pairings/pair-1/complete/extra"),
        ("DELETE", "/api/pairings/pair-1/extra"),
        ("PATCH", "/api/pairings/pair-1"),
    ):
        response = _remote_request(client, method, path)
        assert response.status_code == 401, (method, path, response.text)


def test_device_list_allows_loopback_and_requires_remote_bearer() -> None:
    client = _make_client()

    local = client.get("/api/devices")
    assert local.status_code == 200
    assert local.json() == {"devices": [{"key": "device-abc123", "name": "Android Phone"}]}

    unauthorized = _remote_request(client, "GET", "/api/devices")
    assert unauthorized.status_code == 401



def test_remote_device_revoke_removes_authorization() -> None:
    client = _make_client()
    key = "device-abc123"
    auth_manager = client.app.state.auth_manager
    auth_manager.authorized_keys.add(key)
    revoked: list[str] = []
    client.app.state.media_event_hub = type("Hub", (), {"revoke": lambda _, digest: revoked.append(digest)})()

    response = _remote_request(client, "DELETE", f"/api/devices/{key}", headers={"Authorization": f"Bearer {key}"})

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert revoked == [__import__("hashlib").sha256(key.encode()).hexdigest()]

def test_local_pairings_code_and_remote_not_found() -> None:
    client = _make_client()
    local = client.get("/api/local/pairings")
    assert local.status_code == 200 and local.json()["pairings"][0]["code"] == "1234"
    remote = _remote_request(client, "GET", "/api/local/pairings")
    assert remote.status_code == 404



def test_web_shell_revalidates_and_references_versioned_assets() -> None:
    client = _make_client()

    home = client.get("/")
    index = client.get("/index.html")

    assert home.headers["cache-control"] == "no-cache, must-revalidate"
    assert index.headers["cache-control"] == "no-cache, must-revalidate"
    assert '/static/app.js?v=20260717' in home.text
    assert '/static/style.css?v=20260717' in home.text

    script = client.get("/static/app.js")
    versioned_script = client.get("/static/app.js?v=20260717")
    assert script.status_code == 200
    assert versioned_script.status_code == 200
    assert versioned_script.content == script.content
    assert "no-store" not in script.headers.get("cache-control", "")


def test_pc_page_uses_local_events_without_idle_polling() -> None:
    client = _make_client()
    page = client.get("/").text
    script = client.get("/static/app.js").text

    assert 'id="pc-pairing-area"' in page
    assert 'fetchJson("/api/local/pairings"' in script
    assert 'new EventSource("/api/local/events")' in script
    assert 'addEventListener("open", pcRefreshSnapshots)' in script
    assert "pcStartPolling" not in script
    assert "PC_CODE_POLL_MS" not in script
    assert "setInterval(extLoadDevices, DEVICE_POLL_MS)" in script  # 仅外部控制页保留
    assert script.count("setInterval(extLoadDevices, DEVICE_POLL_MS)") == 1
    assert "has_code" not in script
    assert 'fetchJson("/api/devices")' in script
    assert 'fetchJson("/api/devices", {}, "pc-error")' not in script
    style = client.get("/static/style.css").text
    assert "pairing-empty" in script and "等待手机发起配对" in script
    assert "pairing-card" in script and "pairing-device-name" in script
    assert "pcPairingShortId(pairing.pairing_id)" in script
    assert "/^\\d{4}$/.test(code)" in script
    assert "pairing-code" in style and "font-size: 52px" in style
    assert 'id="ext-pairing"' not in page
    assert "#pc-pairing-code" not in style and "#pc-countdown" not in style


def test_local_events_are_loopback_only_and_payload_is_non_sensitive() -> None:
    import asyncio
    from agent.api import LocalEventHub

    async def scenario() -> str:
        loop = asyncio.get_running_loop()
        hub = LocalEventHub(loop)
        stream = hub.stream()
        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        hub.publish(frozenset({"pairings", "devices"}))
        frame = await asyncio.wait_for(pending, timeout=1)
        await stream.aclose()
        return frame

    frame = asyncio.run(scenario())
    assert frame == 'event: changed\ndata: {"domains":["devices","pairings"]}\n\n'
    assert "code" not in frame and "device_key" not in frame

    client = _make_client()
    remote = _remote_request(client, "GET", "/api/local/events")
    assert remote.status_code == 404


def test_auth_manager_publishes_pairing_and_device_invalidations() -> None:
    from agent.auth import AuthManager

    store = _StubStore()
    manager = AuthManager(store, server_id="server-1")
    changes: list[frozenset[str]] = []
    manager.set_change_listener(changes.append)

    created = manager.create_pairing("Android Phone")
    code = manager.list_pairings(include_code=True)[0]["code"]
    assert manager.complete_pairing("server-1", created["pairing_id"], code, "Android Phone") == "device-abc123"
    assert changes == [frozenset({"pairings"}), frozenset({"pairings", "devices"})]

    assert manager.rename_device("device-abc123", "New Name")
    assert manager.remove_device("device-abc123")
    assert changes[-2:] == [frozenset({"devices"}), frozenset({"devices"})]


def test_android_lan_command_accepts_valid_bearer() -> None:
    client = _make_client()

    response = client.post(
        "/api/command",
        headers={"Authorization": "Bearer device-abc123"},
        json={"action": "media.play_pause", "params": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "success": True,
        "message": "executed:media.play_pause",
        "data": {"action": "media.play_pause", "params": {}},
    }