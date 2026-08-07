from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent import display_power
from agent.display_power import DisplayPowerController
from agent.dispatcher import Dispatcher
from plugins.oled_saver import OledSaverPlugin
from plugins.loader import PluginLoader


class StubController:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls: list[str] = []

    def turn_off(self) -> bool:
        self.calls.append("turn_off")
        return self.result

    def turn_on(self) -> bool:
        self.calls.append("turn_on")
        return self.result


def test_display_power_controller_maps_off_and_on_to_win32_power_values() -> None:
    power_states: list[int] = []
    controller = DisplayPowerController(lambda power_state: power_states.append(power_state) or True)

    assert controller.turn_off() is True
    assert controller.turn_on() is True
    assert power_states == [2, -1]


def test_send_monitor_power_message_uses_broadcast_system_message(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(display_power.os, "name", "nt")

    def send_message(*args):
        calls.append(args)
        return 1

    monkeypatch.setattr(
        display_power.ctypes,
        "WinDLL",
        lambda *args, **kwargs: SimpleNamespace(SendMessageTimeoutW=send_message),
    )

    assert display_power._send_monitor_power_message(2, timeout_ms=321) is True
    assert calls[0][:6] == (
        display_power.HWND_BROADCAST,
        display_power.WM_SYSCOMMAND,
        display_power.SC_MONITORPOWER,
        2,
        display_power.SMTO_ABORTIFHUNG,
        321,
    )

def test_send_monitor_power_message_returns_failure_and_logs(monkeypatch, caplog) -> None:
    def send_message(*args):
        return 0

    monkeypatch.setattr(display_power.os, "name", "nt")
    monkeypatch.setattr(
        display_power.ctypes,
        "WinDLL",
        lambda *args, **kwargs: SimpleNamespace(SendMessageTimeoutW=send_message),
    )

    with caplog.at_level("ERROR"):
        assert display_power._send_monitor_power_message(2) is False
    assert "发送显示器电源消息失败" in caplog.text


def test_oled_saver_plugin_exposes_two_actions_and_dispatches_them() -> None:
    controller = StubController()
    plugin = OledSaverPlugin(controller)

    assert plugin.get_metadata()["label"] == "OLED 护屏"
    assert [item["id"] for item in plugin.get_sub_actions()] == ["turn_off", "turn_on"]
    assert plugin.execute({"sub_action": "turn_off"}).to_dict() == {
        "success": True,
        "message": "已进入护屏",
        "data": None,
    }
    assert plugin.execute({"sub_action": "turn_on"}).message == "已恢复显示"
    assert controller.calls == ["turn_off", "turn_on"]


def test_oled_saver_plugin_logs_and_returns_failure_when_windows_call_fails(caplog) -> None:
    plugin = OledSaverPlugin(StubController(result=False))

    with caplog.at_level("ERROR"):
        result = plugin.execute({"sub_action": "turn_off"})

    assert result.success is False
    assert result.message == "护屏操作失败"
    assert "OLED 护屏操作失败" in caplog.text


def test_loader_discovers_oled_saver_plugin() -> None:
    loader = PluginLoader()
    loader.discover(Path(__file__).parents[1] / "plugins", exclude={"media", "esports_mode"})

    plugin = loader.get("oled_saver")
    assert plugin is not None
    assert [item["id"] for item in plugin.get_sub_actions()] == ["turn_off", "turn_on"]


def test_dispatcher_exposes_oled_saver_action(tmp_path: Path) -> None:
    dispatcher = Dispatcher(tmp_path / "plugins.json")
    dispatcher.discover_plugins(Path(__file__).parents[1] / "plugins", exclude={"media", "esports_mode"})

    action = next(item for item in dispatcher.list_actions() if item["name"] == "oled_saver")
    assert action["label"] == "OLED 护屏"
    assert [item["id"] for item in action["sub_actions"]] == ["turn_off", "turn_on"]
