"""EzWinCommand 服务端稳定身份。"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import tempfile
import uuid

_SCHEMA_VERSION = 1


def _display_name(value: str) -> str:
    """清洗 TXT/界面使用的显示名，不允许控制字符或过长内容。"""
    value = " ".join(str(value).split())
    value = "".join(ch for ch in value if ch.isprintable())
    return value[:128] or "EzWinCommand Server"


@dataclass(frozen=True, slots=True)
class ServerIdentity:
    server_id: str
    name: str
    version: int = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        parsed = uuid.UUID(self.server_id)
        if parsed.version != 4 or str(parsed) != self.server_id.lower():
            raise ValueError("server_id 必须是规范 UUID v4")
        object.__setattr__(self, "server_id", str(parsed))
        object.__setattr__(self, "name", _display_name(self.name))
        if self.version != _SCHEMA_VERSION:
            raise ValueError("不支持的 identity schema")

    @property
    def short_id(self) -> str:
        return self.server_id.split("-", 1)[0]

    def to_dict(self) -> dict[str, object]:
        return {"version": self.version, "server_id": self.server_id, "name": self.name}

    @classmethod
    def load(cls, path: str | Path, name: str | None = None) -> "ServerIdentity":
        """严格读取 identity；损坏、未知 schema 或不完整时安全生成新身份。"""
        target = Path(path)
        identity: ServerIdentity | None = None
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or set(raw) != {"version", "server_id", "name"}:
                raise ValueError("identity schema invalid")
            if type(raw["version"]) is not int or raw["version"] != _SCHEMA_VERSION:
                raise ValueError("identity schema unsupported")
            if not isinstance(raw["server_id"], str) or not isinstance(raw["name"], str):
                raise ValueError("identity field invalid")
            identity = cls(raw["server_id"], raw["name"], raw["version"])
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            identity = cls(str(uuid.uuid4()), name or socket.gethostname())
            identity._persist(target)
        return identity

    def _persist(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(self.to_dict(), handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            os.replace(temporary, path)
            try:
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def load_server_identity(path: str | Path, name: str | None = None) -> ServerIdentity:
    return ServerIdentity.load(path, name)
