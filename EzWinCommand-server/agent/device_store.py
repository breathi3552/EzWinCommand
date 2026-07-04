"""设备持久化存储。

管理 devices.json，提供设备的增删查改与原子写入。
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


class DeviceStore:
    """设备持久化存储，管理 devices.json 的读写。"""

    def __init__(self, path: str = "agent/devices.json") -> None:
        """初始化存储。

        Args:
            path: devices.json 的文件路径，不存在时自动创建空结构。
        """
        self._path = Path(path)
        self._data: dict = {"devices": {}}
        self._load()

    def _load(self) -> None:
        """从磁盘加载设备数据，文件不存在则初始化为空结构。"""
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            # 兼容旧格式：确保 devices 键存在
            if "devices" not in self._data:
                self._data["devices"] = {}
        else:
            # 确保目录存在
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._data = {"devices": {}}
            self._save()

    def _save(self) -> None:
        """原子写入：先写临时文件，成功后再 rename，防止写一半崩溃损坏数据。"""
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            # 清理可能残留的临时文件
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

    def add_device(self, name: str) -> str:
        """添加一台设备。

        Args:
            name: 设备显示名称。

        Returns:
            生成的设备 key（uuid 十六进制串）。
        """
        key = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        self._data["devices"][key] = {
            "name": name,
            "created_at": now,
            "last_seen": now,
        }
        self._save()
        return key

    def remove_device(self, key: str) -> bool:
        """移除一台设备。

        Args:
            key: 设备 key。

        Returns:
            是否成功移除（key 存在为 True，否则 False）。
        """
        if key not in self._data["devices"]:
            return False
        del self._data["devices"][key]
        self._save()
        return True

    def is_authorized(self, key: str) -> bool:
        """检查设备 key 是否已授权。

        Args:
            key: 设备 key。

        Returns:
            是否存在该设备。
        """
        return key in self._data["devices"]

    def touch(self, key: str) -> None:
        """更新设备的 last_seen 时间戳。

        Args:
            key: 设备 key，不存在时静默忽略。
        """
        if key not in self._data["devices"]:
            return
        self._data["devices"][key]["last_seen"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def list_devices(self) -> list[dict]:
        """列出所有已配对设备。

        Returns:
            设备列表，每项包含 key, name, created_at, last_seen。
        """
        return [
            {
                "key": k,
                "name": v["name"],
                "created_at": v["created_at"],
                "last_seen": v["last_seen"],
            }
            for k, v in self._data["devices"].items()
        ]

    def has_any_device(self) -> bool:
        """检查是否至少有一台已配对设备。

        Returns:
            devices 字典非空时返回 True。
        """
        return len(self._data["devices"]) > 0

    def rename_device(self, key: str, name: str) -> bool:
        """重命名已配对设备。

        Args:
            key: 设备 UUID 密钥。
            name: 新的设备名称。

        Returns:
            设备存在并重命名成功时返回 True，设备不存在返回 False。
        """
        if key not in self._data["devices"]:
            return False
        self._data["devices"][key]["name"] = name
        self._save()
        return True
