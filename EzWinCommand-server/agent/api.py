"""REST API 路由。

所有的 API 端点在此定义，命令执行通过 Dispatcher 分发。
"""
from fastapi import APIRouter, Request

from agent.dispatcher import Dispatcher

router = APIRouter()


def _get_dispatcher(request: Request) -> Dispatcher:
    """从 app state 中获取 Dispatcher 单例。"""
    return request.app.state.dispatcher


@router.get("/ping")
async def ping():
    """健康检查。"""
    return {"status": "ok"}


@router.get("/status")
async def get_status(request: Request):
    """系统状态快照：CPU、内存等。

    后续可扩展为插件化状态采集。
    """
    import psutil

    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory": psutil.virtual_memory()._asdict(),
    }


@router.post("/api/command")
async def execute_command(request: Request):
    """统一命令入口。

    Body: {"action": "...", "params": {...}}
    """
    body = await request.json()
    dispatcher = _get_dispatcher(request)
    action = body.get("action", "")
    params = body.get("params")
    result = dispatcher.execute(action, params)
    return result.__dict__


@router.get("/api/actions")
async def list_actions(request: Request):
    """列出所有可用的 action。"""
    dispatcher = _get_dispatcher(request)
    return {"actions": dispatcher.list_actions()}
