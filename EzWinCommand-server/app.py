"""EzWinCommand Agent 入口。

启动 FastAPI 服务，初始化 Dispatcher、防火墙、系统托盘。
"""
import argparse
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from agent.api import router as api_router
from agent.device_store import DeviceStore
from agent.auth import AuthManager, create_auth_middleware
from agent.dispatcher import Dispatcher
from agent.firewall import add_rule
import config
from tray import SystemTray

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="EzWinCommand Agent")

# —— 初始化 Dispatcher ——
dispatcher = Dispatcher()
dispatcher.discover_plugins("plugins")
app.state.dispatcher = dispatcher

# —— 注册 API 路由 ——
app.include_router(api_router)

# —— 挂载 Web UI ——
web_dir = Path(__file__).parent / "web"
if web_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="webui")

# —— 初始化鉴权系统 ——
device_store = DeviceStore()
auth_manager = AuthManager(device_store)
app.state.auth_manager = auth_manager
app.add_middleware(create_auth_middleware(auth_manager))



def main() -> None:
    # —— 启动时自动配置防火墙 ——
    add_rule(config.PORT)

    uvicorn_config = uvicorn.Config(
        app, host=config.HOST, port=config.PORT, log_level="info",
    )
    server = uvicorn.Server(uvicorn_config)

    # —— 系统托盘 ——
    def _on_tray_exit() -> None:
        logger.info("托盘退出 → 关闭服务")
        server.should_exit = True

    tray = SystemTray(on_exit=_on_tray_exit)
    try:
        tray.start()
    except Exception:
        logger.warning("系统托盘启动失败，以无托盘模式运行")

    logger.info("启动 EzWinCommand Agent @ http://%s:%d", config.HOST, config.PORT)
    server.run()

    # 服务退出后清理托盘
    try:
        tray.stop()
    except Exception:
        pass


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="EzWinCommand Agent",
        description="Windows 命令代理服务",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true", help="注册开机自启动")
    group.add_argument("--uninstall", action="store_true", help="注销开机自启动")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.install:
        from startup import install
        install()
        print("EzWinCommand Agent 已注册开机自启动。")
    elif args.uninstall:
        from startup import uninstall
        uninstall()
        print("EzWinCommand Agent 已注销开机自启动。")
    else:
        main()
