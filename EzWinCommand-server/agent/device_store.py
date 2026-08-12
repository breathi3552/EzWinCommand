"""设备持久化存储。

管理 devices.json，提供设备的增删查改与原子写入。
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


_LAST_SEEN_WRITE_INTERVAL = 30

class DeviceStore:
    """设备持久化存储，管理 devices.json 的读写。"""

    def __init__(self, path: str | Path = "agent/devices.json") -> None:
        """初始化存储。

        Args:
            path: devices.json 的文件路径，不存在时自动创建空结构。
        """
        self._path = Path(path)
        self._lock = RLock()
        self._data: dict = {"devices": {}}
        self._last_seen_writes: dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        """从磁盘加载设备数据，并为旧记录补充稳定 device_id。"""
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._commit({"devices": {}})
            return

        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("设备存储无法读取") from exc

        if not isinstance(loaded, dict):
            raise ValueError("设备存储格式无效")
        devices = loaded.get("devices", {})
        if not isinstance(devices, dict):
            raise ValueError("设备存储格式无效")

        migrated_devices: dict[str, dict] = {}
        used_ids: set[str] = set()
        migrated = False
        for key, raw_record in devices.items():
            if not isinstance(key, str) or not key or not isinstance(raw_record, dict):
                raise ValueError("设备存储记录无效")
            record = dict(raw_record)
            device_id = record.get("device_id")
            if (
                not isinstance(device_id, str)
                or not device_id.strip()
                or device_id == key
                or device_id in used_ids
            ):
                device_id = self._new_device_id(used_ids)
                record["device_id"] = device_id
                migrated = True
            used_ids.add(device_id)
            migrated_devices[key] = record

        candidate = {"devices": migrated_devices}
        if migrated:
            self._commit(candidate)
        else:
            self._data = candidate

    @staticmethod
    def _new_device_id(used_ids: set[str]) -> str:
        """生成当前存储内唯一且不含凭据材料的设备标识。"""
        while True:
            device_id = str(uuid.uuid4())
            if device_id not in used_ids:
                return device_id

    def _commit(self, candidate: dict) -> None:
        """提交内存快照；失败时恢复旧快照并保留磁盘上的有效文件。"""
        with self._lock:
            previous = self._data
            self._data = candidate
            try:
                self._save()
            except Exception:
                self._data = previous
                raise

    def _save(self) -> None:
        """原子写入：先写临时文件，成功后再 rename。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, self._path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

    def add_device(self, name: str) -> str:
        """添加一台设备并返回仅用于鉴权的 Device Key。"""
        with self._lock:
            key = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            devices = {device_key: dict(record) for device_key, record in self._data["devices"].items()}
            devices[key] = {
                "device_id": self._new_device_id({record["device_id"] for record in devices.values()}),
                "name": name,
                "created_at": now,
                "last_seen": now,
            }
            self._commit({"devices": devices})
            return key

    def remove_device(self, key: str) -> bool:
        """按现有 Device Key 撤销一台设备；device_id 管理切换由后续任务完成。"""
        with self._lock:
            if key not in self._data["devices"]:
                return False
            devices = {
                device_key: dict(record)
                for device_key, record in self._data["devices"].items()
                if device_key != key
            }
            self._commit({"devices": devices})
            return True

    def is_authorized(self, key: str) -> bool:
        """检查 Bearer Device Key 是否已授权。"""
        with self._lock:
            return key in self._data["devices"]

    def device_id_for_key(self, key: str) -> str | None:
        """将当前请求的 Device Key 映射到内部 device_id。"""
        with self._lock:
            record = self._data["devices"].get(key)
            if not isinstance(record, dict):
                return None
            value = record.get("device_id")
            return value if isinstance(value, str) and value else None


    def touch(self, key: str) -> None:
        """更新设备的 last_seen 时间戳，同一设备 30 秒内最多落盘一次。"""
        with self._lock:
            record = self._data["devices"].get(key)
            if not isinstance(record, dict):
                return
            now_dt = datetime.now(timezone.utc)
            now_ts = now_dt.timestamp()
            if now_ts - self._last_seen_writes.get(key, 0.0) < _LAST_SEEN_WRITE_INTERVAL:
                return
            devices = {device_key: dict(value) for device_key, value in self._data["devices"].items()}
            devices[key]["last_seen"] = now_dt.isoformat()
            self._commit({"devices": devices})
            self._last_seen_writes[key] = now_ts

    def list_devices(self) -> list[dict]:
        """保持现有设备管理 wire，device_id 暂只作为持久化关系事实。"""
        with self._lock:
            return [
                {
                    "key": key,
                    "name": record.get("name", ""),
                    "created_at": record.get("created_at"),
                    "last_seen": record.get("last_seen"),
                }
                for key, record in self._data["devices"].items()
            ]

    def has_any_device(self) -> bool:
        """检查是否至少有一台已配对设备。"""
        with self._lock:
            return bool(self._data["devices"])

    def rename_device(self, key: str, name: str) -> bool:
        """按现有 Device Key 重命名设备；device_id 管理切换由后续任务完成。"""
        with self._lock:
            if key not in self._data["devices"]:
                return False
            devices = {device_key: dict(record) for device_key, record in self._data["devices"].items()}
            devices[key]["name"] = name
            self._commit({"devices": devices})
            return True
