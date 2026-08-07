from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent import display_power, display_protection
from agent.display_power import DisplayPowerController
from agent.display_protection import (
    DISPLAY_PROTECTION_DELAY_SECONDS,
    DisplayProtectionController,
    WindowsRawInputMonitor,
)
from agent.dispatcher import Dispatcher
from plugins.loader import PluginLoader
from plugins.oled_saver import OledSaverPlugin


class StubPower:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls = 0

    def turn_off(self) -> bool:
        self.calls += 1
        return self.result


class FakeTimer:
    def __init__(self, interval: float, callback) -> None:
        self.interval = interval
        self.callback = callback
        self.started = False
        self.cancelled = False

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self.callback()

    def fire_even_if_cancelled(self) -> None:
        self.callback()


class FakeTimerFactory:
    def __init__(self) -> None:
        self.timers: list[FakeTimer] = []

    def __call__(self, interval: float, callback) -> FakeTimer:
        timer = FakeTimer(interval, callback)
        self.timers.append(timer)
        return timer


class FakeRawInputMonitor:
    def __init__(self, start_result: bool = True) -> None:
        self.start_result = start_result
        self.start_count = 0
        self.stop_count = 0
        self.active = False
        self._on_input = None

    def start(self, on_input) -> bool:
        self.start_count += 1
        self._on_input = on_input
        self.active = self.start_result
        return self.start_result

    def stop(self) -> bool:
        self.stop_count += 1
        self.active = False
        return True

    def emit_input(self) -> None:
        callback = self._on_input
        if callback is not None:
            callback()


class RetryingRawInputMonitor(FakeRawInputMonitor):
    def __init__(self, stop_results: list[bool]) -> None:
        super().__init__()
        self._stop_results = iter(stop_results)

    def stop(self) -> bool:
        super().stop()
        return next(self._stop_results)


class StubProtection:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.arm_count = 0
        self.close_count = 0

    def arm(self) -> bool:
        self.arm_count += 1
        return self.result

    def close(self) -> None:
        self.close_count += 1


def make_controller(
    *,
    power: StubPower | None = None,
    monitor: FakeRawInputMonitor | None = None,
    timers: FakeTimerFactory | None = None,
) -> tuple[DisplayProtectionController, StubPower, FakeRawInputMonitor, FakeTimerFactory]:
    power = power or StubPower()
    monitor = monitor or FakeRawInputMonitor()
    timers = timers or FakeTimerFactory()
    controller = DisplayProtectionController(
        power=power,
        input_monitor=monitor,
        timer_factory=timers,
    )
    return controller, power, monitor, timers


def test_display_power_controller_maps_off_to_win32_power_value() -> None:
    power_states: list[int] = []
    controller = DisplayPowerController(lambda power_state: power_states.append(power_state) or True)

    assert controller.turn_off() is True
    assert power_states == [display_power.MONITOR_POWER_OFF]


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


def test_raw_input_devices_cover_keyboard_and_mouse() -> None:
    devices = display_protection.WindowsRawInputMonitor._raw_input_devices(None)

    assert [(device.usUsagePage, device.usUsage) for device in devices] == [(0x01, 0x06), (0x01, 0x02)]
    assert [device.dwFlags for device in devices] == [
        display_protection.RIDEV_INPUTSINK,
        display_protection.RIDEV_INPUTSINK,
    ]


def test_raw_input_window_proc_calls_def_window_proc_for_cleanup() -> None:
    monitor = WindowsRawInputMonitor()
    handled: list[tuple[object, int]] = []
    monitor._handle_raw_input = lambda user32, handle: handled.append((user32, handle))
    cleanup_calls: list[tuple[object, int, int, int]] = []
    user32 = SimpleNamespace(
        DefWindowProcW=lambda *args: cleanup_calls.append(args) or 17,
    )

    assert monitor._window_proc(user32, 1, display_protection.WM_INPUT, 2, 3) == 17
    assert handled == [(user32, 3)]
    assert cleanup_calls == [(1, display_protection.WM_INPUT, 2, 3)]

def test_raw_input_monitor_does_not_start_on_non_windows(monkeypatch, caplog) -> None:
    monkeypatch.setattr(display_protection.os, "name", "posix")
    monitor = WindowsRawInputMonitor()

    with caplog.at_level("ERROR"):
        assert monitor.start(lambda: None) is False
    assert "Raw Input 监听失败" in caplog.text


def test_display_protection_arms_one_60_second_timer_and_turns_off_once() -> None:
    controller, power, monitor, timers = make_controller()

    assert controller.arm() is True
    timer = timers.timers[0]
    assert timer.interval == DISPLAY_PROTECTION_DELAY_SECONDS
    assert timer.started is True
    assert monitor.start_count == 1

    timer.fire()
    timer.fire_even_if_cancelled()

    assert power.calls == 1
    assert monitor.stop_count == 0

    controller.close()


def test_raw_input_before_deadline_cancels_timer_without_turning_off() -> None:
    controller, power, monitor, timers = make_controller()

    assert controller.arm() is True
    timer = timers.timers[0]
    monitor.emit_input()
    timer.fire_even_if_cancelled()

    assert timer.cancelled is True
    assert power.calls == 0
    assert monitor.stop_count == 1

    controller.close()


def test_raw_input_after_display_off_stops_listener_without_second_turn_off() -> None:
    controller, power, monitor, timers = make_controller()

    assert controller.arm() is True
    timer = timers.timers[0]
    timer.fire()
    assert power.calls == 1
    assert monitor.stop_count == 0

    monitor.emit_input()
    timer.fire_even_if_cancelled()

    assert power.calls == 1
    assert monitor.stop_count == 1

    controller.close()

def test_timer_display_power_failure_logs_and_stops_listener(caplog) -> None:
    controller, power, monitor, timers = make_controller(power=StubPower(result=False))

    assert controller.arm() is True
    with caplog.at_level("ERROR"):
        timers.timers[0].fire()

    assert power.calls == 1
    assert monitor.stop_count == 1
    assert "OLED 护屏定时关闭显示器失败" in caplog.text

    controller.close()


def test_rearming_cancels_old_timer_and_does_not_duplicate_turn_off() -> None:
    controller, power, monitor, timers = make_controller()

    assert controller.arm() is True
    old_timer = timers.timers[0]
    assert controller.arm() is True
    new_timer = timers.timers[1]

    old_timer.fire_even_if_cancelled()
    new_timer.fire()

    assert old_timer.cancelled is True
    assert monitor.start_count == 2
    assert monitor.stop_count == 1
    assert power.calls == 1

    controller.close()


def test_close_cancels_timer_and_stops_monitor_without_display_change() -> None:
    controller, power, monitor, timers = make_controller()

    assert controller.arm() is True
    timer = timers.timers[0]
    controller.close()
    timer.fire_even_if_cancelled()

    assert timer.cancelled is True
    assert monitor.stop_count == 1
    assert power.calls == 0


def test_close_retries_when_monitor_stop_reports_failure() -> None:
    monitor = RetryingRawInputMonitor([False, True])
    controller, _, _, _ = make_controller(monitor=monitor)

    assert controller.arm() is True
    controller.close()
    controller.close()

    assert monitor.stop_count == 2


def test_monitor_start_failure_returns_false_and_cleans_up(caplog) -> None:
    monitor = FakeRawInputMonitor(start_result=False)
    controller, power, _, timers = make_controller(monitor=monitor)

    with caplog.at_level("ERROR"):
        assert controller.arm() is False

    assert timers.timers == []
    assert monitor.stop_count == 1
    assert power.calls == 0


def test_oled_saver_plugin_exposes_one_action_and_starts_protection() -> None:
    protection = StubProtection()
    plugin = OledSaverPlugin(protection)

    assert plugin.get_metadata()["label"] == "OLED 护屏"
    assert plugin.get_sub_actions() == [{"id": "turn_off", "label": "进入护屏"}]
    assert plugin.execute({"sub_action": "turn_off"}).to_dict() == {
        "success": True,
        "message": "已启动护屏，60 秒后关闭显示器",
        "data": None,
    }
    assert plugin.execute({"sub_action": "turn_on"}).success is False
    assert protection.arm_count == 1

    plugin.close()
    assert protection.close_count == 1


def test_oled_saver_plugin_logs_and_returns_failure_when_listener_fails(caplog) -> None:
    plugin = OledSaverPlugin(StubProtection(result=False))

    with caplog.at_level("ERROR"):
        result = plugin.execute({"sub_action": "turn_off"})

    assert result.success is False
    assert result.message == "护屏操作失败"
    assert "OLED 护屏启动失败" in caplog.text


def test_loader_discovers_oled_saver_plugin() -> None:
    loader = PluginLoader()
    loader.discover(Path(__file__).parents[1] / "plugins", exclude={"media", "esports_mode"})

    plugin = loader.get("oled_saver")
    assert plugin is not None
    assert [item["id"] for item in plugin.get_sub_actions()] == ["turn_off"]


def test_dispatcher_exposes_oled_saver_action(tmp_path: Path) -> None:
    dispatcher = Dispatcher(tmp_path / "plugins.json")
    dispatcher.discover_plugins(Path(__file__).parents[1] / "plugins", exclude={"media", "esports_mode"})

    action = next(item for item in dispatcher.list_actions() if item["name"] == "oled_saver")
    assert action["label"] == "OLED 护屏"
    assert [item["id"] for item in action["sub_actions"]] == ["turn_off"]
    dispatcher.close()
