"""Windows 媒体与 Core Audio 的单线程后台服务。"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass, replace
import hashlib
import logging
import time
import threading
import comtypes
from typing import Callable, Literal, Protocol

from plugins.base import CommandResult

logger = logging.getLogger(__name__)
MAX_ARTWORK_BYTES = 5 * 1024 * 1024
STARTUP_DEADLINE = 2.0
REPLAY_WINDOW = 64
RUNTIME_FAILURE_THRESHOLD = 3
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
    source_app_user_model_id: str | None = None


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
        self._session_key: str | None = None
        self._manager_tokens: list[tuple[str, object]] = []
        self._candidate_sessions: dict[str, tuple[object, object, list[tuple[str, object]]]] = {}
        self._event_sessions: dict[str, object] = {}
        self._notify: Callable[[], None] = lambda: None
        self._com_initialized = False
        self._policy_config: _PolicyConfig | None = None
        self._device_enumerator = None
        self._device_callback = None
        self._volume_callback = None
        self._volume_interface = None
        self._volume_callback_interface = None
        self._volume_endpoint_id: str | None = None

    async def initialize(self, notify: Callable[[], None]) -> None:
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        self._com_initialized = True
        self._notify = notify
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager

            self._manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
            current_token = self._manager.add_current_session_changed(self._on_manager_changed)
            self._manager_tokens.append(("current_session_changed", current_token))
            sessions_token = self._manager.add_sessions_changed(self._on_manager_changed)
            self._manager_tokens.append(("sessions_changed", sessions_token))
            self._sync_sessions(force_rebind=True)
            self._policy_config = _PolicyConfig()
            self._bind_audio_callbacks()
        except BaseException:
            await self.close()
            raise

    def _bind_audio_callbacks(self) -> None:
        from pycaw.api.endpointvolume import IAudioEndpointVolumeCallback
        from pycaw.callbacks import AudioEndpointVolumeCallback, MMNotificationClient
        from pycaw.utils import AudioUtilities

        notify = self._notify

        class DeviceCallback(MMNotificationClient):
            def on_default_device_changed(self, *_args): notify()
            def on_device_added(self, *_args): notify()
            def on_device_removed(self, *_args): notify()
            def on_device_state_changed(self, *_args): notify()

        class VolumeCallback(AudioEndpointVolumeCallback):
            def on_notify(self, *_args): notify({"audio"})

        self._device_enumerator = AudioUtilities.GetDeviceEnumerator()
        self._device_callback = DeviceCallback()
        self._volume_callback = VolumeCallback()
        self._volume_callback_interface = self._volume_callback.QueryInterface(IAudioEndpointVolumeCallback)
        self._device_enumerator.RegisterEndpointNotificationCallback(self._device_callback)
        self._rebind_volume_callback()

    def _rebind_volume_callback(self, render=None) -> None:
        from pycaw.constants import EDataFlow, ERole
        from pycaw.utils import AudioUtilities

        if render is None:
            enumerator = self._device_enumerator or AudioUtilities.GetDeviceEnumerator()
            render = enumerator.GetDefaultAudioEndpoint(EDataFlow.eRender.value, ERole.eMultimedia.value)
        endpoint_id = str(render.GetId())
        if endpoint_id == self._volume_endpoint_id:
            return
        callback_interface = self._volume_callback_interface
        if callback_interface is None:
            return
        volume_interface = AudioUtilities.CreateDevice(render).EndpointVolume
        volume_interface.RegisterControlChangeNotify(callback_interface)
        old_interface = self._volume_interface
        old_endpoint_id = self._volume_endpoint_id
        if old_interface is not None:
            try:
                old_interface.UnregisterControlChangeNotify(callback_interface)
            except Exception:
                logger.exception("注销旧默认输出音量回调失败: operation=rebind_audio_callback endpoint_id=%s", old_endpoint_id)
        self._volume_interface = volume_interface
        self._volume_endpoint_id = endpoint_id

    @staticmethod
    def _session_key_for(session) -> str | None:
        if session is None:
            return None
        source_id = str(session.source_app_user_model_id or "")
        return source_id or None

    def _on_manager_changed(self, *_args) -> None:
        self._notify()

    def _on_session_changed(self, sender, *_args) -> None:
        # WinRT 回调线程不得读取或改写 GSMTC 对象；只唤醒 EzMediaLoop。
        self._notify()

    def _unbind_candidate(self, session_key: str) -> None:
        binding = self._candidate_sessions.pop(session_key, None)
        if binding is not None:
            _session, event_owner, tokens = binding
            for event, event_token in tokens:
                try:
                    getattr(event_owner, f"remove_{event}")(event_token)
                except Exception:
                    logger.exception("注销 GSMTC session 事件失败: event=%s source_id=%s", event, session_key)
        self._event_sessions.pop(session_key, None)
        if self._session_key == session_key:
            self._session_key = None
            self._session = None

    def _unbind_sessions(self) -> None:
        for session_key in tuple(self._candidate_sessions):
            self._unbind_candidate(session_key)
        self._session_key = None
        self._session = None

    def _bind_candidate(self, session_key: str, session) -> None:
        tokens: list[tuple[str, object]] = []
        try:
            tokens.append(("media_properties_changed", session.add_media_properties_changed(self._on_session_changed)))
            tokens.append(("playback_info_changed", session.add_playback_info_changed(self._on_session_changed)))
        except Exception:
            for event, event_token in tokens:
                try:
                    getattr(session, f"remove_{event}")(event_token)
                except Exception:
                    logger.exception("回滚 GSMTC session 事件失败: event=%s source_id=%s", event, session_key)
            raise
        self._candidate_sessions[session_key] = (session, session, tokens)

    def _select_session(self, current_key: str | None) -> None:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status

        by_status: dict[object, list[str]] = {Status.PLAYING: [], Status.PAUSED: []}
        for session_key, (session, _event_owner, _tokens) in self._candidate_sessions.items():
            try:
                status = session.get_playback_info().playback_status
            except Exception:
                logger.exception("读取 GSMTC playback 状态失败: source_id=%s", session_key)
                continue
            if status in by_status:
                by_status[status].append(session_key)

        eligible = by_status[Status.PLAYING] or by_status[Status.PAUSED]
        if self._session_key in eligible:
            selected_key = self._session_key
        elif current_key in eligible:
            selected_key = current_key
        else:
            selected_key = min(eligible) if eligible else None
        self._session_key = selected_key
        self._session = self._candidate_sessions[selected_key][0] if selected_key is not None else None

    def _sync_sessions(self, *, force_rebind: bool = False, snapshot_manager=None) -> None:
        manager = snapshot_manager or self._manager
        if manager is None:
            return

        sessions: dict[str, object] = {}
        for session in manager.get_sessions():
            session_key = self._session_key_for(session)
            if session_key is not None:
                sessions[session_key] = session
        current_key = self._session_key_for(manager.get_current_session())

        if force_rebind:
            selected_key = self._session_key
            self._unbind_sessions()
            self._session_key = selected_key
        else:
            for session_key in tuple(self._candidate_sessions):
                if session_key not in sessions:
                    self._unbind_candidate(session_key)
        for session_key in sorted(sessions):
            if session_key not in self._candidate_sessions:
                self._bind_candidate(session_key, sessions[session_key])
            else:
                _session, event_owner, tokens = self._candidate_sessions[session_key]
                latest_session = self._event_sessions.pop(session_key, sessions[session_key])
                self._candidate_sessions[session_key] = (latest_session, event_owner, tokens)
        self._select_session(current_key)
        if snapshot_manager is not None and self._manager is not None:
            subscribed_keys = set(self._candidate_sessions)
            for session in self._manager.get_sessions():
                session_key = self._session_key_for(session)
                if session_key is not None and session_key not in subscribed_keys:
                    self._bind_candidate(session_key, session)


    async def _request_session_manager(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager

        return await GlobalSystemMediaTransportControlsSessionManager.request_async()

    async def _refresh_session_snapshots(self) -> None:
        snapshot_manager = await self._request_session_manager()
        self._sync_sessions(snapshot_manager=snapshot_manager)

    async def read_media(self) -> _MediaReading:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status
        await self._refresh_session_snapshots()
        session = self._session
        session_key = self._session_key
        if session is None:
            return _MediaReading(False, None, None, "none")
        status = session.get_playback_info().playback_status
        if status not in {Status.PLAYING, Status.PAUSED}:
            return _MediaReading(False, None, None, "none")
        props = await session.try_get_media_properties_async()
        playback: Playback = "playing" if status == Status.PLAYING else "paused"
        return _MediaReading(
            True,
            (props.title or None) if props is not None else None,
            (props.artist or None) if props is not None else None,
            playback,
            source_app_user_model_id=session_key,
        )

    async def read_artwork(self) -> tuple[bytes | None, str | None]:
        await self._refresh_session_snapshots()
        session = self._session
        session_key = self._session_key
        if session is None:
            return None, None
        props = await session.try_get_media_properties_async()
        if props is None or props.thumbnail is None:
            return None, None
        try:
            return await self._read_thumbnail(props.thumbnail)
        except Exception:
            logger.exception(
                "读取媒体封面失败: operation=read_thumbnail source_id=%s",
                session_key,
            )
            return None, None

    @staticmethod
    async def _read_thumbnail(reference) -> tuple[bytes | None, str | None]:
        from winrt.windows.storage.streams import DataReader

        stream = None
        reader = None
        try:
            started = time.monotonic()
            logger.info("开始打开媒体封面流: operation=open_artwork_stream")
            stream = await reference.open_read_async()
            logger.info(
                "媒体封面流已打开: operation=open_artwork_stream elapsed_ms=%.1f",
                (time.monotonic() - started) * 1000,
            )
            size = int(stream.size)
            if size > MAX_ARTWORK_BYTES:
                raise ValueError(f"封面超过 {MAX_ARTWORK_BYTES} bytes 上限")
            reader = DataReader(stream.get_input_stream_at(0))
            started = time.monotonic()
            logger.info("开始加载媒体封面: operation=load_artwork size=%d", size)
            loaded = int(await reader.load_async(size))
            logger.info(
                "媒体封面已加载: operation=load_artwork elapsed_ms=%.1f loaded_bytes=%d",
                (time.monotonic() - started) * 1000,
                loaded,
            )
            if loaded > MAX_ARTWORK_BYTES:
                raise ValueError(f"封面超过 {MAX_ARTWORK_BYTES} bytes 上限")
            buffer = bytearray(loaded)
            reader.read_bytes(buffer)
            mime = str(stream.content_type or "application/octet-stream")
            logger.info(
                "媒体封面字节读取完成: operation=read_artwork_bytes bytes=%d mime=%s",
                len(buffer),
                mime,
            )
            return bytes(buffer), mime
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

        enumerator = self._device_enumerator or AudioUtilities.GetDeviceEnumerator()
        render = enumerator.GetDefaultAudioEndpoint(EDataFlow.eRender.value, ERole.eMultimedia.value)
        capture = enumerator.GetDefaultAudioEndpoint(EDataFlow.eCapture.value, ERole.eMultimedia.value)
        self._rebind_volume_callback(render)
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
            await self._refresh_session_snapshots()
            session = self._session
            if session is None:
                return CommandResult(False, "当前没有可控制的媒体")
            method = {
                "play_pause": session.try_toggle_play_pause_async,
                "prev": session.try_skip_previous_async,
                "next": session.try_skip_next_async,
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
        self._unbind_sessions()
        if self._manager is not None:
            for event, event_token in self._manager_tokens:
                try:
                    getattr(self._manager, f"remove_{event}")(event_token)
                except Exception:
                    logger.exception("注销 GSMTC manager 事件失败: event=%s", event)
        self._manager_tokens.clear()
        self._manager = None
        callback_interface = self._volume_callback_interface
        if self._volume_interface is not None and callback_interface is not None:
            try:
                self._volume_interface.UnregisterControlChangeNotify(callback_interface)
            except Exception:
                logger.exception("注销默认输出音量回调失败: operation=close_audio_callback endpoint_id=%s", self._volume_endpoint_id)
        self._volume_interface = None
        self._volume_endpoint_id = None
        if self._device_enumerator is not None and self._device_callback is not None:
            try:
                self._device_enumerator.UnregisterEndpointNotificationCallback(self._device_callback)
            except Exception:
                logger.exception("注销音频设备回调失败: operation=close_audio_callback")
        self._volume_callback_interface = None
        self._volume_callback = None
        self._device_callback = None
        self._device_enumerator = None
        if self._policy_config is not None:
            try:
                self._policy_config.close()
            except Exception:
                logger.exception("释放 PolicyConfig COM 接口失败: operation=close_policy_config")
            self._policy_config = None
        if self._com_initialized:
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
        self._dirty: set[str] = set()
        self._dirty_event: asyncio.Event | None = None
        self._refresh_waiters: list[tuple[set[str], asyncio.Future[MediaState]]] = []
        self._artwork_task: asyncio.Task[None] | None = None
        self._media_identity: tuple[str | None, str | None, str | None] | None = None
        self._media_generation = 0
        self._artwork_generation_read: int | None = None
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
        self._dirty_event = asyncio.Event()
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
                self._mark_dirty({"devices", "audio", "media", "artwork"})
                worker = asyncio.create_task(self._dirty_worker())
                done, _ = await asyncio.wait({worker, stop_task}, return_when=asyncio.FIRST_COMPLETED)
                if stop_task in done:
                    worker.cancel()
                    await asyncio.gather(worker, return_exceptions=True)
                    break
                await worker
                self._media_ready.clear()
                await self._close_adapter()
                if await self._retry_sleep(stop_task):
                    break
        finally:
            stop_task.cancel()
            await asyncio.gather(stop_task, return_exceptions=True)
            if self._artwork_task is not None:
                self._artwork_task.cancel()
                await asyncio.gather(self._artwork_task, return_exceptions=True)
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
        try:
            logger.info("媒体服务阶段开始: operation=initialize")
            await adapter.initialize(self._schedule_refresh)
            if self._stop_requested is not None and self._stop_requested.is_set():
                return
            self._adapter = adapter
            installed = True
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("媒体服务初始化失败: operation=initialize")
            raise
        finally:
            if not installed:
                try:
                    await adapter.close()
                except Exception:
                    logger.exception("释放失败的媒体 adapter 失败")

    def _schedule_refresh(self, domains: set[str] | None = None) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._mark_dirty, domains or {"devices", "audio", "media", "artwork"})

    def _mark_dirty(self, domains: set[str]) -> None:
        self._dirty.update(domains)
        if self._dirty_event is not None:
            self._dirty_event.set()

    async def _dirty_worker(self) -> None:
        while True:
            if not self._dirty:
                assert self._dirty_event is not None
                self._dirty_event.clear()
                await self._dirty_event.wait()
            domains = set(self._dirty)
            self._dirty.difference_update(domains)
            completed = await self._refresh(domains)
            state = self.snapshot()
            remaining = []
            for requested, waiter in self._refresh_waiters:
                if waiter.cancelled():
                    continue
                requested.difference_update(completed)
                if requested:
                    remaining.append((requested, waiter))
                else:
                    waiter.set_result(state)
            self._refresh_waiters = remaining

    async def _refresh(self, domains: set[str]) -> set[str]:
        completed: set[str] = set()
        async with self._refresh_lock:
            adapter = self._adapter
            if adapter is None:
                return completed
            if domains & {"devices", "audio"}:
                try:
                    audio = adapter.read_audio()
                    old = self.snapshot()
                    self._publish(replace(
                        old,
                        volume=audio.volume,
                        render_devices=audio.render_devices,
                        capture_devices=audio.capture_devices,
                        selected_render_id=audio.selected_render_id,
                        selected_capture_id=audio.selected_capture_id,
                        error=None,
                    ))
                    completed.update(domains & {"devices", "audio"})
                except Exception:
                    logger.exception("读取音频状态失败: operation=refresh domains=devices,audio")
                    self._publish(replace(self.snapshot(), error="音频: 读取状态失败"))
            if "media" in domains:
                try:
                    media = await adapter.read_media()
                    identity = (media.source_app_user_model_id, media.title, media.artist) if media.available else None
                    old = self.snapshot()
                    if identity != self._media_identity:
                        self._media_identity = identity
                        self._media_generation += 1
                        self._artwork_generation_read = None
                        if self._artwork_task is not None:
                            self._artwork_task.cancel()
                        cover = None
                    else:
                        cover = old.cover
                    self._publish(replace(
                        old,
                        available=media.available,
                        title=media.title,
                        artist=media.artist,
                        playback=media.playback,
                        cover=cover,
                        error=None,
                    ))
                    completed.add("media")
                except Exception:
                    logger.exception("读取媒体状态失败: operation=refresh domain=media")
                    self._publish(replace(self.snapshot(), error="媒体: 读取状态失败"))
            if "artwork" in domains:
                self._start_artwork_read()
                completed.add("artwork")
        return completed

    def _start_artwork_read(self) -> None:
        if self._media_identity is None or self._artwork_generation_read == self._media_generation:
            return
        adapter = self._adapter
        read_artwork = getattr(adapter, "read_artwork", None)
        if read_artwork is None:
            return
        generation = self._media_generation
        identity = self._media_identity
        self._artwork_generation_read = generation
        self._artwork_task = asyncio.create_task(self._read_artwork(read_artwork, identity, generation))

    async def _read_artwork(self, read_artwork, identity, generation: int) -> None:
        try:
            artwork, artwork_mime = await read_artwork()
            cover = self._cache_artwork(artwork, artwork_mime)
            if cover is not None and generation == self._media_generation and identity == self._media_identity:
                self._publish(replace(self.snapshot(), cover=cover))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("读取媒体封面失败: operation=read_artwork generation=%d", generation)
        finally:
            if asyncio.current_task() is self._artwork_task:
                self._artwork_task = None

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
            if result.success:
                domains = {"media"} if sub_action in {"play_pause", "prev", "next"} else {"devices", "audio"}
                await self._request_refresh(domains)
            return result
        except Exception:
            logger.exception("媒体命令执行失败: operation=%s", sub_action)
            return CommandResult(False, "媒体操作失败")

    async def _request_refresh(self, domains: set[str]) -> MediaState:
        if self._adapter is None:
            raise RuntimeError("媒体服务不可用")
        required = set(domains) & {"devices", "audio", "media"}
        waiter = asyncio.get_running_loop().create_future()
        if not required:
            return self.snapshot()
        self._refresh_waiters.append((required, waiter))
        self._mark_dirty(set(domains))
        return await waiter

    def request_refresh(self, domains) -> Future[MediaState]:
        loop = self._loop
        requested = set(domains)
        allowed = {"devices", "audio", "media", "artwork"}
        if not requested or not requested <= allowed or loop is None or not loop.is_running() or not self._media_ready.is_set():
            unavailable: Future[MediaState] = Future()
            unavailable.set_exception(RuntimeError("媒体服务不可用"))
            return unavailable
        return asyncio.run_coroutine_threadsafe(self._request_refresh(requested), loop)

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
