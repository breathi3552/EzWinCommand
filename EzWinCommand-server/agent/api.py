"""REST API 路由。

所有的 API 端点在此定义，命令执行通过 Dispatcher 分发。
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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
    return {"success": result.success, "message": result.message, "data": result.data}


@router.get("/api/actions")
async def list_actions(request: Request):
    """列出所有可用的 action。"""
    dispatcher = _get_dispatcher(request)
    return {"actions": dispatcher.list_actions()}


def _get_auth_manager(request: Request):
    """从 app state 中获取 AuthManager 单例。"""
    return request.app.state.auth_manager


@router.get("/api/pairing-code")
async def get_pairing_code(request: Request):
    """获取当前配对码（无设备时有效）。

    无需鉴权。有设备时 code 为 None。
    """
    auth_manager = _get_auth_manager(request)
    code = auth_manager.get_pairing_code()
    return {"code": code, "has_devices": auth_manager.has_devices()}


@router.post("/api/authorize")
async def authorize(request: Request):
    """新设备配对鉴权。

    无需鉴权。Body: {"token": "配对码", "name": "设备名称"}。
    成功返回 201 + device_key，失败返回 403。
    """
    body = await request.json()
    token = body.get("token", "")
    name = body.get("name", "")
    auth_manager = _get_auth_manager(request)
    device_key = auth_manager.try_pair(token, name)
    if device_key:
        return JSONResponse(
            status_code=201,
            content={"success": True, "device_key": device_key},
        )
    return JSONResponse(
        status_code=403,
        content={"success": False, "message": "配对码无效或已锁定"},
    )


@router.get("/api/devices")
async def list_devices(request: Request):
    """列出所有已配对设备。

    需要鉴权。
    """
    auth_manager = _get_auth_manager(request)
    return {"devices": auth_manager.list_devices()}


@router.delete("/api/devices/{device_key}")
async def remove_device(device_key: str, request: Request):
    """移除已配对设备。

    需要鉴权。
    """
    auth_manager = _get_auth_manager(request)
    success = auth_manager.remove_device(device_key)
    return {"success": success}


@router.post("/api/pairing-code/refresh")
async def refresh_pairing_code(request: Request):
    """强制生成新配对码（仅 localhost 可达，中间件已保证）。

    Returns:
        {"code": "a3x9", "expires_in": 300}
    """
    auth_manager = _get_auth_manager(request)
    code = auth_manager.generate_new_code()
    return {"code": code, "expires_in": 300}


class _RenameBody(BaseModel):
    """设备重命名请求体。"""
    name: str


@router.patch("/api/devices/{device_key}")
async def rename_device(device_key: str, body: _RenameBody, request: Request):
    """重命名已配对设备。

    需要鉴权。
    """
    auth_manager = _get_auth_manager(request)
    success = auth_manager.rename_device(device_key, body.name)
    return {"success": success}
