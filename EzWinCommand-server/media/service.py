"""Windows 媒体与 Core Audio 的单线程后台服务。"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass, replace
import hashlib
import logging
import threading
from typing import Callable, Literal, Protocol

from plugins.base import CommandResult

logger = logging.getLogger(__name__)
MAX_ARTWORK_BYTES = 5 * 1024 * 1024
STARTUP_DEADLINE = 2.0
REPLAY_WINDOW = 64
RUNTIME_FAILURE_THRESHOLD = 3
MEDIA_PROPERTIES_DEADLINE = 0.3
Playback = Literal["playing", "paused", "stopped", "none"]


@dataclass(frozen=True, slots=True)
class AudioEndpoint:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class MediaState:
    revision: int = 0
    available: bool = False
    title: str | None = None
    artist: str | None = None
    playback: Playback = "none"
    cover: str | None = None
    volume: int = 0
    render_devices: tuple[AudioEndpoint, ...] = ()
    capture_devices: tuple[AudioEndpoint, ...] = ()
    selected_render_id: str | None = None
    selected_capture_id: str | None = None
    error: str | None = "媒体服务正在初始化"


@dataclass(frozen=True, slots=True)
class _MediaReading:
    available: bool
    title: str | None
    artist: str | None
    playback: Playback
    artwork: bytes | None = None
    artwork_mime: str | None = None


@dataclass(frozen=True, slots=True)
class _AudioReading:
    volume: int
    render_devices: tuple[AudioEndpoint, ...]
    capture_devices: tuple[AudioEndpoint, ...]
    selected_render_id: str | None
    selected_capture_id: str | None


class _PlatformAdapter(Protocol):
    async def initialize(self, notify: Callable[[], None]) -> None: ...
    async def read_media(self) -> _MediaReading: ...
    def read_audio(self) -> _AudioReading: ...
    async def execute(self, sub_action: str, volume: int | None, endpoint_id: str | None) -> CommandResult: ...
    async def close(self) -> None: ...


class _PolicyConfig:
    """Windows 未公开稳定 IPolicyConfig 的仓库内最小 COM 封装。"""

    def __init__(self) -> None:
        import comtypes
        from pycaw.api.policyconfig import IPolicyConfig
        from pycaw.constants import CLSID_CPolicyConfigClient
        self._interface = comtypes.CoCreateInstance(
            CLSID_CPolicyConfigClient, IPolicyConfig, comtypes.CLSCTX_ALL,
        )

    def set_default_endpoint(self, endpoint_id: str, role: int) -> None:
        result = self._interface.SetDefaultEndpoint(endpoint_id, role)
        if result not in (None, 0):
            raise OSError(f"SetDefaultEndpoint HRESULT={result:#x}")

    def close(self) -> None:
        interface = self._interface
        self._interface = None
        if interface is not None:
            interface.Release()


class _WindowsPlatformAdapter:
    """仅在 EzMediaLoop 内构造和使用的真实 Windows adapter。"""

    def __init__(self) -> None:
        self._manager = None
        self._session = None
        self._manager_tokens: list[tuple[str, object]] = []
        self._session_tokens: list[tuple[str, object]] = []
        self._notify: Callable[[], None] = lambda: None
        self._com_initialized = False
        self._policy_config: _PolicyConfig | None = None

    async def initialize(self, notify: Callable[[], None]) -> None:
        import comtypes
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager

        comtypes.CoInitialize()
        self._com_initialized = True
        self._notify = notify
        try:
            self._manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
            self._manager_tokens = [
                ("current_session_changed", self._manager.add_current_session_changed(self._on_manager_changed)),
                ("sessions_changed", self._manager.add_sessions_changed(self._on_manager_changed)),
            ]
            self._bind_current_session()
            self._policy_config = _PolicyConfig()
        except BaseException:
            await self.close()
            raise

    def _on_manager_changed(self, *_args) -> None:
        self._notify()

    def _on_session_changed(self, *_args) -> None:
        self._notify()

    def _unbind_session(self) -> None:
        if self._session is not None:
            for event, event_token in self._session_tokens:
                try:
                    getattr(self._session, f"remove_{event}")(event_token)
                except Exception:
                    logger.exception("注销 GSMTC session 事件失败: event=%s", event)
        self._session_tokens.clear()
        self._session = None

    def _bind_current_session(self) -> None:
        current = self._manager.get_current_session() if self._manager is not None else None
        if current is self._session:
            return
        self._unbind_session()
        self._session = current
        if current is not None:
            self._session_tokens = [
                ("media_properties_changed", current.add_media_properties_changed(self._on_session_changed)),
                ("playback_info_changed", current.add_playback_info_changed(self._on_session_changed)),
            ]

    async def read_media(self) -> _MediaReading:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status

        self._bind_current_session()
        session = self._session
        if session is None:
            return _MediaReading(False, None, None, "none")
        status = session.get_playback_info().playback_status
        if status not in {Status.PLAYING, Status.PAUSED}:
            return _MediaReading(False, None, None, "none")
        properties_task = asyncio.ensure_future(session.try_get_media_properties_async())
        done, _ = await asyncio.wait({properties_task}, timeout=MEDIA_PROPERTIES_DEADLINE)
        if properties_task not in done:
            # WinRT async operation 的取消可能同步等待底层确认并卡住媒体线程。
            # 保留 pending future 直到其自行结束，只丢弃该旧 session 的结果。
            properties_task.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
            logger.warning("读取媒体属性超时，按无活动媒体处理: operation=read_media_properties")
            self._unbind_session()
            return _MediaReading(False, None, None, "none")
        props = properties_task.result()
        playback: Playback = "playing" if status == Status.PLAYING else "paused"
        artwork = None
        mime = None
        if props is not None and props.thumbnail is not None:
            thumbnail_task = asyncio.create_task(self._read_thumbnail(props.thumbnail))
            done, _ = await asyncio.wait({thumbnail_task}, timeout=MEDIA_PROPERTIES_DEADLINE)
            if thumbnail_task in done:
                try:
                    artwork, mime = thumbnail_task.result()
                except Exception:
                    logger.exception("读取媒体封面失败: operation=read_thumbnail")
            else:
                thumbnail_task.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
                logger.warning("读取媒体封面超时: operation=read_thumbnail")
        return _MediaReading(
            True,
            (props.title or None) if props is not None else None,
            (props.artist or None) if props is not None else None,
            playback,
            artwork,
            mime,
        )

    @staticmethod
    async def _read_thumbnail(reference) -> tuple[bytes | None, str | None]:
        from winrt.windows.storage.streams import DataReader

        stream = None
        reader = None
        try:
            stream = await reference.open_read_async()
            size = int(stream.size)
            if size > MAX_ARTWORK_BYTES:
                raise ValueError(f"封面超过 {MAX_ARTWORK_BYTES} bytes 上限")
            reader = DataReader(stream.get_input_stream_at(0))
            loaded = int(await reader.load_async(size))
            if loaded > MAX_ARTWORK_BYTES:
                raise ValueError(f"封面超过 {MAX_ARTWORK_BYTES} bytes 上限")
            buffer = bytearray(loaded)
            reader.read_bytes(buffer)
            return bytes(buffer), str(stream.content_type or "application/octet-stream")
        finally:
            if reader is not None:
                reader.close()
            if stream is not None:
                stream.close()

    @staticmethod
    def _devices(flow: int) -> tuple[AudioEndpoint, ...]:
        from pycaw.constants import DEVICE_STATE
        from pycaw.utils import AudioUtilities

        return tuple(
            AudioEndpoint(str(device.id), str(device.FriendlyName or device.id))
            for device in AudioUtilities.GetAllDevices(flow, DEVICE_STATE.ACTIVE.value)
        )

    def read_audio(self) -> _AudioReading:
        from pycaw.constants import EDataFlow, ERole
        from pycaw.utils import AudioUtilities

        enumerator = AudioUtilities.GetDeviceEnumerator()
        render = enumerator.GetDefaultAudioEndpoint(EDataFlow.eRender.value, ERole.eMultimedia.value)
        capture = enumerator.GetDefaultAudioEndpoint(EDataFlow.eCapture.value, ERole.eMultimedia.value)
        render_device = AudioUtilities.CreateDevice(render)
        volume = round(float(render_device.EndpointVolume.GetMasterVolumeLevelScalar()) * 100)
        return _AudioReading(
            max(0, min(100, volume)),
            self._devices(EDataFlow.eRender.value),
            self._devices(EDataFlow.eCapture.value),
            str(render.GetId()),
            str(capture.GetId()),
        )

    async def execute(self, sub_action: str, volume: int | None, endpoint_id: str | None) -> CommandResult:
        if sub_action in {"play_pause", "prev", "next"}:
            self._bind_current_session()
            if self._session is None:
                return CommandResult(False, "当前没有可控制的媒体")
            method = {
                "play_pause": self._session.try_toggle_play_pause_async,
                "prev": self._session.try_skip_previous_async,
                "next": self._session.try_skip_next_async,
            }[sub_action]
            accepted = bool(await method())
            return CommandResult(accepted, "媒体操作已执行" if accepted else "播放器拒绝了媒体操作")
        if sub_action == "set_volume":
            from pycaw.constants import EDataFlow, ERole
            from pycaw.utils import AudioUtilities
            enumerator = AudioUtilities.GetDeviceEnumerator()
            render = enumerator.GetDefaultAudioEndpoint(EDataFlow.eRender.value, ERole.eMultimedia.value)
            AudioUtilities.CreateDevice(render).EndpointVolume.SetMasterVolumeLevelScalar(volume / 100.0, None)
            return CommandResult(True, "音量已设置")
        if sub_action in {"set_output_device", "set_input_device"}:
            from pycaw.constants import ERole
            flow = "render" if sub_action == "set_output_device" else "capture"
            completed: list[str] = []
            policy = self._policy_config
            if policy is None:
                raise RuntimeError("PolicyConfig 尚未初始化")
            for role in (ERole.eConsole, ERole.eMultimedia):
                try:
                    policy.set_default_endpoint(endpoint_id, role.value)
                    completed.append(role.name)
                except Exception:
                    logger.exception("设置默认 endpoint 失败: operation=%s flow=%s role=%s endpoint_id=%s", sub_action, flow, role.name, endpoint_id)
                    suffix = "，可能部分完成" if completed else ""
                    return CommandResult(False, f"切换{('输出' if flow == 'render' else '输入')}设备失败{suffix}")
            return CommandResult(True, "默认设备已切换")
        return CommandResult(False, "未知媒体操作")

    async def close(self) -> None:
        self._unbind_session()
        if self._manager is not None:
            for event, event_token in self._manager_tokens:
                try:
                    getattr(self._manager, f"remove_{event}")(event_token)
                except Exception:
                    logger.exception("注销 GSMTC manager 事件失败: event=%s", event)
        self._manager_tokens.clear()
        self._manager = None
        if self._policy_config is not None:
            try:
                self._policy_config.close()
            except Exception:
                logger.exception("释放 PolicyConfig COM 接口失败: operation=close_policy_config")
            self._policy_config = None
        if self._com_initialized:
            import comtypes
            comtypes.CoUninitialize()
            self._com_initialized = False


class MediaService:
    """持有唯一 Windows 媒体线程及不可变快照。"""

    def __init__(self, adapter_factory: Callable[[], _PlatformAdapter] = _WindowsPlatformAdapter) -> None:
        self._adapter_factory = adapter_factory
        self._adapter: _PlatformAdapter | None = None
        self._state = MediaState()
        self._state_lock = threading.Lock()
        self._listeners: set[Callable[[MediaState], None]] = set()
        self._listener_lock = threading.Lock()
        self._covers: OrderedDict[str, tuple[bytes, str]] = OrderedDict()
        self._cover_lock = threading.Lock()
        self._refresh_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._readiness_decision = threading.Event()
        self._media_ready = threading.Event()
        self._stop_signal = threading.Event()
        self._stop_requested: asyncio.Event | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._readiness_decision.clear(); self._media_ready.clear(); self._stop_signal.clear()
        self._thread = threading.Thread(target=self._thread_main, name="EzMediaLoop", daemon=True)
        self._thread.start(); self._readiness_decision.wait(STARTUP_DEADLINE + 0.2)

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop(); self._loop = loop
        try: loop.run_until_complete(self._run())
        except Exception:
            logger.exception("媒体服务线程异常退出"); self._publish_error("媒体服务启动失败"); self._readiness_decision.set()
        finally:
            loop.close()
            self._loop = None

    async def _run(self) -> None:
        self._stop_requested = asyncio.Event()
        if self._stop_signal.is_set():
            self._stop_requested.set()
        stop_task = asyncio.create_task(self._stop_requested.wait())
        first_attempt = True
        try:
            while not stop_task.done():
                attempt = asyncio.create_task(self._bootstrap())
                done, _ = await asyncio.wait(
                    {attempt, stop_task},
                    timeout=STARTUP_DEADLINE if first_attempt else None,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if stop_task in done:
                    attempt.cancel()
                    await asyncio.gather(attempt, return_exceptions=True)
                    break
                if attempt not in done:
                    # 首次 deadline 只决定启动就绪状态；取消后的 adapter
                    # 必须仍在媒体线程清理，再进入有界退避重试。
                    self._publish_error("媒体服务初始化超时")
                    self._readiness_decision.set()
                    first_attempt = False
                    attempt.cancel()
                    await asyncio.gather(attempt, return_exceptions=True)
                    if await self._retry_sleep(stop_task):
                        break
                    continue
                first_attempt = False
                if attempt.cancelled() or attempt.exception() is not None:
                    if await self._retry_sleep(stop_task):
                        break
                    continue
                self._media_ready.set()
                self._readiness_decision.set()
                self._publish_error(None)
                poll = asyncio.create_task(self._poll())
                done, _ = await asyncio.wait({poll, stop_task}, return_when=asyncio.FIRST_COMPLETED)
                if stop_task in done:
                    poll.cancel()
                    await asyncio.gather(poll, return_exceptions=True)
                    break
                await poll
                self._media_ready.clear()
                await self._close_adapter()
                if await self._retry_sleep(stop_task):
                    break
        finally:
            stop_task.cancel()
            await asyncio.gather(stop_task, return_exceptions=True)
            self._media_ready.clear()
            await self._close_adapter()

    async def _close_adapter(self) -> None:
        adapter = self._adapter
        self._adapter = None
        if adapter is None:
            return
        try:
            await adapter.close()
        except Exception:
            logger.exception("释放媒体平台对象失败: operation=close")

    async def _retry_sleep(self, stop_task: asyncio.Task[bool]) -> bool:
        delay = asyncio.create_task(asyncio.sleep(0.1))
        done, _ = await asyncio.wait({delay, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        if stop_task in done:
            delay.cancel()
            await asyncio.gather(delay, return_exceptions=True)
            return True
        return False

    async def _bootstrap(self) -> None:
        adapter = self._adapter_factory()
        installed = False
        healthy = False
        try:
            logger.info("媒体服务阶段开始: operation=initialize")
            await adapter.initialize(self._schedule_refresh)
            if self._stop_requested is not None and self._stop_requested.is_set():
                return
            self._adapter = adapter
            installed = True
            logger.info("媒体服务阶段开始: operation=read_media")
            await self._refresh()
            healthy = True
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("媒体服务初始化失败: operation=initialize/read_media/read_audio")
            raise
        finally:
            if installed and not healthy and self._adapter is adapter:
                self._adapter = None
            if not installed or not healthy:
                try:
                    await adapter.close()
                except Exception:
                    logger.exception("释放失败的媒体 adapter 失败")
    async def _poll(self) -> None:
        consecutive_failures = 0
        while True:
            await asyncio.sleep(0.5)
            media_ok, audio_ok = await self._refresh()
            if media_ok or audio_ok:
                consecutive_failures = 0
                continue
            consecutive_failures += 1
            if consecutive_failures >= RUNTIME_FAILURE_THRESHOLD:
                logger.error(
                    "媒体 adapter 连续读取失败，准备重建: operation=runtime_health failures=%d",
                    consecutive_failures,
                )
                return

    def _schedule_refresh(self) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self._refresh()))

    async def _refresh(self) -> tuple[bool, bool]:
        async with self._refresh_lock:
            adapter = self._adapter
            if adapter is None:
                return False, False
            media = None
            audio = None
            media_error = None
            audio_error = None
            try:
                logger.info("媒体服务阶段开始: operation=read_media")
                media = await adapter.read_media()
            except Exception:
                logger.exception("读取媒体状态失败: operation=read_media")
                media_error = "读取状态失败"
            try:
                logger.info("媒体服务阶段开始: operation=read_audio")
                audio = adapter.read_audio()
            except Exception:
                logger.exception("读取音频状态失败: operation=read_audio")
                audio_error = "读取状态失败"
            old = self.snapshot()
            cover = self._cache_artwork(media.artwork, media.artwork_mime) if media is not None else old.cover
            errors = ([f"媒体: {media_error}"] if media_error else []) + ([f"音频: {audio_error}"] if audio_error else [])
            candidate = MediaState(revision=old.revision, available=media.available if media is not None else old.available, title=media.title if media is not None else old.title, artist=media.artist if media is not None else old.artist, playback=media.playback if media is not None else old.playback, cover=cover, volume=audio.volume if audio is not None else old.volume, render_devices=audio.render_devices if audio is not None else old.render_devices, capture_devices=audio.capture_devices if audio is not None else old.capture_devices, selected_render_id=audio.selected_render_id if audio is not None else old.selected_render_id, selected_capture_id=audio.selected_capture_id if audio is not None else old.selected_capture_id, error="；".join(errors) or None)
            self._publish(candidate)
            return media is not None, audio is not None

    def _cache_artwork(self, data: bytes | None, mime: str | None) -> str | None:
        if data is None:
            return None
        if len(data) > MAX_ARTWORK_BYTES:
            logger.error("封面超过大小上限: operation=cache_artwork bytes=%d", len(data))
            return None
        content_type = mime or "application/octet-stream"
        artwork_id = hashlib.sha256(content_type.encode("utf-8") + b"\0" + data).hexdigest()
        with self._cover_lock:
            self._covers[artwork_id] = (data, content_type)
            self._covers.move_to_end(artwork_id)
            while len(self._covers) > REPLAY_WINDOW:
                self._covers.popitem(last=False)
        return f"/api/media/cover/{artwork_id}"

    def get_cover(self, artwork_id: str) -> tuple[bytes, str] | None:
        if len(artwork_id) != 64 or any(ch not in "0123456789abcdef" for ch in artwork_id):
            return None
        with self._cover_lock:
            return self._covers.get(artwork_id)

    def snapshot(self) -> MediaState:
        with self._state_lock:
            return self._state

    def _publish_error(self, message: str) -> None:
        self._publish(replace(self.snapshot(), error=message))

    def _publish(self, candidate: MediaState) -> None:
        old = self.snapshot()
        if replace(candidate, revision=old.revision) == old:
            return
        state = replace(candidate, revision=old.revision + 1)
        with self._state_lock:
            self._state = state
        with self._listener_lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(state)
            except Exception:
                logger.exception("媒体状态 listener 异常")

    async def _execute(self, sub_action: str, volume: int | None, endpoint_id: str | None) -> CommandResult:
        adapter = self._adapter
        if adapter is None:
            return CommandResult(False, "媒体服务不可用")
        try:
            result = await adapter.execute(sub_action, volume, endpoint_id)
        except Exception:
            logger.exception("媒体命令执行失败: operation=%s", sub_action)
            result = CommandResult(False, "媒体操作失败")
        await self._refresh()
        return result

    def submit(self, sub_action: str, *, volume: int | None = None, endpoint_id: str | None = None) -> Future[CommandResult]:
        loop = self._loop
        if loop is None or not loop.is_running() or not self._media_ready.is_set():
            unavailable: Future[CommandResult] = Future()
            unavailable.set_result(CommandResult(False, "媒体服务不可用"))
            return unavailable
        return asyncio.run_coroutine_threadsafe(self._execute(sub_action, volume, endpoint_id), loop)

    def add_listener(self, listener: Callable[[MediaState], None]) -> Callable[[], None]:
        with self._listener_lock:
            self._listeners.add(listener)
        removed = False
        remove_lock = threading.Lock()

        def remove() -> None:
            nonlocal removed
            with remove_lock:
                if removed:
                    return
                removed = True
            with self._listener_lock:
                self._listeners.discard(listener)
        return remove
    def stop(self, timeout: float = 5.0) -> None:
        thread = self._thread
        self._stop_signal.set()
        if thread is None:
            return
        loop = self._loop
        event = self._stop_requested
        if loop is not None and event is not None and loop.is_running():
            loop.call_soon_threadsafe(event.set)
        thread.join(timeout)
        if thread.is_alive():
            logger.error("媒体服务停止超时: timeout=%s", timeout)
        else:
            self._thread = None
