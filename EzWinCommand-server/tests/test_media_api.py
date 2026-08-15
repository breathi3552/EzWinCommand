from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from dataclasses import replace
import http.client
import socket
import threading
import time

import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import create_app
from agent.device_store import DeviceStore
from agent.invalidation import DeviceRevoked
from media.service import AudioEndpoint, MediaService, MediaState, _AudioReading, _MediaReading
from plugins.base import CommandResult


class FakeMediaService(MediaService):
    def __init__(self) -> None:
        super().__init__()
        self.started = False
        self._state = MediaState(
            revision=4,
            available=True,
            title="Song",
            artist="Artist",
            playback="playing",
            volume=37,
            render_devices=(AudioEndpoint("out", "Output"),),
            capture_devices=(AudioEndpoint("in", "Input"),),
            selected_render_id="out",
            selected_capture_id="in",
            error=None,
        )
        self.calls = []

    def start(self) -> None:
        self.started = True

    def stop(self, timeout=5.0) -> None:
        self.started = False

    def submit(self, sub_action, *, volume=None, endpoint_id=None):
        from concurrent.futures import Future
        self.calls.append((sub_action, volume, endpoint_id))
        future = Future()
        future.set_result(CommandResult(True, "ok"))
        return future

    def request_refresh(self, domains):
        from concurrent.futures import Future
        self.calls.append(("refresh", frozenset(domains)))
        future = Future()
        future.set_result(self.snapshot())
        return future

class _LiveUvicornServer:
    def __init__(
        self,
        application: FastAPI,
        before_shutdown: Callable[[], None] | None = None,
    ) -> None:
        self._before_shutdown = before_shutdown
        self._socket = socket.socket()
        self._socket.bind(("127.0.0.1", 0))
        self.port = self._socket.getsockname()[1]
        self._server = uvicorn.Server(
            uvicorn.Config(application, host="127.0.0.1", port=self.port, log_level="error")
        )
        self._thread = threading.Thread(
            target=self._server.run,
            kwargs={"sockets": [self._socket]},
            daemon=True,
        )
        self._connections: list[http.client.HTTPConnection] = []

    def start(self) -> None:
        self._thread.start()
        deadline = time.time() + 5
        last_error: OSError | None = None
        while time.time() < deadline:
            try:
                status, _ = self.request("GET", "/ping", timeout=0.5)
                if status == 200:
                    return
            except OSError as exc:
                last_error = exc
                time.sleep(0.05)
        raise AssertionError("HTTP server 未就绪") from last_error

    def request(
        self,
        method: str,
        path: str,
        body: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 5,
    ) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def open_connection(self, timeout: float = 5) -> http.client.HTTPConnection:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        self._connections.append(connection)
        return connection

    def stop(self) -> None:
        for connection in self._connections:
            connection.close()
        self._connections.clear()
        self._server.should_exit = True
        if self._before_shutdown is not None:
            self._before_shutdown()
        if self._thread.is_alive():
            self._thread.join(timeout=5)
        self._socket.close()
        assert not self._thread.is_alive()


@contextmanager
def _run_uvicorn(
    application: FastAPI,
    before_shutdown: Callable[[], None] | None = None,
) -> Iterator[_LiveUvicornServer]:
    live_server = _LiveUvicornServer(application, before_shutdown)
    try:
        live_server.start()
        yield live_server
    finally:
        live_server.stop()

def _read_sse_event(response: http.client.HTTPResponse) -> tuple[str, dict]:
    lines = []
    while True:
        raw = response.readline()
        if not raw:
            raise AssertionError("SSE 流在事件前结束")
        line = raw.decode("utf-8").rstrip("\r\n")
        lines.append(line)
        if line == "":
            break
    event = next((line.removeprefix("event: ") for line in lines if line.startswith("event: ")), "")
    data = next((line.removeprefix("data: ") for line in lines if line.startswith("data: ")), "{}")
    return event, json.loads(data)


def test_hanging_media_service_lifespan_ping() -> None:
    import threading
    import time
    from media.service import _MediaReading
    gate = threading.Event()
    class HangingAdapter:
        closed = False
        close_threads = []
        async def initialize(self, notify):
            await asyncio.to_thread(gate.wait)
        async def read_media(self):
            return _MediaReading(False, None, None, "none")
        def read_audio(self):
            raise RuntimeError("not reached")
        async def execute(self, *args):
            return CommandResult(False, "不可用")
        async def close(self):
            self.closed = True; self.close_threads.append(threading.current_thread().name)
    adapter = HangingAdapter()
    service = MediaService(lambda: adapter)
    try:
        with TestClient(create_app(service)) as client:
            assert client.get("/ping").status_code == 200
            assert client.get("/api/actions").status_code == 200
            assert client.get("/api/devices").status_code == 200
        gate.set()
        service.stop(timeout=1.0)
        assert service._thread is None
        assert adapter.closed is True
        assert adapter.close_threads == ["EzMediaLoop"]
    finally:
        gate.set(); service.stop(timeout=1.0)
def test_hanging_media_service_real_uvicorn_socket_ping() -> None:
    from media.service import _MediaReading

    gate = threading.Event()

    class HangingAdapter:
        async def initialize(self, notify):
            await asyncio.to_thread(gate.wait)
        async def read_media(self):
            return _MediaReading(False, None, None, "none")
        def read_audio(self):
            raise RuntimeError("not reached")
        async def execute(self, *args):
            return CommandResult(False, "不可用")
        async def close(self):
            pass

    service = MediaService(HangingAdapter)
    application = create_app(service)
    with _run_uvicorn(application, before_shutdown=gate.set) as live_server:
        status, body = live_server.request("GET", "/ping")
        assert status == 200
        assert body == b'{"status":"ok"}'


def _remote_request(client: TestClient, method: str, url: str, **kwargs):
    transport = client._transport
    previous = getattr(transport, "client", None)
    transport.client = ("192.168.1.10", 54321)
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("X-EzWinCommand-Protocol", "2")
    kwargs["headers"] = headers
    try:
        return client.request(method, url, **kwargs)
    finally:
        transport.client = previous


def test_state_cover_and_command_validation() -> None:
    service = FakeMediaService()
    cover_url = service._cache_artwork(b"png", "image/png")
    service._state = replace(service._state, cover=cover_url)
    with TestClient(create_app(service)) as client:
        state = client.get("/api/media/state")
        assert state.status_code == 200
        assert state.json()["revision"] == 4
        assert state.json()["render_devices"] == [{"id": "out", "name": "Output"}]

        cover = client.get(cover_url)
        assert cover.status_code == 200
        assert cover.content == b"png"
        assert cover.headers["content-type"] == "image/png"
        assert cover.headers["cache-control"] == "private, max-age=31536000, immutable"
        assert client.get("/api/media/cover/bad").status_code == 404

        good = client.post("/api/command", json={"action": "media", "params": {"sub_action": "set_volume", "volume": 0}})
        assert good.status_code == 200 and good.json()["success"] is True
        assert service.calls[-1] == ("set_volume", 0, None)
        for bad in (True, -1, 101, 1.5, "37"):
            response = client.post("/api/command", json={"action": "media", "params": {"sub_action": "set_volume", "volume": bad}})
            assert response.status_code == 422
        assert client.post("/api/command", json={"action": "media", "params": {"sub_action": "set_output_device", "endpoint_id": "in"}}).status_code == 409
        assert client.post("/api/command", json={"action": "media", "params": {"sub_action": "play_pause", "extra": 1}}).status_code == 422


def test_refresh_returns_existing_media_state_and_503_when_unavailable() -> None:
    service = FakeMediaService()
    with TestClient(create_app(service)) as client:
        response = client.post("/api/media/refresh")
        assert response.status_code == 200
        assert response.json()["revision"] == 4
        assert service.calls[-1] == ("refresh", frozenset({"devices", "audio", "media", "artwork"}))

        from concurrent.futures import Future
        failed = Future()
        failed.set_exception(RuntimeError("internal"))
        service.request_refresh = lambda _domains: failed
        unavailable = client.post("/api/media/refresh")
        assert unavailable.status_code == 503
        assert unavailable.json() == {"detail": "媒体服务不可用"}


def test_successful_media_commands_publish_authoritative_sse_snapshot() -> None:
    class MediaAdapter:
        def __init__(self) -> None:
            self.media = _MediaReading(
                True,
                "before",
                "Artist",
                "playing",
                source_app_user_model_id="player",
            )
            self.audio = _AudioReading(
                37,
                (AudioEndpoint("out", "Output"), AudioEndpoint("out-2", "Output 2")),
                (AudioEndpoint("in", "Input"), AudioEndpoint("in-2", "Input 2")),
                "out",
                "in",
            )
            self.commands: list[tuple[str, int | None, str | None]] = []

        async def initialize(self, notify) -> None:
            self.notify = notify

        async def read_media(self) -> _MediaReading:
            return self.media

        def read_audio(self) -> _AudioReading:
            return self.audio

        async def execute(self, sub_action, volume, endpoint_id) -> CommandResult:
            self.commands.append((sub_action, volume, endpoint_id))
            self.media = replace(
                self.media,
                title=f"{sub_action}-{len(self.commands)}",
                playback="paused" if sub_action == "play_pause" else "playing",
            )
            if sub_action == "set_volume":
                self.audio = replace(self.audio, volume=volume)
            elif sub_action == "set_output_device":
                self.audio = replace(self.audio, selected_render_id=endpoint_id)
            elif sub_action == "set_input_device":
                self.audio = replace(self.audio, selected_capture_id=endpoint_id)
            return CommandResult(True, "媒体操作已执行")

        async def close(self) -> None:
            pass

    def read_sse_frame(response: http.client.HTTPResponse) -> dict:
        lines = []
        while True:
            raw = response.readline()
            if not raw:
                raise AssertionError("SSE 流在发布媒体快照前结束")
            line = raw.decode("utf-8").rstrip("\r\n")
            lines.append(line)
            if line == "":
                break
        data_line = next((line for line in lines if line.startswith("data: ")), None)
        return json.loads(data_line.removeprefix("data: ")) if data_line else {}

    adapter = MediaAdapter()
    service = MediaService(lambda: adapter)
    application = create_app(service)
    application.state.discovery_publisher.start = lambda: None
    application.state.discovery_publisher.close = lambda: None
    with _run_uvicorn(application) as live_server:
        command_cases = (
            ("play_pause", {}, {"playback": "paused"}),
            ("prev", {}, {"playback": "playing"}),
            ("next", {}, {"playback": "playing"}),
            ("set_volume", {"volume": 55}, {"volume": 55}),
            ("set_output_device", {"endpoint_id": "out-2"}, {"selected_render_id": "out-2"}),
            ("set_input_device", {"endpoint_id": "in-2"}, {"selected_capture_id": "in-2"}),
        )
        for sub_action, extra, expected in command_cases:
            status, state_body = live_server.request("GET", "/api/media/state")
            assert status == 200
            before = json.loads(state_body)["revision"]

            events = live_server.open_connection()
            events.request(
                "GET",
                f"/api/media/events?since={before}",
                headers={"Accept": "text/event-stream"},
            )
            event_response = events.getresponse()
            assert event_response.status == 200
            assert event_response.headers["Content-Type"].startswith("text/event-stream")

            params = {"sub_action": sub_action, **extra}
            command_body = json.dumps({"action": "media", "params": params}, ensure_ascii=False)
            status, response_body = live_server.request(
                "POST",
                "/api/command",
                body=command_body,
                headers={"Content-Type": "application/json"},
            )
            assert status == 200
            assert json.loads(response_body)["success"] is True
            assert adapter.commands[-1] == (sub_action, extra.get("volume"), extra.get("endpoint_id"))

            expected_title = f"{sub_action}-{len(adapter.commands)}"
            payload = None
            for _ in range(16):
                try:
                    candidate = read_sse_frame(event_response)
                except TimeoutError as exc:
                    raise AssertionError(f"等待 {sub_action} 的 SSE 超时，before={before}") from exc
                matches_expected = all(candidate.get(field) == value for field, value in expected.items())
                is_media_event = sub_action in {"play_pause", "prev", "next"}
                if matches_expected and (not is_media_event or candidate.get("title") == expected_title):
                    payload = candidate
                    break
            assert payload is not None
            assert payload["revision"] > before
            if is_media_event:
                assert payload["title"] == expected_title
            events.close()


def test_sse_subscribe_registers_before_snapshot() -> None:
    service = FakeMediaService()
    with TestClient(create_app(service)) as client:
        hub = client.app.state.media_event_hub
        original_snapshot = service.snapshot

        def snapshot_after_publish():
            state = original_snapshot()
            if state.revision == 4:
                service._state = replace(state, revision=5, volume=38)
                hub._accept(service._state)
            return service._state

        service.snapshot = snapshot_after_publish
        queue, initial = hub._subscribe(4, "device-a")
        try:
            assert [state.revision for state in initial] == [5]
            assert queue in hub.subscribers
        finally:
            hub.subscribers.pop(queue, None)


def test_slow_media_command_does_not_block_event_loop_ping() -> None:
    started = threading.Event()
    release = threading.Event()

    class SlowMediaService(FakeMediaService):
        def submit(self, sub_action, *, volume=None, endpoint_id=None):
            from concurrent.futures import Future

            self.calls.append((sub_action, volume, endpoint_id))
            future = Future()
            started.set()

            def complete() -> None:
                release.wait()
                future.set_result(CommandResult(True, "ok"))

            threading.Thread(target=complete, daemon=True).start()
            return future

    service = SlowMediaService()
    with TestClient(create_app(service)) as client:
        response = {}

        def send_command() -> None:
            response["value"] = client.post(
                "/api/command",
                json={"action": "media", "params": {"sub_action": "play_pause"}},
            )

        command_thread = threading.Thread(target=send_command)
        command_thread.start()
        try:
            assert started.wait(1)
            assert client.get("/ping").status_code == 200
            assert client.get("/api/media/state").status_code == 200
        finally:
            release.set()
            command_thread.join(2)
        assert not command_thread.is_alive()
        assert response["value"].status_code == 200


def test_actions_clean_cutover_and_sse_replay_framing() -> None:
    service = FakeMediaService()
    with TestClient(create_app(service)) as client:
        actions = client.get("/api/actions").json()["actions"]
        media = [item for item in actions if item["name"] == "media"]
        assert len(media) == 1
        assert [item["id"] for item in media[0]["sub_actions"]] == ["play_pause", "prev", "next"]
        assert all(item["name"] not in {"calculator", "player", "volume"} for item in actions)
        assert client.patch("/api/plugins/player", json={"enabled": True}).status_code == 404
        assert client.patch("/api/plugins/volume", json={"enabled": True}).status_code == 404
        assert client.patch("/api/plugins/calculator", json={"enabled": True}).status_code == 404
        removed = client.post("/api/command", json={"action": "calculator", "params": {}})
        assert removed.status_code == 200
        assert removed.json() == {"success": False, "message": "未知命令: calculator", "data": None}

        service._publish(replace(service.snapshot(), volume=38))
        hub = client.app.state.media_event_hub

        async def read_replay():
            stream = hub.stream(4)
            try:
                return await anext(stream)
            finally:
                await stream.aclose()

        frame = asyncio.run(read_replay())
        assert frame.startswith("id: 5\nevent: media\ndata: ")
        assert '"revision":5' in frame
        assert client.get("/api/media/events?since=999").status_code == 400
        assert client.get("/api/media/events?since=bad").status_code == 400


def test_media_endpoints_reject_invalid_bearer_before_streaming() -> None:
    service = FakeMediaService()
    cover_url = service._cache_artwork(b"private", "image/png")
    with TestClient(create_app(service)) as client:
        for path in ("/api/media/state", "/api/media/refresh", cover_url, "/api/media/events?since=4"):
            method = "POST" if path == "/api/media/refresh" else "GET"
            missing = _remote_request(client, method, path)
            invalid = _remote_request(client, method, path, headers={"Authorization": "Bearer invalid"})
            assert missing.status_code == invalid.status_code == 401
            assert missing.headers["content-type"].startswith("application/json")
            assert invalid.headers["content-type"].startswith("application/json")


def test_last_event_id_priority_old_replay_and_latest_wins_cleanup() -> None:
    from agent.api import _parse_since
    from starlette.requests import Request

    request = Request({"type": "http", "method": "GET", "path": "/api/media/events", "query_string": b"since=999", "headers": [(b"last-event-id", b"4")]})
    assert _parse_since(request) == 4
    service = FakeMediaService()
    with TestClient(create_app(service)) as client:
        hub = client.app.state.media_event_hub
        for revision in range(5, 71):
            service._state = replace(service.snapshot(), revision=revision, volume=revision % 101)
            hub._accept(service.snapshot())
        assert [state.revision for state in hub.initial(0)] == [service.snapshot().revision]

        async def latest_wins_and_cleanup():
            since = hub.replay[-1].revision
            stream = hub.stream(since, "device-a")
            pending = asyncio.create_task(anext(stream))
            await asyncio.sleep(0)
            service._state = replace(service.snapshot(), revision=since + 1, volume=72)
            hub._accept(service.snapshot())
            service._state = replace(service.snapshot(), revision=since + 2, volume=73)
            hub._accept(service.snapshot())
            first = await pending
            second = await anext(stream)
            service._state = replace(service.snapshot(), revision=since + 3, volume=74)
            hub._accept(service.snapshot())
            third = await anext(stream)
            await stream.aclose()
            return first, second, third

        frames = asyncio.run(latest_wins_and_cleanup())
        combined = "".join(frames)
        assert combined.count("id: 71\n") == 1
        assert combined.count("id: 72\n") == 1
        assert combined.count("id: 73\n") == 1
        assert hub.subscribers == {}


def test_revoke_stops_only_matching_subscriber_and_blocks_future_states() -> None:
    service = FakeMediaService()
    with TestClient(create_app(service)) as client:
        hub = client.app.state.media_event_hub

        async def scenario():
            current = service.snapshot().revision
            revoked = hub.stream(current, "device-a")
            other = hub.stream(current, "device-b")
            revoked_task = asyncio.create_task(anext(revoked))
            other_task = asyncio.create_task(anext(other))
            await asyncio.sleep(0)
            hub.revoke(DeviceRevoked("device-a"))
            revoked_frame = await revoked_task
            assert revoked_frame == "event: authorization_revoked\ndata: {}\n\n"
            late = hub.stream(current, "device-a")
            assert await anext(late) == "event: authorization_revoked\ndata: {}\n\n"
            await late.aclose()
            try:
                await anext(revoked)
            except StopAsyncIteration:
                pass
            else:
                raise AssertionError("已撤销流必须终止")
            service._state = replace(service.snapshot(), revision=current + 1, volume=74)
            hub._accept(service.snapshot())
            other_frame = await other_task
            await revoked.aclose()
            await other.aclose()
            return other_frame

        frame = asyncio.run(scenario())
        assert '"volume":74' in frame
        assert hub.subscribers == {}


def test_public_revoke_terminates_only_target_sse(tmp_path) -> None:
    service = FakeMediaService()
    store = DeviceStore(tmp_path / "devices.json")
    key_a = store.add_device("Android A")
    key_b = store.add_device("Android B")
    device_a = store.device_id_for_key(key_a)
    assert device_a is not None

    application = create_app(service, device_store=store)
    application.state.discovery_publisher.start = lambda: None
    application.state.discovery_publisher.close = lambda: None
    remote_headers = {
        "X-Forwarded-For": "192.168.1.10",
        "X-EzWinCommand-Protocol": "2",
    }


    with _run_uvicorn(application) as live_server:
        headers_b = {**remote_headers, "Authorization": f"Bearer {key_b}"}
        status, body = live_server.request("GET", "/api/devices", headers=headers_b)
        assert status == 200
        devices = json.loads(body)["devices"]
        assert next(device for device in devices if device["device_id"] == store.device_id_for_key(key_b))["is_current"]

        current = service.snapshot().revision
        headers_a = {**remote_headers, "Authorization": f"Bearer {key_a}", "Accept": "text/event-stream"}
        stream_a = live_server.open_connection()
        stream_a.request("GET", f"/api/media/events?since={current}", headers=headers_a)
        response_a = stream_a.getresponse()
        assert response_a.status == 200

        stream_b = live_server.open_connection()
        stream_b.request("GET", f"/api/media/events?since={current}", headers={**headers_b, "Accept": "text/event-stream"})
        response_b = stream_b.getresponse()
        assert response_b.status == 200

        status, body = live_server.request("DELETE", f"/api/devices/{device_a}", headers=headers_b)
        assert status == 200
        assert json.loads(body) == {"success": True}
        assert _read_sse_event(response_a) == ("authorization_revoked", {})
        service._publish(replace(service.snapshot(), volume=74))
        event, payload = _read_sse_event(response_b)
        assert event == "media"
        assert payload["revision"] == current + 1
        assert payload["volume"] == 74
        response_a.close()
        response_b.close()
        stream_a.close()
        stream_b.close()


def test_public_local_revoke_publishes_refetch_event(tmp_path) -> None:
    service = FakeMediaService()
    store = DeviceStore(tmp_path / "devices.json")
    key = store.add_device("Android")
    device_id = store.device_id_for_key(key)
    assert device_id is not None

    application = create_app(service, device_store=store)
    application.state.discovery_publisher.start = lambda: None
    application.state.discovery_publisher.close = lambda: None

    with _run_uvicorn(application) as live_server:
        stream = live_server.open_connection()
        stream.request("GET", "/api/local/events", headers={"Accept": "text/event-stream"})
        response = stream.getresponse()
        assert response.status == 200

        status, body = live_server.request(
            "DELETE",
            f"/api/devices/{device_id}",
            headers={"X-EzWinCommand-Protocol": "2"},
        )
        assert status == 200
        assert json.loads(body) == {"success": True}
        assert _read_sse_event(response) == ("changed", {"domains": ["devices"]})
        response.close()
        stream.close()
