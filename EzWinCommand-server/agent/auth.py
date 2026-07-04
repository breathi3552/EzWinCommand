"""鉴权中间件与配对码管理。

AuthManager 负责设备配对生命周期：生成配对码、验证尝试、锁定防爆破。
create_auth_middleware 工厂函数生成 ASGI 中间件，拦截 /api/* 路径进行 Bearer 鉴权。
"""
import secrets
import time
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


# ---- 配对码常量 ----
_CODE_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
_CODE_LENGTH = 4
_MAX_FAILED_ATTEMPTS = 5
_LOCK_DURATION = 30  # 秒

# ---- 鉴权白名单路径 ----
_WHITELIST_PATHS = frozenset({"/ping", "/api/authorize", "/api/pairing-code"})


class AuthManager:
    """设备配对鉴权管理器。

    管理配对码生命周期、设备密钥验证、失败锁定。
    所有设备持久化委托给 DeviceStore。
    """

    def __init__(self, store) -> None:
        """初始化 AuthManager。

        Args:
            store: DeviceStore 实例，负责设备持久化。
        """
        self._store = store
        self._pairing_code: Optional[str] = None
        self._code_expires_at: float = 0.0
        self._failed_attempts: int = 0
        self._lock_until: float = 0.0

    # ---- 配对码管理 ----

    def _generate_code(self) -> None:
        """从 0-9a-z 字符集中随机生成 4 位配对码。

        使用 secrets 模块以保证加密安全性。
        同时重置失败计数和锁定状态，设置 5 分钟过期时间。
        """
        self._pairing_code = "".join(
            secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH)
        )
        self._failed_attempts = 0
        self._lock_until = 0.0
        self._code_expires_at = time.time() + 300

    def get_pairing_code(self) -> Optional[str]:
        """返回当前配对码。

        若配对码已过期（超过 5 分钟），自动置空。

        Returns:
            当前配对码字符串，若无或过期则返回 None。
        """
        if self._pairing_code is not None and time.time() > self._code_expires_at:
            self._pairing_code = None
        return self._pairing_code

    def generate_new_code(self) -> str:
        """强制生成新配对码，并重置失败计数和锁定状态。

        Returns:
            新生成的配对码字符串。
        """
        self._generate_code()
        return self._pairing_code  # type: ignore[return-value]

    # ---- 配对验证 ----

    def try_pair(self, code: str, device_name: str) -> Optional[str]:
        """尝试验证配对码并注册设备。

        验证逻辑：
        1. 若配对码已过期 → 置空并返回 None
        2. 若当前无配对码 → 返回 None
        3. 若处于锁定状态（lock_until > 当前时间）→ 返回 None
        4. 配对码不匹配 → 累加失败计数，达到阈值则锁定 30 秒，返回 None
        5. 配对码匹配 → 重置状态，invalidate 配对码，调用 store.add_device(name)，返回设备密钥

        Args:
            code: 用户输入的配对码。
            device_name: 设备名称。

        Returns:
            成功时返回设备 UUID 密钥字符串，失败返回 None。
        """
        # 检查配对码是否过期
        if self._pairing_code is not None and time.time() > self._code_expires_at:
            self._pairing_code = None
        if self._pairing_code is None:
            return None

        now = time.time()
        if self._lock_until > now:
            return None

        if code != self._pairing_code:
            self._failed_attempts += 1
            if self._failed_attempts >= _MAX_FAILED_ATTEMPTS:
                self._lock_until = now + _LOCK_DURATION
            return None

        # 配对成功：重置状态，invalidate 配对码，注册设备
        self._failed_attempts = 0
        self._lock_until = 0.0
        self._pairing_code = None

        return self._store.add_device(device_name)

    # ---- 鉴权检查 ----

    def is_authorized(self, key: str) -> bool:
        """检查设备密钥是否已授权，同时更新活跃时间。

        Args:
            key: 设备 UUID 密钥。

        Returns:
            True 表示密钥有效。
        """
        authorized = self._store.is_authorized(key)
        if authorized:
            self._store.touch(key)
        return authorized

    # ---- 透明委托 ----

    def touch(self, key: str) -> None:
        """更新设备活跃时间。"""
        self._store.touch(key)

    def list_devices(self) -> list[dict]:
        """列出所有已注册设备。"""
        return self._store.list_devices()

    def has_devices(self) -> bool:
        """检查是否至少有一台已授权设备。"""
        return self._store.has_any_device()

    def remove_device(self, key: str) -> bool:
        """移除设备。

        Returns:
            True 表示删除成功。
        """
        return self._store.remove_device(key)

    def rename_device(self, key: str, name: str) -> bool:
        """重命名设备。

        Returns:
            True 表示重命名成功，False 表示设备不存在。
        """
        return self._store.rename_device(key, name)


# ---- FastAPI 中间件 ----

def create_auth_middleware(auth_manager: AuthManager):
    """创建 ASGI 鉴权中间件工厂。

    返回一个可调用的类，供 FastAPI/Starlette 的 add_middleware() 使用。
    白名单路径（/ping, /api/authorize, /api/pairing-code）直接放行；
    非 /api/ 前缀路径（静态文件）放行；
    其余 /api/* 路径需携带有效的 Authorization: Bearer <key> 头。

    用法：app.add_middleware(create_auth_middleware(auth_manager))

    Args:
        auth_manager: AuthManager 实例。

    Returns:
        可用于 add_middleware 的中间件类。
    """

    class _AuthMiddleware:
        """ASGI 鉴权中间件。"""

        def __init__(self, app: ASGIApp) -> None:
            self._app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                # 非 HTTP 请求（如 WebSocket）直接放行
                await self._app(scope, receive, send)
                return

            path: str = scope.get("path", "")
            method: str = scope.get("method", "")

            # OPTIONS 预检请求放行（CORS 支持）
            if method == "OPTIONS":
                await self._app(scope, receive, send)
                return

            # 白名单路径放行
            if path in _WHITELIST_PATHS:
                await self._app(scope, receive, send)
                return

            # localhost 请求放行（PC 管理面板无需 Bearer 鉴权）
            client_host = (scope.get("client") or ("", 0))[0]
            if client_host in ("127.0.0.1", "::1", "testclient"):
                await self._app(scope, receive, send)
                return

            # 非 /api/ 前缀放行（静态文件等）
            if not path.startswith("/api/"):
                await self._app(scope, receive, send)
                return

            # /api/* 路径需鉴权
            request = Request(scope, receive)
            auth_header = request.headers.get("Authorization", "")

            if not auth_header.startswith("Bearer "):
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "缺少 Authorization: Bearer <key> 头"},
                )
                await response(scope, receive, send)
                return

            key = auth_header[7:]  # 去掉 "Bearer " 前缀
            if not auth_manager.is_authorized(key):
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "未授权的设备密钥"},
                )
                await response(scope, receive, send)
                return

            await self._app(scope, receive, send)

    return _AuthMiddleware
