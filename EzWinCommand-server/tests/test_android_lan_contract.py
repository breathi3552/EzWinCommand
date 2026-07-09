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
        self._pairing_code = "a1b2"
        self._expired = False
        self._devices = []
        self._device_key = "device-abc123"

    def get_pairing_code(self):
        return self._pairing_code if not self._expired else None

    def get_pairing_code_expires_in(self) -> int:
        return 123

    def has_devices(self) -> bool:
        return bool(self._devices)

    def try_pair(self, token: str, name: str):
        return self._device_key if token == self._pairing_code else None

    def list_devices(self) -> list[dict]:
        return [{"key": self._device_key, "name": "Android Phone"}]

    def remove_device(self, key: str) -> bool:
        return key == self._device_key

    def rename_device(self, key: str, name: str) -> bool:
        return key == self._device_key

    def is_authorized(self, key: str) -> bool:
        return key == self._device_key

    def touch(self, key: str) -> None:
        return None



def _make_client() -> TestClient:
    app = create_app()
    app.state.dispatcher = _StubDispatcher()
    app.state.auth_manager = _StubAuthManager()
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



def test_android_lan_pairing_code_hides_code_for_remote_client() -> None:
    client = _make_client()

    response = _remote_request(client, "GET", "/api/pairing-code")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"has_code": True, "has_devices": False, "expires_in": 123}
    assert "code" not in payload



def test_android_lan_authorize_returns_device_key() -> None:
    client = _make_client()

    response = client.post("/api/authorize", json={"token": "a1b2", "name": "Android Phone"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["success"] is True
    assert payload["device_key"] == "device-abc123"



def test_android_lan_protected_api_requires_bearer() -> None:
    client = _make_client()

    response = _remote_request(client, "GET", "/api/actions")

    assert response.status_code == 401
    assert response.json()["detail"]



def test_android_lan_actions_accepts_valid_bearer() -> None:
    client = _make_client()

    response = client.get("/api/actions", headers={"Authorization": "Bearer device-abc123"})

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["actions"], list)
    assert payload["actions"][0]["name"] == "media.play_pause"



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