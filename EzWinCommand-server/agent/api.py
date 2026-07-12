"""REST API 路由。

所有的 API 端点在此定义，命令执行通过 Dispatcher 分发。
"""
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent.dispatcher import Dispatcher
from agent.auth import is_local_host
from agent.command_tasks import AsyncCommandService

router = APIRouter()


class CommandRequest(BaseModel):
    """命令执行请求体。"""
    action: str = Field(min_length=1, max_length=128)
    params: dict[str, Any] = Field(default_factory=dict)


class AuthorizeRequest(BaseModel):
    """设备配对请求体。"""
    token: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)


def _is_local_client(request: Request) -> bool:
    """判断请求是否来自本机或 FastAPI TestClient。"""
    host = request.client.host if request.client else ""
    return is_local_host(host)


def _get_dispatcher(request: Request) -> Dispatcher:
    """从 app state 中获取 Dispatcher 单例。"""
    return request.app.state.dispatcher


@router.get("/ping")
async def ping():
    """健康检查。"""
    return {"status": "ok"}



@router.post("/api/command")
async def execute_command(body: CommandRequest, request: Request):
    """统一命令入口；电竞命令仅在校验通过后异步入队。"""
    digest = request.scope.get("state", {}).get("device_digest", "")
    if body.action == "esports_mode":
        dispatcher = _get_dispatcher(request)
        params = body.params
        sub_action = params.get("sub_action") if isinstance(params, dict) else None
        if hasattr(dispatcher, "list_plugins"):
            plugin = next((item for item in dispatcher.list_plugins(include_disabled=True)
                           if item.get("name") == "esports_mode"), None)
            if plugin is None:
                return JSONResponse(status_code=404, content={"detail": "插件不存在: esports_mode"})
            if not plugin.get("enabled") or plugin.get("load_error"):
                return JSONResponse(status_code=409, content={"detail": "插件已禁用或不可用"})
            # Dispatcher 元数据使用字典列表；只允许声明过的 id，避免将整个字典与字符串比较。
            sub_actions = plugin.get("sub_actions") or []
            sub_action_ids = {
                item.get("id") for item in sub_actions
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            }
            if not isinstance(sub_action, str) or sub_action not in sub_action_ids:
                return JSONResponse(status_code=422, content={"detail": "无效的 sub_action"})
        service: AsyncCommandService = request.app.state.async_command_service
        record, _ = service.submit(digest, body.action, params)
        if record.owner_digest != digest:
            return JSONResponse(status_code=409, content={"detail":"相同命令正在执行"})
        return JSONResponse(status_code=202, content={"command_id":record.command_id,"status":record.status})
    dispatcher = _get_dispatcher(request)
    result = dispatcher.execute(body.action, body.params)
    return {"success": result.success, "message": result.message, "data": result.data}

@router.get("/api/commands/{command_id}")
async def get_command(command_id: str, request: Request):
    digest = request.scope.get("state", {}).get("device_digest", "")
    record = request.app.state.async_command_service.get(command_id, digest)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "任务不存在"})
    # 仅暴露任务状态与结果字段，避免泄露所有者、命令参数等敏感内部信息。
    serialized = record.to_dict()
    public_fields = (
        "command_id", "status", "message", "data", "error",
        "created_at", "updated_at", "expires_at",
    )
    return {field: serialized.get(field) for field in public_fields}


@router.get("/api/actions")
async def list_actions(request: Request):
    """列出所有可用的 action。"""
    dispatcher = _get_dispatcher(request)
    return {"actions": dispatcher.list_actions()}


@router.get("/api/plugins")
async def list_plugins(request: Request):
    """列出所有本地插件（含禁用和加载错误信息）。"""
    dispatcher = _get_dispatcher(request)
    return {"plugins": dispatcher.list_plugins(include_disabled=True)}


class _EnablePluginBody(BaseModel):
    """插件启用/禁用请求体。"""
    enabled: bool


@router.patch("/api/plugins/{plugin_name}")
async def set_plugin_enabled(plugin_name: str, body: _EnablePluginBody, request: Request):
    """启用或禁用指定插件。"""
    dispatcher = _get_dispatcher(request)
    success = dispatcher.set_plugin_enabled(plugin_name, body.enabled)
    if not success:
        return JSONResponse(status_code=404, content={"detail": f"未知插件: {plugin_name}"})
    plugin = next(
        item for item in dispatcher.list_plugins(include_disabled=True)
        if item["name"] == plugin_name
    )
    return {"success": True, "plugin": plugin}


def _get_auth_manager(request: Request):
    """从 app state 中获取 AuthManager 单例。"""
    return request.app.state.auth_manager


@router.get("/api/pairing-code")
async def get_pairing_code(request: Request):
    """获取当前配对码状态。

    本机/TestClient 返回 code；非本机只返回状态元数据，避免在局域网泄漏配对码。
    """
    auth_manager = _get_auth_manager(request)
    payload = {
        "has_code": auth_manager.get_pairing_code() is not None,
        "has_devices": auth_manager.has_devices(),
        "expires_in": auth_manager.get_pairing_code_expires_in(),
    }
    if _is_local_client(request):
        payload["code"] = auth_manager.get_pairing_code()
    return payload


@router.post("/api/authorize")
async def authorize(body: AuthorizeRequest, request: Request):
    """新设备配对鉴权。

    无需鉴权。Body: {"token": "配对码", "name": "设备名称"}。
    成功返回 201 + device_key，失败返回 403。
    """
    auth_manager = _get_auth_manager(request)
    device_key = auth_manager.try_pair(body.token, body.name)
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
    """强制生成新配对码（仅 localhost 可达，由 _is_local_client 检查保证）。

    Returns:
        {"code": "a3x9", "expires_in": 300}
    """
    if not _is_local_client(request):
        return JSONResponse(status_code=403, content={"detail": "仅允许本机刷新配对码"})
    auth_manager = _get_auth_manager(request)
    code = auth_manager.generate_new_code()
    return {"code": code, "expires_in": auth_manager.get_pairing_code_expires_in()}


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
