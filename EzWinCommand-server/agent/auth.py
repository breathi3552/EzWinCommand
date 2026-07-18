"""线程安全的 HTTP 鉴权与一次性配对状态机。"""
from __future__ import annotations
import hashlib
import logging
import re
import secrets
import time
from threading import RLock
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)
_CODE_LENGTH = 4
_PAIRING_TTL = 300
_MAX_FAILED_ATTEMPTS = 5
_LOCK_DURATION = 30
_TERMINAL_RETENTION = 60
_PUBLIC_GET_PATHS = frozenset({"/ping", "/api/identity", "/api/local/pairings"})
_PAIRING_COMPLETE_PATH = re.compile(r"/api/pairings/[^/]+/complete\Z")
_PAIRING_CANCEL_PATH = re.compile(r"/api/pairings/[^/]+\Z")


def _is_anonymous_request(method: str, path: str) -> bool:
    if method == "GET":
        return path in _PUBLIC_GET_PATHS
    if method == "POST":
        return path == "/api/pairings" or _PAIRING_COMPLETE_PATH.fullmatch(path) is not None
    return method == "DELETE" and _PAIRING_CANCEL_PATH.fullmatch(path) is not None

def is_local_host(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost", "testclient"}

class AuthManager:
    def __init__(self, store, server_id: str = "") -> None:
        self._store = store
        self._server_id = server_id
        self._pairings: dict[str, dict] = {}
        self._pairings_lock = RLock()

    def create_pairing(self, device_name: str = "Android") -> dict:
        with self._pairings_lock:
            pairing_id = secrets.token_urlsafe(16)
            now = time.time()
            self._pairings[pairing_id] = {
                "pairing_id": pairing_id, "server_id": self._server_id,
                "device_name": device_name, "code": "".join(secrets.choice("0123456789") for _ in range(4)),
                "created_at": now, "expires_at": now + _PAIRING_TTL,
                "failed_attempts": 0, "lock_until": 0.0, "terminal_at": None, "status": "pending",
            }
            return {"pairing_id": pairing_id, "server_id": self._server_id, "expires_in": _PAIRING_TTL}

    def list_pairings(self, include_code: bool = False) -> list[dict]:
        with self._pairings_lock:
            now = time.time()
            rows = []
            purge = []
            for pairing_id, p in self._pairings.items():
                if p["status"] in {"pending", "locked"} and now >= p["expires_at"]:
                    p["status"] = "expired"; p["terminal_at"] = now; p["code"] = ""
                elif p["status"] == "locked" and now >= p["lock_until"]:
                    p["status"] = "pending"; p["failed_attempts"] = 0; p["lock_until"] = 0.0
                if p["status"] in {"consumed", "cancelled", "expired"} and now - (p["terminal_at"] or now) >= _TERMINAL_RETENTION:
                    purge.append(pairing_id); continue
                row = {
                    "pairing_id": p["pairing_id"], "server_id": p["server_id"],
                    "device_name": p["device_name"], "status": p["status"],
                    "expires_in": max(0, int(p["expires_at"] - now)),
                    "remaining_attempts": max(0, _MAX_FAILED_ATTEMPTS - p["failed_attempts"]),
                    "locked_until": p["lock_until"] if p["status"] == "locked" else None,
                }
                if include_code and p["status"] in {"pending", "locked"}: row["code"] = p["code"]
                rows.append(row)
            for pairing_id in purge: self._pairings.pop(pairing_id, None)
            return sorted(rows, key=lambda row: (row["status"] not in {"pending", "locked"}, -next(p["created_at"] for p in self._pairings.values() if p["pairing_id"] == row["pairing_id"])))

    def complete_pairing(self, server_id: str, pairing_id: str, code: str, device_name: str) -> str | None:
        if len(code) != 4 or not code.isascii() or not code.isdigit(): return None
        with self._pairings_lock:
            p = self._pairings.get(pairing_id); now = time.time()
            if not p or p["server_id"] != server_id or p["status"] not in {"pending", "locked"}: return None
            if now >= p["expires_at"]: p["status"] = "expired"; p["terminal_at"] = now; p["code"] = ""; return None
            if now < p["lock_until"]: p["status"] = "locked"; return None
            if p["status"] == "locked": p["status"] = "pending"; p["failed_attempts"] = 0; p["lock_until"] = 0.0
            if not secrets.compare_digest(code, p["code"]):
                p["failed_attempts"] += 1
                if p["failed_attempts"] >= _MAX_FAILED_ATTEMPTS:
                    p["lock_until"] = now + _LOCK_DURATION; p["status"] = "locked"
                return None
            try:
                key = self._store.add_device(device_name or p["device_name"])
            except Exception:
                logger.exception("配对设备落盘失败")
                return None
            p["status"] = "consumed"; p["terminal_at"] = now; p["code"] = ""
            return key

    def cancel_pairing(self, pairing_id: str) -> bool:
        with self._pairings_lock:
            p = self._pairings.get(pairing_id)
            if not p or p["status"] not in {"pending", "locked"}: return False
            p["status"] = "cancelled"; p["terminal_at"] = time.time(); p["code"] = ""; return True

    def is_authorized(self, key: str) -> bool:
        ok = self._store.is_authorized(key)
        if ok: self._store.touch(key)
        return ok
    def touch(self, key: str) -> None: self._store.touch(key)
    def list_devices(self) -> list[dict]: return self._store.list_devices()
    def has_devices(self) -> bool: return self._store.has_any_device()
    def remove_device(self, key: str) -> bool: return self._store.remove_device(key)
    def rename_device(self, key: str, name: str) -> bool: return self._store.rename_device(key, name)

def create_auth_middleware(auth_manager: AuthManager):
    class _AuthMiddleware:
        def __init__(self, app: ASGIApp) -> None: self._app = app
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http": return await self._app(scope, receive, send)
            path, method = scope.get("path", ""), scope.get("method", "")
            if method == "OPTIONS" or _is_anonymous_request(method, path) or not path.startswith("/api/"):
                return await self._app(scope, receive, send)
            host = (scope.get("client") or ("", 0))[0]
            if is_local_host(host):
                scope.setdefault("state", {})["device_digest"] = hashlib.sha256(b"ezwincommand:loopback").hexdigest()
                return await self._app(scope, receive, send)
            request = Request(scope, receive); header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer ") or not auth_manager.is_authorized(header[7:]):
                response = JSONResponse(status_code=401, content={"detail": "未授权"})
                return await response(scope, receive, send)
            scope.setdefault("state", {})["device_digest"] = hashlib.sha256(header[7:].encode()).hexdigest()
            await self._app(scope, receive, send)
    return _AuthMiddleware
