from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid

import pytest

from agent.device_store import DeviceStore
from agent.protocol import PROTOCOL_VERSION
from agent.server_identity import IDENTITY_SCHEMA_VERSION, load_server_identity
from agent import device_store as device_store_module


def test_existing_identity_schema_survives_wire_protocol_upgrade(tmp_path) -> None:
    path = tmp_path / "server_identity.json"
    server_id = "00000000-0000-4000-8000-000000000001"
    path.write_text(
        json.dumps({"version": IDENTITY_SCHEMA_VERSION, "server_id": server_id, "name": "PC"}),
        encoding="utf-8",
    )

    identity = load_server_identity(path)

    assert identity.server_id == server_id
    assert identity.schema_version == IDENTITY_SCHEMA_VERSION
    assert PROTOCOL_VERSION == 2
    assert json.loads(path.read_text(encoding="utf-8"))["server_id"] == server_id


def test_legacy_devices_get_stable_public_ids_without_exposing_credentials(tmp_path) -> None:
    path = tmp_path / "devices.json"
    first_key = f"legacy-{uuid.uuid4().hex}"
    second_key = f"legacy-{uuid.uuid4().hex}"
    created_at = "2026-08-01T00:00:00+00:00"
    last_seen = "2026-08-02T00:00:00+00:00"
    path.write_text(
        json.dumps({
            "devices": {
                first_key: {
                    "name": "Phone",
                    "created_at": created_at,
                    "last_seen": last_seen,
                },
                second_key: {
                    "name": "Tablet",
                    "created_at": created_at,
                    "last_seen": last_seen,
                },
            },
        }),
        encoding="utf-8",
    )

    store = DeviceStore(path)
    first = store.list_devices()
    persisted = json.loads(path.read_text(encoding="utf-8"))["devices"]
    persisted_after_migration = path.read_bytes()
    reloaded = DeviceStore(path)
    second = reloaded.list_devices()

    assert len(first) == 2
    assert {row["name"] for row in first} == {"Phone", "Tablet"}
    assert all(row["created_at"] == created_at for row in first)
    assert all(row["last_seen"] == last_seen for row in first)
    assert store.is_authorized(first_key)
    assert store.is_authorized(second_key)
    device_ids = {record["device_id"] for record in persisted.values()}
    assert len(device_ids) == 2
    assert device_ids.isdisjoint({first_key, second_key})
    assert store.device_id_for_key(first_key) in device_ids
    assert store.device_id_for_key(second_key) in device_ids
    assert second == first
    assert path.read_bytes() == persisted_after_migration


def test_failed_device_id_migration_keeps_last_valid_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "devices.json"
    legacy_key = f"legacy-{uuid.uuid4().hex}"
    path.write_text(
        json.dumps({"devices": {legacy_key: {"name": "Phone", "created_at": "created", "last_seen": "seen"}}}),
        encoding="utf-8",
    )
    before = hashlib.sha256(path.read_bytes()).digest()
    def fail_replace(_: object, __: object) -> None:
        raise OSError("simulated persistence failure")

    monkeypatch.setattr("agent.device_store.os.replace", fail_replace)

    with pytest.raises(OSError):
        DeviceStore(path)

    assert hashlib.sha256(path.read_bytes()).digest() == before
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_concurrent_relation_updates_do_not_resurrect_revoked_device(tmp_path, monkeypatch) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    key_a = store.add_device("A")
    key_b = store.add_device("B")
    devices = {row["name"]: row["device_id"] for row in store.list_devices()}
    device_a = devices["A"]
    device_b = devices["B"]

    original_replace = device_store_module.os.replace
    first_replace_entered = threading.Event()
    second_replace_entered = threading.Event()
    release_first_replace = threading.Event()
    replace_count = 0

    def replace(source: object, target: object) -> None:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 1:
            first_replace_entered.set()
            if not release_first_replace.wait(timeout=2):
                raise TimeoutError("first replacement did not release")
        elif replace_count == 2:
            second_replace_entered.set()
        original_replace(source, target)

    monkeypatch.setattr(device_store_module.os, "replace", replace)
    errors: list[BaseException] = []

    def run(operation) -> None:
        try:
            operation()
        except BaseException as exc:
            errors.append(exc)

    rename = threading.Thread(target=run, args=(lambda: store.rename_device(device_a, "Renamed"),))
    revoke = threading.Thread(target=run, args=(lambda: store.remove_device(device_b),))
    rename.start()
    assert first_replace_entered.wait(timeout=1)
    revoke.start()
    second_replace_entered.wait(timeout=0.2)
    release_first_replace.set()
    rename.join(timeout=2)
    revoke.join(timeout=2)

    assert not errors
    assert not store.is_authorized(key_b)
    assert store.is_authorized(key_a)
    assert {row["name"] for row in store.list_devices()} == {"Renamed"}


def test_concurrent_touch_cannot_restore_a_revoked_credential(tmp_path, monkeypatch) -> None:
    store = DeviceStore(tmp_path / "devices.json")
    key = store.add_device("Phone")
    device_id = store.device_id_for_key(key)
    assert device_id is not None
    original_replace = device_store_module.os.replace
    touch_replace_entered = threading.Event()
    release_touch_replace = threading.Event()
    revoke_replace_entered = threading.Event()
    replace_count = 0

    def replace(source: object, target: object) -> None:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 1:
            touch_replace_entered.set()
            if not release_touch_replace.wait(timeout=2):
                raise TimeoutError("touch replacement did not release")
        elif replace_count == 2:
            revoke_replace_entered.set()
        original_replace(source, target)

    monkeypatch.setattr(device_store_module.os, "replace", replace)
    touch = threading.Thread(target=store.touch, args=(key,))
    revoke = threading.Thread(target=store.remove_device, args=(device_id,))
    touch.start()
    assert touch_replace_entered.wait(timeout=1)
    revoke.start()
    assert not revoke_replace_entered.wait(timeout=0.2)
    release_touch_replace.set()
    touch.join(timeout=2)
    revoke.join(timeout=2)

    assert not touch.is_alive()
    assert not revoke.is_alive()
    assert not store.is_authorized(key)
    assert DeviceStore(tmp_path / "devices.json").list_devices() == []
