from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path

from agent.dispatcher import Dispatcher
from media.service import AudioEndpoint, MediaState
from plugins.base import CommandResult
from plugins.loader import PluginLoader
from plugins.media import MediaPlugin


class StubService:
    def __init__(self) -> None:
        self.calls = []
        self.state = MediaState(
            render_devices=(AudioEndpoint("out", "Output"),),
            capture_devices=(AudioEndpoint("in", "Input"),),
        )

    def submit(self, sub_action, *, volume=None, endpoint_id=None):
        self.calls.append((sub_action, volume, endpoint_id))
        future = Future()
        future.set_result(CommandResult(True, "ok"))
        return future

    def snapshot(self):
        return self.state


def test_media_plugin_exposes_three_actions_and_executes_six_commands() -> None:
    service = StubService()
    plugin = MediaPlugin(service)
    assert [item["id"] for item in plugin.get_sub_actions()] == ["play_pause", "prev", "next"]
    commands = [
        ("play_pause", {}), ("prev", {}), ("next", {}),
        ("set_volume", {"volume": 37}),
        ("set_output_device", {"endpoint_id": "out"}),
        ("set_input_device", {"endpoint_id": "in"}),
    ]
    for name, extra in commands:
        assert plugin.execute({"sub_action": name, **extra}).success is True
    assert [call[0] for call in service.calls] == [item[0] for item in commands]


def test_loader_excludes_media_before_import_and_explicit_register_preserves_enabled(tmp_path: Path, monkeypatch) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "media.py").write_text("raise AssertionError('must not import')", encoding="utf-8")
    loader = PluginLoader(enabled={"media": False})
    loader.discover(plugin_dir, package="unused", exclude={"media"})
    plugin = MediaPlugin(StubService())
    loader.register(plugin)
    assert loader.get("media") is plugin
    assert loader.is_enabled("media") is False
    assert loader.errors == []


def test_dispatcher_clean_cutover_has_one_media_and_no_legacy(tmp_path: Path) -> None:
    config = tmp_path / "plugins.json"
    config.write_text('{"version":1,"plugins":{"media":{"enabled":true}}}', encoding="utf-8")
    dispatcher = Dispatcher(config)
    dispatcher.discover_plugins(Path(__file__).parents[1] / "plugins", exclude={"media"})
    dispatcher.register_plugin(MediaPlugin(StubService()))
    names = [item["name"] for item in dispatcher.list_plugins()]
    assert names.count("media") == 1
    assert all(name not in names for name in {"calculator", "player", "volume"})
    media = next(item for item in dispatcher.list_actions() if item["name"] == "media")
    assert [item["id"] for item in media["sub_actions"]] == ["play_pause", "prev", "next"]
    assert dispatcher.execute("player", {}).success is False
    assert dispatcher.execute("volume", {}).success is False
    assert dispatcher.execute("calculator", {}).success is False
