"""EzWinCommand Agent 入口。

启动 FastAPI 服务，初始化 Dispatcher 并挂载 Web UI。
"""
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from agent.api import router as api_router
from agent.dispatcher import Dispatcher
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

    logger.info("启动 EzWinCommand Agent @ http://%s:%d", config.HOST, config.PORT)
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
