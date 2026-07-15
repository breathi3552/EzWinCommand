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

def test_initialize_does_not_wait_for_first_refresh_and_refresh_can_finish_late() -> None:
    gate = threading.Event()
    refresh_started = threading.Event()

    class HangingRefresh(FakeAdapter):
        async def read_media(self):
            refresh_started.set()
            await asyncio.to_thread(gate.wait)
            return self.media

    adapter = HangingRefresh()
    service = MediaService(lambda: adapter)
    service.start()
    try:
        assert service.snapshot().error is None
        assert refresh_started.wait(1)
        assert service.snapshot().available is False
        gate.set()
        for _ in range(30):
            if service.snapshot().available:
                break
            threading.Event().wait(0.1)
        assert service.snapshot().available is True
    finally:
        gate.set()
        service.stop()

def test_command_returns_while_media_refresh_is_blocked() -> None:
    gate = threading.Event()
    refresh_started = threading.Event()

    class HangingRefresh(FakeAdapter):
        async def read_media(self):
            refresh_started.set()
            await asyncio.to_thread(gate.wait)
            return self.media

    adapter = HangingRefresh()
    service = MediaService(lambda: adapter)
    service.start()
    try:
        assert refresh_started.wait(1)
        result = service.submit("play_pause").result(timeout=1)
        assert result.success is True
        assert adapter.commands == [("play_pause", None, None)]
    finally:
        gate.set()
        service.stop()

def test_service_single_thread_revision_and_artwork_are_independent() -> None:
    adapter = FakeAdapter()
    service = MediaService(lambda: adapter)
    observed = []
    remove = service.add_listener(observed.append)
    service.start()
    try:
        for _ in range(20):
            first = service.snapshot()
            if first.cover is not None:
                break
            threading.Event().wait(0.05)
        assert first.cover and first.cover.startswith("/api/media/cover/")
        token_url = first.cover
        result = service.submit("set_volume", volume=55).result(timeout=1)
        assert result.success is True
        assert service.snapshot().cover == token_url
        assert adapter.commands == [("set_volume", 55, None)]
        for _ in range(20):
            second = service.snapshot()
            if second.volume == 55:
                break
            threading.Event().wait(0.05)
        assert second.volume == 55
        assert second.cover == token_url
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
        for _ in range(20):
            state = service.snapshot()
            if state.volume == 37:
                break
            threading.Event().wait(0.05)
        assert state.available is False
        assert state.playback == "none"
        assert state.error is None
        assert state.volume == 37
        assert state.render_devices[0].id == "render-1"
    finally:
        service.stop()


def _install_fake_windows_modules(monkeypatch, request_async, *, init_error: Exception | None = None):
    calls: list[tuple] = []
    comtypes = ModuleType("comtypes")
    comtypes.COINIT_MULTITHREADED = 0

    def co_initialize_ex(flags):
        calls.append(("init", threading.current_thread().name, threading.get_ident(), flags))
        if init_error is not None:
            raise init_error

    def co_uninitialize():
        calls.append(("uninit", threading.current_thread().name, threading.get_ident()))

    comtypes.CoInitializeEx = co_initialize_ex
    comtypes.CoUninitialize = co_uninitialize
    control = ModuleType("winrt.windows.media.control")
    control.GlobalSystemMediaTransportControlsSessionManager = SimpleNamespace(request_async=request_async)
    control.GlobalSystemMediaTransportControlsSessionPlaybackStatus = SimpleNamespace(PLAYING=1, PAUSED=2)
    monkeypatch.setattr(media_service_module, "comtypes", comtypes)
    monkeypatch.setitem(sys.modules, "winrt.windows.media.control", control)
    return calls


def test_windows_adapter_balances_com_on_media_thread(monkeypatch) -> None:
    class Manager:
        def add_current_session_changed(self, _handler): return "current"
        def add_sessions_changed(self, _handler): return "sessions"
        def remove_current_session_changed(self, event_token): assert event_token == "current"
        def remove_sessions_changed(self, event_token): assert event_token == "sessions"
        def get_current_session(self): return None
        def get_sessions(self): return ()

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
    assert calls[0][3] == 0
    assert len({item[2] for item in calls}) == 1
    assert adapter._com_initialized is False




class _FakeGsmSession:
    def __init__(self, source_id: str, status: int, *, title: str | None = None) -> None:
        self.source_app_user_model_id = source_id
        self.status = status
        self.title = title or source_id
        self.artist = f"{source_id}-artist"
        self.thumbnail = object()
        self.handlers: dict[str, object] = {}
        self.added: list[tuple[str, object]] = []
        self.removed: list[tuple[str, object]] = []
        self.commands: list[str] = []

    def _add(self, event: str, handler):
        handle = (self.source_app_user_model_id, event, len(self.added))
        self.handlers[event] = handler
        self.added.append((event, handle))
        return handle

    def add_media_properties_changed(self, handler): return self._add("media_properties_changed", handler)
    def add_playback_info_changed(self, handler): return self._add("playback_info_changed", handler)
    def remove_media_properties_changed(self, handle): self.removed.append(("media_properties_changed", handle))
    def remove_playback_info_changed(self, handle): self.removed.append(("playback_info_changed", handle))
    def get_playback_info(self): return SimpleNamespace(playback_status=self.status)

    async def try_get_media_properties_async(self):
        return SimpleNamespace(title=self.title, artist=self.artist, thumbnail=self.thumbnail)

    async def try_toggle_play_pause_async(self): self.commands.append("play_pause"); return True
    async def try_skip_previous_async(self): self.commands.append("prev"); return True
    async def try_skip_next_async(self): self.commands.append("next"); return True

    def fire(self, event: str = "playback_info_changed") -> None:
        self.handlers[event](self, None)


class _FakeGsmManager:
    def __init__(self, sessions: list[_FakeGsmSession], current: _FakeGsmSession | None) -> None:
        self.sessions = sessions
        self.current = current
        self.handlers: dict[str, object] = {}
        self.removed: list[tuple[str, object]] = []

    def get_sessions(self): return tuple(self.sessions)
    def get_current_session(self): return self.current
    def add_current_session_changed(self, handler): self.handlers["current_session_changed"] = handler; return "manager-current"
    def add_sessions_changed(self, handler): self.handlers["sessions_changed"] = handler; return "manager-sessions"
    def remove_current_session_changed(self, handle): self.removed.append(("current_session_changed", handle))
    def remove_sessions_changed(self, handle): self.removed.append(("sessions_changed", handle))


def _install_fake_playback_status(monkeypatch) -> None:
    control = ModuleType("winrt.windows.media.control")
    control.GlobalSystemMediaTransportControlsSessionPlaybackStatus = SimpleNamespace(PLAYING=1, PAUSED=2)
    monkeypatch.setitem(sys.modules, "winrt.windows.media.control", control)


def _multi_session_adapter(monkeypatch, sessions, current):
    _install_fake_playback_status(monkeypatch)
    adapter = _WindowsPlatformAdapter()
    adapter._manager = _FakeGsmManager(sessions, current)
    adapter._read_thumbnail = lambda _reference: asyncio.sleep(0, result=(b"cover", "image/png"))
    async def fresh_manager(): return adapter._manager
    adapter._request_session_manager = fresh_manager
    adapter._sync_sessions(force_rebind=True)
    return adapter


def test_s01_playing_session_wins_over_paused_windows_current(monkeypatch) -> None:
    browser = _FakeGsmSession("browser", 2)
    spotify = _FakeGsmSession("spotify", 1)
    adapter = _multi_session_adapter(monkeypatch, [browser, spotify], browser)
    reading = asyncio.run(adapter.read_media())
    assert adapter._session_key == "spotify"
    assert (reading.title, reading.playback) == ("spotify", "playing")


def test_s02_selected_paused_session_is_kept_without_playing_candidate(monkeypatch) -> None:
    browser = _FakeGsmSession("browser", 2)
    spotify = _FakeGsmSession("spotify", 1)
    adapter = _multi_session_adapter(monkeypatch, [browser, spotify], browser)
    spotify.status = 2
    spotify.fire()
    assert adapter._session_key == "spotify"


def test_s03_new_playing_session_replaces_selected_paused_session(monkeypatch) -> None:
    browser = _FakeGsmSession("browser", 2)
    spotify = _FakeGsmSession("spotify", 1)
    adapter = _multi_session_adapter(monkeypatch, [browser, spotify], browser)
    spotify.status = 2
    spotify.fire()
    browser.status = 1
    browser.fire()
    assert adapter._session_key == "browser"


def test_s04_multiple_playing_sessions_are_stable_then_switch_deterministically(monkeypatch) -> None:
    alpha = _FakeGsmSession("alpha", 1)
    spotify = _FakeGsmSession("spotify", 1)
    current = _FakeGsmSession("current", 2)
    adapter = _multi_session_adapter(monkeypatch, [spotify, alpha, current], spotify)
    assert adapter._session_key == "spotify"
    adapter._manager.current = alpha
    adapter._sync_sessions(force_rebind=True)
    assert adapter._session_key == "spotify"
    adapter._manager.sessions.remove(spotify)
    adapter._on_manager_changed()
    assert adapter._session_key == "alpha"


def test_s05_state_artwork_and_commands_share_selected_session(monkeypatch) -> None:
    browser = _FakeGsmSession("browser", 2)
    spotify = _FakeGsmSession("spotify", 1)
    adapter = _multi_session_adapter(monkeypatch, [browser, spotify], browser)
    reading = asyncio.run(adapter.read_media())
    artwork = asyncio.run(adapter.read_artwork())
    results = [asyncio.run(adapter.execute(action, None, None)) for action in ("play_pause", "prev", "next")]
    assert reading.title == "spotify" and artwork == (b"cover", "image/png")
    assert all(result.success for result in results)
    assert spotify.commands == ["play_pause", "prev", "next"]
    assert browser.commands == []


def test_poll_refreshes_same_source_wrapper_playback_state(monkeypatch) -> None:
    browser = _FakeGsmSession("browser", 1)
    spotify = _FakeGsmSession("spotify", 2)
    adapter = _multi_session_adapter(monkeypatch, [browser, spotify], browser)
    assert adapter._session_key == "browser"
    refreshed_browser = _FakeGsmSession("browser", 2)
    refreshed_spotify = _FakeGsmSession("spotify", 1)
    adapter._manager.sessions = [refreshed_browser, refreshed_spotify]
    adapter._manager.current = refreshed_browser
    reading = asyncio.run(adapter.read_media())
    assert adapter._session_key == "spotify"
    assert (reading.title, reading.playback) == ("spotify", "playing")


def test_read_media_uses_fresh_manager_snapshot_when_subscribed_manager_is_stale(monkeypatch) -> None:
    stale_browser = _FakeGsmSession("browser", 1)
    stale_spotify = _FakeGsmSession("spotify", 2)
    adapter = _multi_session_adapter(monkeypatch, [stale_browser, stale_spotify], stale_browser)
    fresh_browser = _FakeGsmSession("browser", 2)
    fresh_spotify = _FakeGsmSession("spotify", 1)
    fresh_manager = _FakeGsmManager([fresh_browser, fresh_spotify], fresh_spotify)

    async def request_fresh_manager(): return fresh_manager

    adapter._request_session_manager = request_fresh_manager
    reading = asyncio.run(adapter.read_media())
    assert adapter._session_key == "spotify"
    assert (reading.title, reading.playback) == ("spotify", "playing")


def test_playback_event_state_survives_stale_manager_poll(monkeypatch) -> None:
    browser = _FakeGsmSession("browser", 2)
    spotify = _FakeGsmSession("spotify", 1)
    adapter = _multi_session_adapter(monkeypatch, [browser, spotify], browser)
    event_spotify = _FakeGsmSession("spotify", 2)
    adapter._on_session_changed(event_spotify)
    reading = asyncio.run(adapter.read_media())
    assert adapter._session_key == "spotify"
    assert (reading.title, reading.playback) == ("spotify", "paused")


def test_artwork_diagnostic_reads_current_properties_reference(monkeypatch) -> None:
    spotify = _FakeGsmSession("spotify", 1)
    adapter = _multi_session_adapter(monkeypatch, [spotify], spotify)
    references = []

    async def thumbnail(reference):
        references.append(reference)
        return b"spotify-cover", "image/png"

    adapter._read_thumbnail = thumbnail

    reading = asyncio.run(adapter.read_media())
    artwork = asyncio.run(adapter.read_artwork())

    assert reading.title == "spotify" and reading.artwork is None
    assert artwork == (b"spotify-cover", "image/png")
    assert references == [spotify.thumbnail]


def test_artwork_diagnostic_failure_does_not_change_media_state(monkeypatch, caplog) -> None:
    spotify = _FakeGsmSession("spotify", 1)
    adapter = _multi_session_adapter(monkeypatch, [spotify], spotify)

    async def thumbnail(_reference):
        raise OSError("thumbnail failed")

    adapter._read_thumbnail = thumbnail

    reading = asyncio.run(adapter.read_media())
    with caplog.at_level("ERROR"):
        artwork = asyncio.run(adapter.read_artwork())

    assert (reading.available, reading.title, reading.playback) == (True, "spotify", "playing")
    assert artwork == (None, None)
    assert "读取媒体封面失败" in caplog.text




def test_s06_candidate_rebind_and_close_remove_every_event_handle(monkeypatch) -> None:
    first_browser = _FakeGsmSession("browser", 2)
    spotify = _FakeGsmSession("spotify", 1)
    adapter = _multi_session_adapter(monkeypatch, [first_browser, spotify], first_browser)
    manager = adapter._manager
    adapter._manager_tokens = [("current_session_changed", "manager-current"), ("sessions_changed", "manager-sessions")]
    replacement_browser = _FakeGsmSession("browser", 2)
    manager.sessions = [replacement_browser, spotify]
    manager.current = replacement_browser
    adapter._on_manager_changed()
    assert len(first_browser.removed) == 2
    assert len(spotify.removed) == 2
    asyncio.run(adapter.close())
    assert len(replacement_browser.removed) == 2
    assert len(spotify.removed) == 4
    assert manager.removed == [
        ("current_session_changed", "manager-current"),
        ("sessions_changed", "manager-sessions"),
    ]
    assert adapter._candidate_sessions == {}
    assert adapter._manager_tokens == []


def test_artwork_diagnostic_gets_properties_and_thumbnail_in_same_task(monkeypatch) -> None:
    spotify = _FakeGsmSession("spotify", 1)
    adapter = _multi_session_adapter(monkeypatch, [spotify], spotify)
    task_ids = []

    async def properties():
        task_ids.append(asyncio.current_task())
        return SimpleNamespace(title=spotify.title, artist=spotify.artist, thumbnail=spotify.thumbnail)

    async def thumbnail(_reference):
        task_ids.append(asyncio.current_task())
        return b"cover", "image/png"

    spotify.try_get_media_properties_async = properties
    adapter._read_thumbnail = thumbnail

    artwork = asyncio.run(adapter.read_artwork())

    assert artwork == (b"cover", "image/png")
    assert len(task_ids) == 2
    assert task_ids[0] is task_ids[1]


def test_windows_adapter_does_not_uninitialize_when_mta_init_fails(monkeypatch) -> None:
    async def request_async():
        raise AssertionError("COM 失败后不得访问 WinRT")

    calls = _install_fake_windows_modules(monkeypatch, request_async, init_error=RuntimeError("mta failed"))
    adapter = _WindowsPlatformAdapter()

    try:
        asyncio.run(adapter.initialize(lambda: None))
    except RuntimeError as exc:
        assert str(exc) == "mta failed"
    else:
        raise AssertionError("MTA 初始化失败必须向上传播")

    assert [item[0] for item in calls] == ["init"]
    assert calls[0][3] == 0
    assert adapter._com_initialized is False


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


def test_windows_adapter_rolls_back_first_manager_token_when_second_add_fails(monkeypatch) -> None:
    removed: list[tuple[str, str]] = []

    class Manager:
        def add_current_session_changed(self, _handler):
            return "current"

        def add_sessions_changed(self, _handler):
            raise RuntimeError("sessions add failed")

        def remove_current_session_changed(self, token):
            removed.append(("current_session_changed", token))

    async def request_async():
        return Manager()

    calls = _install_fake_windows_modules(monkeypatch, request_async)
    adapter = _WindowsPlatformAdapter()

    try:
        asyncio.run(adapter.initialize(lambda: None))
    except RuntimeError as exc:
        assert str(exc) == "sessions add failed"
    else:
        raise AssertionError("第二个事件注册失败必须向上传播")

    assert removed == [("current_session_changed", "current")]
    assert [item[0] for item in calls] == ["init", "uninit"]
    assert adapter._manager_tokens == []
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
