"""异步命令服务状态与隔离契约测试。"""
from datetime import datetime, timezone, timedelta
import json
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api import router
from agent.auth import AuthManager, create_auth_middleware
from agent.device_store import DeviceStore
from agent.command_tasks import CommandTaskStore, AsyncCommandService
from plugins.base import CommandResult


def test_store_same_owner_dedup_and_cross_owner_conflict(tmp_path):
    store = CommandTaskStore(tmp_path / "tasks.json")
    first, created = store.submit("owner-a", "esports_mode", {"sub_action": "enter"})
    assert created
    same, created = store.submit("owner-a", "esports_mode", {"sub_action": "enter"})
    assert not created and same.command_id == first.command_id
    other, created = store.submit("owner-b", "esports_mode", {"sub_action": "enter"})
    assert not created and other.command_id == first.command_id
    assert other.owner_digest == "owner-a"


def test_running_not_purged_and_restart_recovery(tmp_path):
    path = tmp_path / "tasks.json"
    store = CommandTaskStore(path)
    rec, _ = store.submit("owner", "esports_mode", {"sub_action": "enter"})
    store.update(rec.command_id, status="running")
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    store._records[rec.command_id].updated_at = old
    store._records[rec.command_id].expires_at = old
    store.purge_expired(datetime.now(timezone.utc))
    assert store.get_for_owner(rec.command_id, "owner") is not None

    recovered = CommandTaskStore(path)
    failed = recovered.get_for_owner(rec.command_id, "owner")
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error["code"] == "service_restarted"



def test_queued_recovery_executes_persisted_full_params(tmp_path):
    path = tmp_path / "tasks.json"
    initial = CommandTaskStore(path)
    record, _ = initial.submit("owner", "esports_mode", {"sub_action": "enter", "profile": {"slot": 3}})
    initial._records[record.command_id].status = "queued"
    initial._save()
    seen = []

    class Capture:
        def execute(self, action, params):
            seen.append((action, params))
            return CommandResult(True, "ok", {})

    service = AsyncCommandService(Capture(), CommandTaskStore(path))
    for _ in range(100):
        if service.get(record.command_id, "owner").status == "succeeded":
            break
        time.sleep(0.01)
    assert seen == [("esports_mode", {"sub_action": "enter", "profile": {"slot": 3}})]
    service.executor.shutdown(wait=True)
def test_service_exception_becomes_safe_terminal_failure(tmp_path):
    class Broken:
        def execute(self, action, params):
            raise RuntimeError("secret traceback")
    service = AsyncCommandService(Broken(), CommandTaskStore(tmp_path / "tasks.json"))
    rec, _ = service.submit("owner", "esports_mode", {"sub_action": "enter"})
    for _ in range(100):
        current = service.get(rec.command_id, "owner")
        if current.status == "failed":
            break
        time.sleep(0.01)
    assert current.status == "failed"
    assert current.error["code"] == "command_exception"
    assert "secret" not in json.dumps(current.to_dict())
    service.executor.shutdown(wait=True)


def test_loopback_post_then_get_and_cross_owner_404(tmp_path):
    class Slow:
        def execute(self, action, params):
            time.sleep(0.05)
            return CommandResult(True, "done", {"ok": True})
    app = FastAPI()
    app.include_router(router)
    app.state.dispatcher = Slow()
    app.state.async_command_service = AsyncCommandService(Slow(), CommandTaskStore(tmp_path / "tasks.json"))
    with TestClient(app) as client:
        accepted = client.post("/api/command", json={"action":"esports_mode", "params":{"sub_action":"enter"}})
        assert accepted.status_code == 202
        command_id = accepted.json()["command_id"]
        command_response = client.get(f"/api/commands/{command_id}")
        assert command_response.status_code == 200
        payload = command_response.json()
        assert set(payload) == {
            "command_id", "status", "message", "data", "error",
            "created_at", "updated_at", "expires_at",
        }
        assert not {"owner_digest", "action", "sub_action", "params"} & payload.keys()
        request = client.build_request("GET", f"/api/commands/{command_id}", headers={"X-Owner":"forged"})
        # loopback identity is server-derived; client owner headers do not affect visibility
        assert client.send(request).status_code == 200
    app.state.async_command_service.executor.shutdown(wait=True)

def test_running_command_continues_after_owner_revoke_but_polling_stops(tmp_path):
    started = threading.Event()
    finish = threading.Event()
    finished = threading.Event()

    class Slow:
        def execute(self, action, params):
            started.set()
            assert finish.wait(2)
            finished.set()
            return CommandResult(True, "done", {})

    store = DeviceStore(tmp_path / "devices.json")
    owner_key = store.add_device("Phone")
    other_key = store.add_device("Tablet")
    owner_id = store.device_id_for_key(owner_key)
    assert owner_id is not None
    auth_manager = AuthManager(store, server_id="server")
    service = AsyncCommandService(Slow(), CommandTaskStore(tmp_path / "tasks.json"))
    app = FastAPI()
    app.include_router(router)
    app.state.dispatcher = Slow()
    app.state.async_command_service = service
    app.state.auth_manager = auth_manager
    app.add_middleware(create_auth_middleware(auth_manager))

    def remote(client, method, path, key, **kwargs):
        transport = client._transport
        old_client = transport.client
        transport.client = ("192.168.1.10", 54321)
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Authorization", f"Bearer {key}")
        headers.setdefault("X-EzWinCommand-Protocol", "2")
        kwargs["headers"] = headers
        try:
            return client.request(method, path, **kwargs)
        finally:
            transport.client = old_client

    try:
        with TestClient(app) as client:
            accepted = remote(
                client,
                "POST",
                "/api/command",
                owner_key,
                json={"action": "esports_mode", "params": {"sub_action": "enter"}},
            )
            assert accepted.status_code == 202
            command_id = accepted.json()["command_id"]
            assert started.wait(1)

            revoked = remote(client, "DELETE", f"/api/devices/{owner_id}", owner_key)
            assert revoked.status_code == 200
            assert remote(client, "GET", f"/api/commands/{command_id}", owner_key).status_code == 401
            assert remote(client, "GET", f"/api/commands/{command_id}", other_key).status_code == 404

            finish.set()
            assert finished.wait(1)
    finally:
        finish.set()
        service.executor.shutdown(wait=True)

def test_esports_metadata_dict_ids_accept_enter_exit_and_reject_unknown(tmp_path):
    from pathlib import Path
    from agent.dispatcher import Dispatcher

    dispatcher = Dispatcher()
    root = Path(__file__).resolve().parents[1]
    dispatcher.discover_plugins(root / "plugins", package="plugins")
    # 保留真实 Dispatcher 元数据，仅替换执行体避免测试触发系统副作用。
    dispatcher.execute = lambda action, params: CommandResult(True, "ok", {})
    app = FastAPI()
    app.include_router(router)
    app.state.dispatcher = dispatcher
    service = AsyncCommandService(dispatcher, CommandTaskStore(tmp_path / "tasks.json"))
    app.state.async_command_service = service
    with TestClient(app) as client:
        for sub_action in ("enter", "exit"):
            response = client.post("/api/command", json={"action": "esports_mode", "params": {"sub_action": sub_action}})
            assert response.status_code == 202
        invalid = client.post("/api/command", json={"action": "esports_mode", "params": {"sub_action": "bogus"}})
        assert invalid.status_code == 422
    service.executor.shutdown(wait=True)


def test_rebuilt_service_executes_persisted_queued_task(tmp_path):
    path = tmp_path / "tasks.json"
    original_store = CommandTaskStore(path)
    record, created = original_store.submit("owner", "esports_mode", {"sub_action": "enter"})
    assert created and record.status == "queued"

    class Dispatcher:
        def execute(self, action, params):
            return CommandResult(True, "recovered", {"action": action, "params": params})
    service = AsyncCommandService(Dispatcher(), CommandTaskStore(path))
    try:
        for _ in range(100):
            current = service.get(record.command_id, "owner")
            if current and current.status == "succeeded":
                break
            time.sleep(0.01)
        assert current.status == "succeeded"
        assert current.message == "recovered"
    finally:
        service.executor.shutdown(wait=True)
