from __future__ import annotations

import asyncio
import sys
import threading
from types import ModuleType, SimpleNamespace

from media.service import AudioEndpoint, MediaService, _AudioReading, _MediaReading, _WindowsPlatformAdapter
import media.service as media_service_module
from plugins.base import CommandResult


class FakeAdapter:
    def __init__(self) -> None:
        self.thread_names: list[str] = []
        self.closed = False
        self.close_count = 0
        self.close_threads: list[str] = []
        self.media = _MediaReading(True, "Song", "Artist", "playing", b"cover-a", "image/png")
        self.audio = _AudioReading(
            37,
            (AudioEndpoint("render-1", "Speakers"),),
            (AudioEndpoint("capture-1", "Mic"),),
            "render-1",
            "capture-1",
        )
        self.commands: list[tuple[str, int | None, str | None]] = []

    async def initialize(self, notify) -> None:
        self.thread_names.append(threading.current_thread().name)
        self.notify = notify

    async def read_media(self) -> _MediaReading:
        self.thread_names.append(threading.current_thread().name)
        return self.media

    def read_audio(self) -> _AudioReading:
        self.thread_names.append(threading.current_thread().name)
        return self.audio

    async def execute(self, sub_action, volume, endpoint_id) -> CommandResult:
        self.thread_names.append(threading.current_thread().name)
        self.commands.append((sub_action, volume, endpoint_id))
        if volume is not None:
            self.audio = _AudioReading(volume, self.audio.render_devices, self.audio.capture_devices, self.audio.selected_render_id, self.audio.selected_capture_id)
        return CommandResult(True, "ok")

    async def close(self) -> None:
        self.thread_names.append(threading.current_thread().name)
        self.close_threads.append(threading.current_thread().name)
        self.close_count += 1
        self.closed = True


def test_initialize_hang_is_bounded_and_submit_unavailable() -> None:
    started = threading.Event()

    class Hanging(FakeAdapter):
        async def initialize(self, notify) -> None:
            started.set()
            await asyncio.Event().wait()

    adapter = Hanging()
    service = MediaService(lambda: adapter)
    service.start()
    try:
        assert started.wait(1)
        assert service.snapshot().error == "媒体服务初始化超时"
        assert service.submit("play").result(timeout=0.2).message == "媒体服务不可用"
    finally:
        service.stop(timeout=1.0)
    assert adapter.closed is True
    assert adapter.close_count == 1
    assert adapter.close_threads == ["EzMediaLoop"]

def test_initialize_late_completion_recovers_without_restart() -> None:
    attempts = 0

    class RetryAdapter(FakeAdapter):
        async def initialize(self, notify) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                await asyncio.Event().wait()

    adapters: list[RetryAdapter] = []
    def make_adapter() -> RetryAdapter:
        adapter = RetryAdapter()
        adapters.append(adapter)
        return adapter
    service = MediaService(make_adapter)
    service.start()
    try:
        assert service.snapshot().error == "媒体服务初始化超时"
        assert service.submit("play").result(timeout=0.2).success is False
        for _ in range(30):
            if service.snapshot().error is None and service.snapshot().available:
                break
            threading.Event().wait(0.1)
        assert attempts >= 2
        assert service.snapshot().error is None
        assert service.submit("play").result(timeout=1).success is True
    finally:
        service.stop(timeout=1.0)
    assert len(adapters) >= 2
    assert all(item.close_count == 1 for item in adapters)

def test_stop_before_start_and_repeat_stop() -> None:
    service = MediaService(FakeAdapter)
    service.stop(timeout=0.1)
    service.start()
    service.stop(timeout=1.0)
    service.stop(timeout=0.1)
def test_late_bootstrap_exception_closes_adapter() -> None:
    gate = threading.Event()
    adapter = FakeAdapter()
    async def failing_read():
        await asyncio.to_thread(gate.wait)
        raise RuntimeError("late")
    adapter.read_media = failing_read
    service = MediaService(lambda: adapter)
    service.start(); service.stop(timeout=0.1)
    gate.set(); service.stop(timeout=1.0)
    assert adapter.close_count == 1
    assert adapter.close_threads == ["EzMediaLoop"]

def test_first_refresh_hang_recovers_late() -> None:
    gate = threading.Event()
    released = threading.Event()

    class HangingRefresh(FakeAdapter):
        async def read_media(self):
            if not released.is_set():
                await asyncio.to_thread(gate.wait)
            return self.media

    adapter = HangingRefresh()
    service = MediaService(lambda: adapter)
    service.start()
    try:
        assert service.snapshot().error == "媒体服务初始化超时"
        assert service.submit("play").result(timeout=0.2).message == "媒体服务不可用"
        released.set()
        gate.set()
        for _ in range(30):
            if service.snapshot().error is None and service.snapshot().available:
                break
            threading.Event().wait(0.1)
        assert service.snapshot().error is None
        assert service.submit("play").result(timeout=1).success is True
    finally:
        service.stop()
def test_service_single_thread_revision_and_artwork_are_independent() -> None:
    adapter = FakeAdapter()
    service = MediaService(lambda: adapter)
    observed = []
    remove = service.add_listener(observed.append)
    service.start()
    try:
        first = service.snapshot()
        assert first.revision == 1
        assert first.cover and first.cover.startswith("/api/media/cover/")
        token_url = first.cover

        result = service.submit("set_volume", volume=55).result(timeout=1)
        second = service.snapshot()
        assert result.success is True
        assert second.revision == first.revision + 1
        assert second.volume == 55
        assert second.cover == token_url
        assert adapter.commands == [("set_volume", 55, None)]
        assert observed[-1] == second
        assert set(adapter.thread_names) == {"EzMediaLoop"}
    finally:
        remove()
        service.stop()
    assert adapter.closed is True


def test_cover_cache_keeps_replay_window_and_uses_mime_in_hash() -> None:
    service = MediaService()
    first = service._cache_artwork(b"same", "image/png")
    second = service._cache_artwork(b"same", "image/jpeg")
    assert first != second
    generated = [service._cache_artwork(f"cover-{index}".encode(), "image/png") for index in range(63)]
    assert service.get_cover(first.rsplit("/", 1)[1]) is None
    assert service.get_cover(second.rsplit("/", 1)[1]) == (b"same", "image/jpeg")
    assert all(service.get_cover(path.rsplit("/", 1)[1]) is not None for path in generated)
    assert service.get_cover("not-a-token") is None


def test_runtime_full_domain_failures_close_and_rebootstrap() -> None:
    class FailingAfterBootstrap(FakeAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.media_reads = 0

        async def read_media(self):
            self.media_reads += 1
            if self.media_reads > 1:
                raise RuntimeError("stale media adapter")
            return await super().read_media()

        def read_audio(self):
            if self.media_reads > 1:
                raise RuntimeError("stale audio adapter")
            return super().read_audio()

    first = FailingAfterBootstrap()
    recovered = FakeAdapter()
    adapters = iter((first, recovered))
    service = MediaService(lambda: next(adapters))
    service.start()
    try:
        for _ in range(40):
            if first.closed and service.snapshot().error is None and service.snapshot().available:
                break
            threading.Event().wait(0.1)
        assert first.closed is True
        assert first.close_count == 1
        assert first.close_threads == ["EzMediaLoop"]
        assert service.snapshot().error is None
        assert service.submit("play_pause").result(timeout=1).success is True
    finally:
        service.stop()
    assert recovered.close_count == 1


def test_single_domain_failures_preserve_other_state_without_restart() -> None:
    class MediaOnlyFailure(FakeAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.media_reads = 0

        async def read_media(self):
            self.media_reads += 1
            if self.media_reads > 1:
                raise RuntimeError("transient media failure")
            return await super().read_media()

    adapter = MediaOnlyFailure()
    factory_calls = 0

    def factory():
        nonlocal factory_calls
        factory_calls += 1
        return adapter

    service = MediaService(factory)
    service.start()
    try:
        threading.Event().wait(2.0)
        state = service.snapshot()
        assert factory_calls == 1
        assert adapter.closed is False
        assert state.volume == 37
        assert state.title == "Song"
        assert state.error == "媒体: 读取状态失败"
    finally:
        service.stop()


def test_no_media_is_normal_and_does_not_drop_audio() -> None:
    adapter = FakeAdapter()
    adapter.media = _MediaReading(False, None, None, "none")
    service = MediaService(lambda: adapter)
    service.start()
    try:
        state = service.snapshot()
        assert state.available is False
        assert state.playback == "none"
        assert state.error is None
        assert state.volume == 37
        assert state.render_devices[0].id == "render-1"
    finally:
        service.stop()


def _install_fake_windows_modules(monkeypatch, request_async):
    calls: list[tuple[str, str, int]] = []
    comtypes = ModuleType("comtypes")

    def co_initialize():
        calls.append(("init", threading.current_thread().name, threading.get_ident()))

    def co_uninitialize():
        calls.append(("uninit", threading.current_thread().name, threading.get_ident()))

    comtypes.CoInitialize = co_initialize
    comtypes.CoUninitialize = co_uninitialize
    control = ModuleType("winrt.windows.media.control")
    control.GlobalSystemMediaTransportControlsSessionManager = SimpleNamespace(request_async=request_async)
    monkeypatch.setitem(sys.modules, "comtypes", comtypes)
    monkeypatch.setitem(sys.modules, "winrt.windows.media.control", control)
    return calls


def test_windows_adapter_balances_com_on_media_thread(monkeypatch) -> None:
    class Manager:
        def add_current_session_changed(self, _handler): return "current"
        def add_sessions_changed(self, _handler): return "sessions"
        def remove_current_session_changed(self, event_token): assert event_token == "current"
        def remove_sessions_changed(self, event_token): assert event_token == "sessions"
        def get_current_session(self): return None

    async def request_async():
        return Manager()

    calls = _install_fake_windows_modules(monkeypatch, request_async)

    class Policy:
        def close(self):
            calls.append(("policy_close", threading.current_thread().name, threading.get_ident()))

    monkeypatch.setattr(media_service_module, "_PolicyConfig", Policy)
    adapter = _WindowsPlatformAdapter()

    def run() -> None:
        async def lifecycle() -> None:
            await adapter.initialize(lambda: None)
            await adapter.close()
            await adapter.close()
        asyncio.run(lifecycle())

    thread = threading.Thread(target=run, name="EzMediaLoop")
    thread.start()
    thread.join(2)
    assert not thread.is_alive()
    assert [item[:2] for item in calls] == [
        ("init", "EzMediaLoop"),
        ("policy_close", "EzMediaLoop"),
        ("uninit", "EzMediaLoop"),
    ]
    assert len({item[2] for item in calls}) == 1
    assert adapter._com_initialized is False


def test_windows_adapter_stale_session_properties_timeout_is_no_media(monkeypatch) -> None:
    class Session:
        def add_media_properties_changed(self, _handler): return "media"
        def add_playback_info_changed(self, _handler): return "playback"
        def remove_media_properties_changed(self, token): assert token == "media"
        def remove_playback_info_changed(self, token): assert token == "playback"
        def get_playback_info(self): return SimpleNamespace(playback_status=1)
        async def try_get_media_properties_async(self):
            await asyncio.Event().wait()

    adapter = _WindowsPlatformAdapter()
    adapter._manager = SimpleNamespace(get_current_session=lambda: Session())
    control = ModuleType("winrt.windows.media.control")
    control.GlobalSystemMediaTransportControlsSessionPlaybackStatus = SimpleNamespace(
        PLAYING=1, PAUSED=2,
    )
    monkeypatch.setitem(sys.modules, "winrt.windows.media.control", control)
    monkeypatch.setattr(media_service_module, "MEDIA_PROPERTIES_DEADLINE", 0.01)
    reading = asyncio.run(adapter.read_media())
    assert reading == _MediaReading(False, None, None, "none")
    assert adapter._session is None


def test_windows_adapter_balances_com_when_manager_init_fails(monkeypatch) -> None:
    async def request_async():
        raise RuntimeError("manager failed")

    calls = _install_fake_windows_modules(monkeypatch, request_async)
    monkeypatch.setattr(media_service_module, "_PolicyConfig", lambda: SimpleNamespace())
    adapter = _WindowsPlatformAdapter()

    async def initialize() -> None:
        try:
            await adapter.initialize(lambda: None)
        except RuntimeError as exc:
            assert str(exc) == "manager failed"
        else:
            raise AssertionError("初始化失败必须向上传播")

    asyncio.run(initialize())
    assert [item[0] for item in calls] == ["init", "uninit"]
    assert calls[0][2] == calls[1][2]
    assert adapter._com_initialized is False


def test_set_volume_targets_multimedia_render_when_roles_diverge(monkeypatch) -> None:
    from pycaw.constants import EDataFlow, ERole
    from pycaw.utils import AudioUtilities

    calls = []
    console = SimpleNamespace(GetId=lambda: "console")
    multimedia = SimpleNamespace(GetId=lambda: "multimedia")

    class Enumerator:
        def GetDefaultAudioEndpoint(self, flow, role):
            assert flow == EDataFlow.eRender.value
            return multimedia if role == ERole.eMultimedia.value else console

    endpoint_volume = SimpleNamespace(SetMasterVolumeLevelScalar=lambda value, context: calls.append((value, context)))
    monkeypatch.setattr(AudioUtilities, "GetDeviceEnumerator", staticmethod(lambda: Enumerator()))
    monkeypatch.setattr(AudioUtilities, "CreateDevice", staticmethod(lambda endpoint: SimpleNamespace(EndpointVolume=endpoint_volume if endpoint is multimedia else (_ for _ in ()).throw(AssertionError("不得写 Console endpoint")))))
    adapter = _WindowsPlatformAdapter()
    result = asyncio.run(adapter.execute("set_volume", 37, None))
    assert result.success is True
    assert calls == [(0.37, None)]


def test_policy_config_roles_are_console_then_multimedia_and_partial_failure() -> None:
    from pycaw.constants import ERole

    roles = []
    class Policy:
        def set_default_endpoint(self, endpoint_id, role):
            roles.append((endpoint_id, role))
            if role == ERole.eMultimedia.value:
                raise OSError("role failed")

    adapter = _WindowsPlatformAdapter()
    adapter._policy_config = Policy()
    result = asyncio.run(adapter.execute("set_output_device", None, "out"))
    assert result.success is False
    assert "可能部分完成" in result.message
    assert roles == [("out", ERole.eConsole.value), ("out", ERole.eMultimedia.value)]


def test_policy_config_close_releases_interface_once() -> None:
    released = []
    wrapper = object.__new__(media_service_module._PolicyConfig)
    wrapper._interface = SimpleNamespace(Release=lambda: released.append(threading.get_ident()))
    owner_thread = threading.get_ident()
    wrapper.close()
    wrapper.close()
    assert released == [owner_thread]
    assert wrapper._interface is None
