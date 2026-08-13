from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from importlib import import_module
import pytest

from fastapi.testclient import TestClient
from agent.device_store import DeviceStore


app_module = import_module("app")
create_app = getattr(app_module, "create_app", lambda: app_module.app)


class _StubStore:
    def __init__(self) -> None:
        self._device_key = "fixture-device-credential"
        self._other_device_key = "fixture-other-credential"
        self._devices = [
            {
                "device_id": "device-android",
                "name": "Android Phone",
                "created_at": "2026-07-08T00:00:00Z",
                "last_seen": "2026-07-08T00:00:00Z",
            },
            {
                "device_id": "device-tablet",
                "name": "Tablet",
                "created_at": "2026-07-09T00:00:00Z",
                "last_seen": "2026-07-09T00:00:00Z",
            },
        ]
        self.touched: list[str] = []

    def add_device(self, name: str) -> str:
        return self._device_key

    def is_authorized(self, key: str) -> bool:
        return key in {self._device_key, self._other_device_key}

    def touch(self, key: str) -> None:
        self.touched.append(key)

    def device_id_for_key(self, key: str) -> str | None:
        return {
            self._device_key: "device-android",
            self._other_device_key: "device-tablet",
        }.get(key)

    def key_for_device_id(self, device_id: str) -> str | None:
        return {
            "device-android": self._device_key,
            "device-tablet": self._other_device_key,
        }.get(device_id)

    def list_devices(self, current_device_id: str | None = None) -> list[dict]:
        return [
            {**device, "is_current": device["device_id"] == current_device_id}
            for device in self._devices
        ]

    def has_any_device(self) -> bool:
        return bool(self._devices)

    def remove_device(self, device_id: str) -> bool:
        before = len(self._devices)
        self._devices = [device for device in self._devices if device["device_id"] != device_id]
        return len(self._devices) != before

    def rename_device(self, device_id: str, name: str) -> bool:
        for device in self._devices:
            if device["device_id"] == device_id:
                device["name"] = name
                return True
        return False

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
        self._device_keys = {
            "device-android": "fixture-device-credential",
            "device-tablet": "fixture-other-credential",
        }
        self._devices = [
            {
                "device_id": "device-android",
                "name": "Android Phone",
                "created_at": "2026-07-08T00:00:00Z",
                "last_seen": "2026-07-08T00:00:00Z",
            },
            {
                "device_id": "device-tablet",
                "name": "Tablet",
                "created_at": "2026-07-09T00:00:00Z",
                "last_seen": "2026-07-09T00:00:00Z",
            },
        ]
        self._revoke_listener = None

    def create_pairing(self, device_name="Android"):
        return {"pairing_id": "pair-1", "server_id": "server-1", "expires_in": 300}

    def list_pairings(self, include_code=False):
        row = {"pairing_id": "pair-1", "server_id": "server-1", "device_name": "Android", "status": "pending", "expires_in": 300, "lock_expires_in": 0}
        if include_code:
            row["code"] = "1234"
        return [row]

    def complete_pairing(self, server_id, pairing_id, code, device_name):
        if (server_id, pairing_id, code) != ("server-1", "pair-1", "1234"):
            return None
        key = self._device_keys["device-android"]
        self.authorized_keys.add(key)
        return key

    def cancel_pairing(self, pairing_id):
        return pairing_id == "pair-1"

    def list_devices(self, current_device_id=None):
        return [
            {**device, "is_current": device["device_id"] == current_device_id}
            for device in self._devices
        ]


    def rename_device(self, device_id, name):
        for device in self._devices:
            if device["device_id"] == device_id:
                device["name"] = name
                return True
        return False

    def key_for_device_id(self, device_id):
        if any(device["device_id"] == device_id for device in self._devices):
            return self._device_keys[device_id]
        return None

    def device_id_for_key(self, key):
        for device_id, device_key in self._device_keys.items():
            if device_key == key and self.key_for_device_id(device_id) is not None:
                return device_id
        return None

    def is_authorized(self, key):
        return key in self.authorized_keys and self.device_id_for_key(key) is not None

    def touch(self, key):
        return None

    def set_revoke_listener(self, listener):
        self._revoke_listener = listener

    def remove_device(self, device_id):
        if self.key_for_device_id(device_id) is None:
            return False
        self._devices = [device for device in self._devices if device["device_id"] != device_id]
        self.authorized_keys.discard(self._device_keys[device_id])
        if self._revoke_listener is not None:
            self._revoke_listener(hashlib.sha256(self._device_keys[device_id].encode()).hexdigest())
        return True

def _make_client(store=None) -> TestClient:
    app = create_app(device_store=store) if store is not None else create_app()
    app.state.dispatcher = _StubDispatcher()
    if store is None:
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
    add_protocol = kwargs.pop("_add_protocol", True)
    headers = dict(kwargs.pop("headers", {}) or {})
    if add_protocol:
        headers.setdefault("X-EzWinCommand-Protocol", "2")
    kwargs["headers"] = headers
    try:
        return client.request(method, url, **kwargs)
    finally:
        transport.client = old_client


def test_android_lan_ping_public() -> None:
    client = _make_client()

    response = client.get("/ping")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_remote_protocol_marker_is_required_before_authentication() -> None:
    client = _make_client()

    missing = _remote_request(client, "GET", "/api/actions", _add_protocol=False)
    mismatched = _remote_request(
        client,
        "GET",
        "/api/actions",
        headers={"X-EzWinCommand-Protocol": "1"},
        _add_protocol=False,
    )

    assert missing.status_code == 426
    assert mismatched.status_code == 426
    assert _remote_request(client, "GET", "/api/identity", _add_protocol=False).status_code == 426
    assert _remote_request(
        client,
        "GET",
        "/api/identity",
        headers={"X-EzWinCommand-Protocol": "1"},
        _add_protocol=False,
    ).status_code == 426




def test_remote_pairing_full_flow_and_strict_anonymous_boundary() -> None:
    client = _make_client()
    identity = _remote_request(client, "GET", "/api/identity")
    assert identity.status_code == 200
    assert identity.json()["protocol_version"] == 2
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
    assert device_key == "fixture-device-credential"

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


def test_device_list_marks_authenticated_device_without_exposing_credentials() -> None:
    client = _make_client()

    local = client.get("/api/devices")
    assert local.status_code == 200
    local_devices = local.json()["devices"]
    assert all(set(device) == {"device_id", "name", "created_at", "last_seen", "is_current"} for device in local_devices)
    assert all(device["is_current"] is False for device in local_devices)
    assert all("key" not in device and "device_key" not in device for device in local_devices)

    key = "fixture-device-credential"
    client.app.state.auth_manager.authorized_keys.add(key)
    remote = _remote_request(client, "GET", "/api/devices", headers={"Authorization": f"Bearer {key}"})
    assert remote.status_code == 200
    remote_devices = remote.json()["devices"]
    assert next(device for device in remote_devices if device["device_id"] == "device-android")["is_current"] is True
    assert next(device for device in remote_devices if device["device_id"] == "device-tablet")["is_current"] is False

    unauthorized = _remote_request(client, "GET", "/api/devices")
    assert unauthorized.status_code == 401


def test_real_device_store_covers_local_and_remote_management(tmp_path) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    current_key = store.add_device("Android Phone")
    other_key = store.add_device("Tablet")
    current_id = store.device_id_for_key(current_key)
    other_id = store.device_id_for_key(other_key)
    assert current_id and other_id
    client = _make_client(store)

    local = client.get("/api/devices")
    assert local.status_code == 200
    local_devices = local.json()["devices"]
    assert all(set(device) == {"device_id", "name", "created_at", "last_seen", "is_current"} for device in local_devices)
    assert all(device["is_current"] is False for device in local_devices)
    assert "device_key" not in json.dumps(local.json())

    remote = _remote_request(
        client,
        "GET",
        "/api/devices",
        headers={"Authorization": f"Bearer {current_key}"},
    )
    assert remote.status_code == 200
    remote_devices = remote.json()["devices"]
    assert all(set(device) == {"device_id", "name", "created_at", "last_seen", "is_current"} for device in remote_devices)
    assert all("key" not in device and "device_key" not in device for device in remote_devices)
    assert next(device for device in remote_devices if device["device_id"] == current_id)["is_current"] is True
    assert next(device for device in remote_devices if device["device_id"] == other_id)["is_current"] is False
    assert "key" not in json.dumps(remote.json()) and "device_key" not in json.dumps(remote.json())

    renamed = _remote_request(
        client,
        "PATCH",
        f"/api/devices/{other_id}",
        headers={"Authorization": f"Bearer {current_key}"},
        json={"name": "Renamed Tablet"},
    )
    assert renamed.status_code == 200 and renamed.json() == {"success": True}
    revoked = _remote_request(
        client,
        "DELETE",
        f"/api/devices/{other_id}",
        headers={"Authorization": f"Bearer {current_key}"},
    )
    assert revoked.status_code == 200 and revoked.json() == {"success": True}
    assert store.is_authorized(current_key)
    assert not store.is_authorized(other_key)

    local_renamed = client.patch(f"/api/devices/{current_id}", json={"name": "Renamed Android"})
    local_revoked = client.delete(f"/api/devices/{current_id}")
    assert local_renamed.status_code == 200 and local_renamed.json() == {"success": True}
    assert local_revoked.status_code == 200 and local_revoked.json() == {"success": True}
    assert not store.is_authorized(current_key)

    missing_rename = client.patch("/api/devices/missing-id", json={"name": "Nope"})
    missing_revoke = client.delete("/api/devices/missing-id")
    assert missing_rename.status_code == 404
    assert missing_revoke.status_code == 404

def test_authenticated_device_can_manage_other_device_by_device_id() -> None:
    client = _make_client()
    key = "fixture-device-credential"
    client.app.state.auth_manager.authorized_keys.add(key)
    headers = {"Authorization": f"Bearer {key}"}

    renamed = _remote_request(client, "PATCH", "/api/devices/device-tablet", headers=headers, json={"name": "Renamed"})
    assert renamed.status_code == 200
    assert renamed.json() == {"success": True}

    client.app.state.media_event_hub = type("Hub", (), {"revoke": lambda *_: None})()
    revoked = _remote_request(client, "DELETE", "/api/devices/device-tablet", headers=headers)
    assert revoked.status_code == 200
    assert revoked.json() == {"success": True}


def test_missing_device_id_cannot_report_management_success() -> None:
    client = _make_client()
    key = "fixture-device-credential"
    client.app.state.auth_manager.authorized_keys.add(key)
    headers = {"Authorization": f"Bearer {key}"}

    renamed = _remote_request(client, "PATCH", "/api/devices/missing-device", headers=headers, json={"name": "Nope"})
    revoked = _remote_request(client, "DELETE", "/api/devices/missing-device", headers=headers)

    assert renamed.status_code == 404
    assert revoked.status_code == 404
    assert "success" not in renamed.json()
    assert "success" not in revoked.json()


def test_device_list_requires_remote_bearer() -> None:
    client = _make_client()

    unauthorized = _remote_request(client, "GET", "/api/devices")
    assert unauthorized.status_code == 401


def test_remote_device_revoke_removes_authorization() -> None:
    client = _make_client()
    key = "fixture-device-credential"
    auth_manager = client.app.state.auth_manager
    auth_manager.authorized_keys.add(key)
    revoked: list[str] = []
    hub = type("Hub", (), {"revoke": lambda _, digest: revoked.append(digest)})()
    client.app.state.media_event_hub = hub
    auth_manager.set_revoke_listener(hub.revoke)

    response = _remote_request(
        client,
        "DELETE",
        "/api/devices/device-android",
        headers={"Authorization": f"Bearer {key}"},
    )
    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert revoked == [hashlib.sha256(key.encode()).hexdigest()]
    assert not auth_manager.is_authorized(key)


def test_real_http_revoke_wires_to_media_event_hub(tmp_path) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    key = store.add_device("Android Phone")
    device_id = store.device_id_for_key(key)
    assert device_id is not None

    with TestClient(create_app(device_store=store)) as client:
        digest = hashlib.sha256(key.encode()).hexdigest()
        response = _remote_request(
            client,
            "DELETE",
            f"/api/devices/{device_id}",
            headers={"Authorization": f"Bearer {key}"},
        )
        assert response.status_code == 200
        assert response.json() == {"success": True}
        assert not store.is_authorized(key)
        assert digest in client.app.state.media_event_hub.revoked_digests



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
    assert '/static/app.js?v=20260813' in home.text
    assert '/static/style.css?v=20260813' in home.text

    script = client.get("/static/app.js")
    versioned_script = client.get("/static/app.js?v=20260813")
    assert script.status_code == 200
    assert versioned_script.status_code == 200
    assert versioned_script.content == script.content
    assert "no-store" not in script.headers.get("cache-control", "")


def test_web_shell_javascript_parses_with_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("当前环境未安装 Node.js")
    result = subprocess.run(
        [node, "--check", str(app_module.BASE_DIR / "web" / "static" / "app.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

def test_web_device_management_behaviour_with_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("当前环境未安装 Node.js")
    script = r"""
const fs = require("fs");
const vm = require("vm");

class Element {
    constructor(tag) {
        this.tagName = tag;
        this.children = [];
        this.parentNode = null;
        this.listeners = {};
        this.attributes = {};
        this.style = {};
        this.textContent = "";
        this.value = "";
        this.className = "";
    }
    set innerHTML(_) {
        this.children = [];
    }
    appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        return child;
    }
    replaceWith(replacement) {
        if (!this.parentNode) return;
        const index = this.parentNode.children.indexOf(this);
        if (index >= 0) {
            replacement.parentNode = this.parentNode;
            this.parentNode.children[index] = replacement;
        }
    }
    remove() {
        if (!this.parentNode) return;
        const index = this.parentNode.children.indexOf(this);
        if (index >= 0) this.parentNode.children.splice(index, 1);
        this.parentNode = null;
    }
    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }
    getAttribute(name) {
        return this.attributes[name] ?? null;
    }
    addEventListener(name, handler) {
        this.listeners[name] = handler;
    }
    async click() {
        return this.listeners.click ? this.listeners.click({ target: this }) : undefined;
    }
    focus() {}
    select() {}
}

const roots = new Map();
for (const id of [
    "pc-device-tbody",
    "pc-device-empty",
    "pc-error",
    "ext-device-tbody",
    "ext-device-empty",
    "ext-error",
    "ext-standby",
    "ext-dashboard",
    "ext-actions",
]) {
    roots.set(id, new Element("div"));
}
const document = {
    readyState: "loading",
    addEventListener() {},
    createElement: tag => new Element(tag),
    getElementById: id => roots.get(id) ?? null,
    querySelector: () => null,
    body: { contains: () => true },
};
const calls = [];
const responses = [];
let storedKeyValue = "external-fixture-key";
const localStorage = {
    getItem: key => key === "ez_device_key" ? storedKeyValue : null,
    removeItem: key => { if (key === "ez_device_key") storedKeyValue = null; },
};
const context = {
    console,
    document,
    location: { hostname: "192.168.31.87" },
    window: { prompt: () => "Renamed External" },
    localStorage,
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    fetch: async (url, options = {}) => {
        calls.push({
            url,
            method: options.method || "GET",
            body: options.body || null,
            headers: options.headers || {},
        });
        return {
            ok: true,
            status: 200,
            json: async () => responses.shift() ?? {},
        };
    },
    confirm: () => true,
    setInterval: () => 1,
    clearInterval: () => {},
    setTimeout,
    clearTimeout,
    performance: { now: () => 0 },
    URLSearchParams,
    Date,
    JSON,
    Error,
    Map,
    Set,
    Promise,
    AbortController,
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context, {
    filename: process.argv[1],
});

const device = {
    device_id: "android-device",
    name: "Android Phone",
    created_at: "2026-08-13T00:00:00Z",
    last_seen: "2026-08-13T00:00:00Z",
    is_current: true,
};

(async () => {
    responses.push({ devices: [device] });
    await context.pcLoadDevices();
    const tbody = roots.get("pc-device-tbody");
    if (tbody.children.length !== 1) throw new Error("设备列表未渲染");
    if (tbody.children[0].children[0].textContent !== "android-device") {
        throw new Error("设备列表未使用 device_id");
    }
    if (tbody.children[0].children[1].children[0].textContent !== "Android Phone") {
        throw new Error("设备名称未渲染");
    }

    const input = new Element("input");
    input.value = "Renamed Phone";
    input.setAttribute("data-device-id", "android-device");
    input.setAttribute("data-original-name", "Android Phone");
    responses.push(
        { success: true },
        { devices: [{ ...device, name: "Renamed Phone" }] },
    );
    await context.pcCommitRename(input);
    const renameCall = calls.find(call => call.method === "PATCH");
    if (!renameCall || renameCall.url !== "/api/devices/android-device") {
        throw new Error("重命名未使用 device_id URL");
    }
    if (JSON.parse(renameCall.body).name !== "Renamed Phone") {
        throw new Error("重命名请求体错误");
    }
    await new Promise(resolve => setTimeout(resolve, 0));
    if (tbody.children[0].children[1].children[0].textContent !== "Renamed Phone") {
        throw new Error("重命名后列表未刷新");
    }

    calls.length = 0;
    responses.push({ success: true }, { devices: [] });
    await context.pcRevokeDevice("android-device", tbody.children[0]);
    const revokeCall = calls.find(call => call.method === "DELETE");
    if (!revokeCall || revokeCall.url !== "/api/devices/android-device") {
        throw new Error("撤销未使用 device_id URL");
    }
    await new Promise(resolve => setTimeout(resolve, 0));
    if (tbody.children.length !== 0) throw new Error("撤销后列表未刷新");
    const otherDevice = {
        device_id: "other-device",
        name: "Other Device",
        created_at: "2026-08-13T00:00:00Z",
        last_seen: "2026-08-13T00:00:00Z",
        is_current: false,
    };
    calls.length = 0;
    responses.push({ devices: [device, otherDevice] });
    await context.extLoadDevices();
    const extTbody = roots.get("ext-device-tbody");
    if (extTbody.children.length !== 2) throw new Error("外部设备列表未渲染");
    const listCall = calls.find(call => call.method === "GET");
    if (!listCall || listCall.headers.Authorization !== "Bearer external-fixture-key" ||
        listCall.headers["X-EzWinCommand-Protocol"] !== "2") {
        throw new Error("外部设备列表未携带正确鉴权协议");
    }

    calls.length = 0;
    responses.push(
        { success: true },
        { devices: [device, { ...otherDevice, name: "Renamed External" }] },
    );
    await context.extRenameDevice("other-device", "Other Device");
    const extRenameCall = calls.find(call => call.method === "PATCH");
    if (!extRenameCall || extRenameCall.url !== "/api/devices/other-device") {
        throw new Error("外部重命名未使用 device_id URL");
    }
    if (JSON.parse(extRenameCall.body).name !== "Renamed External") {
        throw new Error("外部重命名请求体错误");
    }

    calls.length = 0;
    responses.push({ success: true }, { devices: [device] });
    await context.extRevokeDevice("other-device", extTbody.children[1], false);
    const extRevokeCall = calls.find(call => call.method === "DELETE");
    if (!extRevokeCall || extRevokeCall.url !== "/api/devices/other-device") {
        throw new Error("外部撤销其他设备未使用 device_id URL");
    }
    if (extTbody.children.length !== 1 || storedKeyValue !== "external-fixture-key") {
        throw new Error("撤销其他设备未保持当前会话");
    }

    responses.push({ success: true });
    await context.extRevokeDevice("android-device", extTbody.children[0], true);
    if (storedKeyValue !== null || roots.get("ext-dashboard").style.display !== "none" ||
        roots.get("ext-standby").style.display !== "") {
        throw new Error("外部自撤销未回到配对页");
    }
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
"""
    result = subprocess.run(
        [node, "--input-type=commonjs", "-e", script, str(app_module.BASE_DIR / "web" / "static" / "app.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout

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
    assert "device_id" in script
    assert "dev.key" not in script
    assert "data-device-key" not in script
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
    assert manager.complete_pairing("server-1", created["pairing_id"], code, "Android Phone") == "fixture-device-credential"
    assert changes == [frozenset({"pairings"}), frozenset({"pairings", "devices"})]

    assert manager.rename_device("device-android", "New Name")
    assert manager.remove_device("device-android")
    assert changes[-2:] == [frozenset({"devices"}), frozenset({"devices"})]


def test_android_lan_command_accepts_valid_bearer() -> None:
    client = _make_client()

    response = client.post(
        "/api/command",
        headers={"Authorization": "Bearer fixture-device-credential", "X-EzWinCommand-Protocol": "2"},
        json={"action": "media.play_pause", "params": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "success": True,
        "message": "executed:media.play_pause",
        "data": {"action": "media.play_pause", "params": {}},
    }