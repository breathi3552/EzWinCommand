"""EzWinCommand mDNS 服务发布器。"""
from __future__ import annotations

import ipaddress
import logging
import threading
from typing import Any

import ifaddr

from .server_identity import ServerIdentity

logger = logging.getLogger(__name__)
SERVICE_TYPE = "_ezwincommand._tcp.local."

try:
    from zeroconf import ServiceInfo, Zeroconf
except ImportError:  # 依赖尚未安装时仍允许 HTTP 服务启动
    ServiceInfo = None  # type: ignore[assignment,misc]
    Zeroconf = None  # type: ignore[assignment,misc]


_VIRTUAL_ADAPTER_MARKERS = (
    "virtual", "vpn", "tunnel", "tap", "tun", "loopback", "bluetooth",
    "wi-fi direct", "wifi direct", "hyper-v", "vmware", "vbox", "wsl",
)


def _publishable_ipv4_addresses() -> list[bytes]:
    """返回实体 LAN 网卡上可供同网段客户端访问的 IPv4 地址。"""
    addresses: set[ipaddress.IPv4Address] = set()
    for adapter in ifaddr.get_adapters():
        name = adapter.nice_name.lower()
        if any(marker in name for marker in _VIRTUAL_ADAPTER_MARKERS):
            continue
        for value in adapter.ips:
            if not isinstance(value.ip, str):
                continue
            try:
                address = ipaddress.IPv4Address(value.ip)
            except ipaddress.AddressValueError:
                continue
            if address.is_unspecified or address.is_loopback or address.is_link_local or address.is_multicast:
                continue
            addresses.add(address)
    return [address.packed for address in sorted(addresses, key=int)]


def _server_hostname(short_id: str) -> str:
    return f"ezwincommand-{short_id.lower()}.local."


class DiscoveryPublisher:
    """隔离 mDNS 故障的同步 publisher；不创建或管理 HTTP server。"""

    def __init__(self, identity: ServerIdentity, port: int, host: str = "0.0.0.0") -> None:
        self.identity = identity
        self.port = int(port)
        self.host = host
        self._zeroconf: Any | None = None
        self._service: Any | None = None
        self._lock = threading.Lock()
        self._registered = False

    @property
    def registered(self) -> bool:
        return self._registered

    def start(self) -> bool:
        with self._lock:
            if self._registered:
                return True
            if ServiceInfo is None or Zeroconf is None:
                logger.warning("mDNS 发布不可用：未安装 zeroconf")
                return False
            try:
                addresses = _publishable_ipv4_addresses()
                if not addresses:
                    logger.warning("mDNS 发布不可用：未找到可达 LAN IPv4 地址")
                    return False
                server = _server_hostname(self.identity.short_id)
                info = ServiceInfo(
                    SERVICE_TYPE,
                    f"EzWinCommand-{self.identity.short_id}.{SERVICE_TYPE}",
                    addresses=addresses,
                    port=self.port,
                    properties={
                        b"ver": str(self.identity.version).encode("ascii"),
                        b"id": self.identity.server_id.encode("ascii"),
                        b"name": self.identity.name.encode("utf-8"),
                    },
                    server=server,
                )
                zc = Zeroconf()
                zc.register_service(info)
                self._zeroconf, self._service = zc, info
                self._registered = True
                families = "ipv4" if addresses else "none"
                logger.info(
                    "mDNS 服务已发布: type=%s port=%d id=%s server=%s addresses=%d family=%s",
                    SERVICE_TYPE, self.port, self.identity.short_id, server, len(addresses), families,
                )
                return True
            except Exception:
                logger.exception("mDNS 服务发布失败: type=%s port=%d", SERVICE_TYPE, self.port)
                try:
                    if self._zeroconf is not None:
                        self._zeroconf.close()
                except Exception:
                    logger.exception("mDNS 发布失败后的资源清理异常")
                self._zeroconf = self._service = None
                return False

    def close(self) -> None:
        with self._lock:
            zc, service = self._zeroconf, self._service
            self._zeroconf = self._service = None
            self._registered = False
        if zc is None:
            return
        finished = threading.Event()
        def cleanup() -> None:
            try:
                if service is not None:
                    zc.unregister_service(service)
            except Exception:
                logger.exception("mDNS 服务注销失败: type=%s", SERVICE_TYPE)
            finally:
                try:
                    zc.close()
                except Exception:
                    logger.exception("mDNS publisher 关闭失败: type=%s", SERVICE_TYPE)
                finished.set()
        threading.Thread(target=cleanup, name="EzMdnsClose", daemon=True).start()
        if not finished.wait(2.0):
            logger.error("mDNS 服务注销超时: type=%s timeout=2.0", SERVICE_TYPE)

    unregister = close


MdnsPublisher = DiscoveryPublisher
