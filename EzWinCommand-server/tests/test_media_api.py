from __future__ import annotations

import asyncio

from dataclasses import replace
import http.client
import socket
import threading
import time

import uvicorn
from fastapi.testclient import TestClient
from app import create_app
from media.service import AudioEndpoint, MediaService, MediaState
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
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=0.5)
                try:
                    conn.request("GET", "/ping")
                    response = conn.getresponse()
                    body = response.read()
                finally:
                    conn.close()
                if response.status == 200:
                    assert body == b'{"status":"ok"}'
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("uvicorn listener did not become reachable")
    finally:
        server.should_exit = True
        gate.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
        service.stop(timeout=1)


def _remote_request(client: TestClient, method: str, url: str, **kwargs):
    transport = client._transport
    previous = getattr(transport, "client", None)
    transport.client = ("192.168.1.10", 54321)
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
        assert all(item["name"] not in {"player", "volume"} for item in actions)
        assert client.patch("/api/plugins/player", json={"enabled": True}).status_code == 404
        assert client.patch("/api/plugins/volume", json={"enabled": True}).status_code == 404

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
            revoked = hub.stream(current, "digest-a")
            other = hub.stream(current, "digest-b")
            revoked_task = asyncio.create_task(anext(revoked))
            other_task = asyncio.create_task(anext(other))
            await asyncio.sleep(0)
            hub.revoke("digest-a")
            try:
                await revoked_task
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
