"""EzWinCommand Server 入口。"""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import asyncio
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from agent.api import LocalEventHub, MediaEventHub, router as api_router
from agent.auth import AuthManager, create_auth_middleware
from agent.command_tasks import AsyncCommandService, CommandTaskStore
from agent.device_store import DeviceStore
from agent.discovery import DiscoveryPublisher
from agent.dispatcher import Dispatcher
from agent.firewall import add_rule
from agent.server_identity import load_server_identity
import config
from media.service import MediaService
from plugins.media import MediaPlugin
from tray import SystemTray

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent


def create_app(media_service: MediaService | None = None) -> FastAPI:
    service = media_service or MediaService()
    identity = load_server_identity(BASE_DIR / "agent" / "server_identity.json", "EzWinCommand Server")
    publisher = DiscoveryPublisher(identity, config.PORT, config.HOST)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        loop = asyncio.get_running_loop()
        media_hub = MediaEventHub(service, loop)
        local_hub = LocalEventHub(loop)
        application.state.media_event_hub = media_hub
        application.state.local_event_hub = local_hub
        application.state.auth_manager.set_change_listener(local_hub.publish)
        try:
            service.start()
            # 发布失败仅隔离发现能力，HTTP 服务继续启动。
            await asyncio.to_thread(publisher.start)
            yield
        finally:
            # 先注销 mDNS，再停止媒体服务，避免退出时留下陈旧服务记录。
            await asyncio.to_thread(publisher.close)
            application.state.auth_manager.set_change_listener(None)
            local_hub.close()
            media_hub.close()
            service.stop()
    application = FastAPI(title="EzWinCommand Server", lifespan=lifespan)
    dispatcher = Dispatcher(plugins_json_path=BASE_DIR / "agent" / "plugins.json")
    dispatcher.discover_plugins(BASE_DIR / "plugins", package="plugins", exclude={"media"})
    dispatcher.register_plugin(MediaPlugin(service))
    application.state.dispatcher = dispatcher
    application.state.media_service = service
    application.state.server_identity = identity
    application.state.discovery_publisher = publisher
    task_store = CommandTaskStore(BASE_DIR / "agent" / "command_tasks.json")
    application.state.async_command_service = AsyncCommandService(dispatcher, task_store)
    application.include_router(api_router)

    device_store = DeviceStore(BASE_DIR / "agent" / "devices.json")
    auth_manager = AuthManager(device_store, server_id=identity.server_id)
    application.state.auth_manager = auth_manager
    application.state.pairing_manager = auth_manager
    application.add_middleware(create_auth_middleware(auth_manager))

    @application.middleware("http")
    async def revalidate_web_shell(request, call_next):
        response = await call_next(request)
        if request.url.path in {"/", "/index.html"}:
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    web_dir = BASE_DIR / "web"
    if web_dir.is_dir():
        application.mount("/", StaticFiles(directory=str(web_dir), html=True), name="webui")
    return application


app = create_app()


def main() -> None:
    add_rule(config.PORT)
    runtime_app = create_app()
    uvicorn_config = uvicorn.Config(runtime_app, host=config.HOST, port=config.PORT, log_level="info")
    server = uvicorn.Server(uvicorn_config)

    def _on_tray_exit() -> None:
        logger.info("托盘退出 → 关闭服务")
        server.should_exit = True

    tray = SystemTray(
        on_exit=_on_tray_exit,
        web_url=f"http://127.0.0.1:{config.PORT}",
        icon_path=BASE_DIR / "assets" / "ezwincommand.ico",
    )
    try:
        tray.start()
    except Exception:
        logger.warning("系统托盘启动失败，以无托盘模式运行")
    logger.info("启动 EzWinCommand Server @ http://%s:%d", config.HOST, config.PORT)
    server.run()
    try:
        tray.stop()
    except Exception:
        pass


def _parse_port_arg(value: str) -> int:
    try:
        return config.parse_port(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="EzWinCommand Server", description="Windows 本地控制服务")
    parser.add_argument("--host", default=None, help="监听地址（临时覆盖配置文件，不写回）")
    parser.add_argument("--port", type=_parse_port_arg, default=None, help="监听端口（临时覆盖配置文件，不写回）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true", help="注册开机自启动")
    group.add_argument("--uninstall", action="store_true", help="注销开机自启动")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    config.override(host=args.host, port=args.port)
    if args.install:
        from startup import install
        install()
        print("EzWinCommand Server 已注册开机自启动。")
    elif args.uninstall:
        from startup import uninstall
        uninstall()
        print("EzWinCommand Server 已注销开机自启动。")
    else:
        main()
