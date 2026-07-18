"""REST API 路由。

所有的 API 端点在此定义，命令执行通过 Dispatcher 分发。
"""
import asyncio
from collections import deque
from dataclasses import asdict
import json
import hashlib
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from agent.dispatcher import Dispatcher
from agent.auth import is_local_host
from agent.command_tasks import AsyncCommandService
from media.service import MediaService, MediaState


def serialize_media_state(state: MediaState) -> dict[str, Any]:
    """将不可变状态转为完整 snake_case wire。"""
    return asdict(state)


class MediaEventHub:
    """主 event loop 内的 64 revision replay 与 latest-wins 订阅管理。"""

    def __init__(self, service: MediaService, loop: asyncio.AbstractEventLoop) -> None:
        self.service = service
        self.loop = loop
        self.replay: deque[MediaState] = deque(maxlen=64)
        self.subscribers: dict[asyncio.Queue[MediaState | None], str] = {}
        self.revoked_digests: set[str] = set()
        current = service.snapshot()
        self.replay.append(current)
        self._remove_listener = service.add_listener(self._from_media_thread)

    def _from_media_thread(self, state: MediaState) -> None:
        self.loop.call_soon_threadsafe(self._accept, state)

    def _accept(self, state: MediaState) -> None:
        if self.replay and state.revision <= self.replay[-1].revision:
            return
        self.replay.append(state)
        for queue, digest in tuple(self.subscribers.items()):
            if digest in self.revoked_digests:
                continue
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(state)

    def close(self) -> None:
        self._remove_listener()
        self.subscribers.clear()
        self.revoked_digests.clear()

    def revoke(self, digest: str) -> None:
        """终止指定已撤销设备的流，并禁止后续状态进入其 queue。"""
        self.revoked_digests.add(digest)
        for queue, subscriber_digest in tuple(self.subscribers.items()):
            if subscriber_digest != digest:
                continue
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(None)


    def _subscribe(self, since: int, digest: str) -> tuple[asyncio.Queue[MediaState | None], list[MediaState]]:
        if digest in self.revoked_digests:
            raise PermissionError
        queue: asyncio.Queue[MediaState | None] = asyncio.Queue(maxsize=1)
        self.subscribers[queue] = digest
        current = self.service.snapshot()
        if since > current.revision:
            self.subscribers.pop(queue, None)
            raise ValueError("revision 不能大于当前值")
        if since == current.revision:
            initial = []
        elif not self.replay or since < self.replay[0].revision:
            initial = [current]
        else:
            initial = [state for state in self.replay if state.revision > since]
        return queue, initial

    def initial(self, since: int) -> list[MediaState]:
        current = self.service.snapshot()
        if since > current.revision:
            raise ValueError("revision 不能大于当前值")
        if since == current.revision:
            return []
        if not self.replay or since < self.replay[0].revision:
            return [current]
        return [state for state in self.replay if state.revision > since]

    async def stream(self, since: int, digest: str = "") -> AsyncIterator[str]:
        try:
            queue, initial = self._subscribe(since, digest)
        except PermissionError:
            return
        try:
            for state in initial:
                yield self.frame(state)
                since = state.revision
            while True:
                try:
                    wakeup = await asyncio.wait_for(queue.get(), timeout=15.0)
                    if wakeup is None or digest in self.revoked_digests:
                        return
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                for state in self.initial(since):
                    yield self.frame(state)
                    since = state.revision
        finally:
            self.subscribers.pop(queue, None)

    @staticmethod
    def frame(state: MediaState) -> str:
        data = json.dumps(serialize_media_state(state), ensure_ascii=False, separators=(",", ":"))
        return f"id: {state.revision}\nevent: media\ndata: {data}\n\n"

router = APIRouter()


class CommandRequest(BaseModel):
    """命令执行请求体。"""
    action: str = Field(min_length=1, max_length=128)
    params: dict[str, Any] = Field(default_factory=dict)


class PairingCreateRequest(BaseModel):
    device_name: str = Field(default="Android", min_length=1, max_length=128)

class PairingCompleteRequest(BaseModel):
    server_id: str
    pairing_id: str
    code: str = Field(min_length=4, max_length=4)
    device_name: str = Field(default="Android", min_length=1, max_length=128)

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



def _validate_media_command(params: dict[str, Any], service: MediaService) -> JSONResponse | None:
    sub_action = params.get("sub_action")
    allowed = {"play_pause", "prev", "next", "set_volume", "set_output_device", "set_input_device"}
    if not isinstance(sub_action, str) or sub_action not in allowed:
        return JSONResponse(status_code=422, content={"detail": "无效的 sub_action"})
    expected = {"sub_action"}
    if sub_action == "set_volume":
        expected.add("volume")
        volume = params.get("volume")
        if isinstance(volume, bool) or not isinstance(volume, int) or not 0 <= volume <= 100:
            return JSONResponse(status_code=422, content={"detail": "volume 必须是 0..100 的整数"})
    elif sub_action in {"set_output_device", "set_input_device"}:
        expected.add("endpoint_id")
        endpoint_id = params.get("endpoint_id")
        if not isinstance(endpoint_id, str) or not endpoint_id:
            return JSONResponse(status_code=422, content={"detail": "endpoint_id 必须是非空字符串"})
        state = service.snapshot()
        devices = state.render_devices if sub_action == "set_output_device" else state.capture_devices
        if endpoint_id not in {device.id for device in devices}:
            return JSONResponse(status_code=409, content={"detail": "endpoint 已失效或不属于对应设备类型"})
    if set(params) != expected:
        return JSONResponse(status_code=422, content={"detail": "媒体命令参数结构无效"})
    return None


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
    if body.action == "media":
        validation_error = _validate_media_command(body.params, request.app.state.media_service)
        if validation_error is not None:
            return validation_error
    dispatcher = _get_dispatcher(request)
    if body.action == "media":
        result = await asyncio.to_thread(dispatcher.execute, body.action, body.params)
    else:
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

@router.get("/api/media/state")
async def get_media_state(request: Request):
    return serialize_media_state(request.app.state.media_service.snapshot())

@router.post("/api/media/refresh")
async def refresh_media_state(request: Request):
    try:
        future = request.app.state.media_service.request_refresh({"devices", "audio", "media", "artwork"})
        state = await asyncio.wrap_future(future)
    except Exception:
        return JSONResponse(status_code=503, content={"detail": "媒体服务不可用"})
    return serialize_media_state(state)


@router.get("/api/media/cover/{artwork_id}")
async def get_media_cover(artwork_id: str, request: Request):
    cover = request.app.state.media_service.get_cover(artwork_id)
    if cover is None:
        return JSONResponse(status_code=404, content={"detail": "封面不存在"})
    data, content_type = cover
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


def _parse_since(request: Request) -> int | JSONResponse:
    raw = request.headers.get("Last-Event-ID")
    if raw is None:
        raw = request.query_params.get("since", "0")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"detail": "revision 必须是非负整数"})
    if value < 0:
        return JSONResponse(status_code=400, content={"detail": "revision 必须是非负整数"})
    return value


@router.get("/api/media/events")
async def get_media_events(request: Request):
    since = _parse_since(request)
    if isinstance(since, JSONResponse):
        return since
    hub: MediaEventHub = request.app.state.media_event_hub
    try:
        hub.initial(since)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    return StreamingResponse(
        hub.stream(since, request.scope.get("state", {}).get("device_digest", "")),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



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
    return request.app.state.auth_manager

@router.get("/api/identity")
async def identity(request: Request):
    value = request.app.state.server_identity
    return {"protocol_version": value.version, "server_id": value.server_id,
            "display_name": value.name, "port": request.app.state.discovery_publisher.port}

@router.post("/api/pairings", status_code=201)
async def create_pairing(body: PairingCreateRequest, request: Request):
    return _get_auth_manager(request).create_pairing(body.device_name)

@router.post("/api/pairings/{pairing_id}/complete")
async def complete_pairing(pairing_id: str, body: PairingCompleteRequest, request: Request):
    if body.pairing_id != pairing_id:
        return JSONResponse(status_code=404, content={"detail": "配对请求不存在"})
    key = _get_auth_manager(request).complete_pairing(body.server_id, pairing_id, body.code, body.device_name)
    if not key:
        return JSONResponse(status_code=403, content={"detail": "验证码无效或已锁定"})
    return JSONResponse(status_code=201, content={"success": True, "device_key": key})

@router.delete("/api/pairings/{pairing_id}")
async def cancel_pairing(pairing_id: str, request: Request):
    ok = _get_auth_manager(request).cancel_pairing(pairing_id)
    return Response(status_code=204 if ok else 404)

@router.get("/api/local/pairings")
async def local_pairings(request: Request):
    if not _is_local_client(request):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return {"pairings": _get_auth_manager(request).list_pairings(include_code=True)}


@router.get("/api/devices")
async def list_devices(request: Request):
    """列出已配对设备；鉴权中间件仅允许本机无凭据访问。"""
    return {"devices": _get_auth_manager(request).list_devices()}


@router.delete("/api/devices/{device_key}")
async def revoke_device(device_key: str, request: Request):
    """撤销指定设备授权；成功后立即终止该设备的活动媒体流。"""
    success = _get_auth_manager(request).remove_device(device_key)
    if success:
        request.app.state.media_event_hub.revoke(hashlib.sha256(device_key.encode()).hexdigest())
    return {"success": success}
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
