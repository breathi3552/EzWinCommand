"""EzWinCommand Agent 入口。

启动 FastAPI 服务，初始化 Dispatcher 并挂载 Web UI。
"""
import argparse
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from agent.api import router as api_router
from agent.dispatcher import Dispatcher
from agent.firewall import add_rule
import config

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
logger.info("已加载 %d 个插件: %s", len(dispatcher.list_actions()), dispatcher.list_actions())

# —— 注册 API 路由 ——
app.include_router(api_router)

# —— 挂载 Web UI ——
web_dir = Path(__file__).parent / "web"
if web_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="webui")
    logger.info("Web UI 已挂载: %s", web_dir)


def main() -> None:
    import uvicorn

    # —— 启动时自动配置防火墙 ——
    add_rule(config.PORT)

    logger.info("启动 EzWinCommand Agent @ http://%s:%d", config.HOST, config.PORT)
    uvicorn.run(app, host=config.HOST, port=config.PORT)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="EzWinCommand Agent",
        description="Windows 命令代理服务",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--install", action="store_true",
        help="注册开机自启动",
    )
    group.add_argument(
        "--uninstall", action="store_true",
        help="注销开机自启动",
    )
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
