from __future__ import annotations

import ctypes
from pathlib import Path
from types import SimpleNamespace

from agent import display_power, display_protection
from agent.display_power import DisplayPowerController
from agent.display_protection import (
    INITIAL_PROTECTION_DELAY_SECONDS,
    REPROTECTION_DELAY_SECONDS,
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
        self._on_key_down = None

    def start(self, on_key_down) -> bool:
        self.start_count += 1
        self._on_key_down = on_key_down
        self.active = self.start_result
        return self.start_result

    def stop(self) -> bool:
        self.stop_count += 1
        self.active = False
        return True

    def emit_key_down(self) -> None:
        callback = self._on_key_down
        if callback is not None:
            callback()

    def emit_mouse(self) -> None:
        """鼠标 Raw Input 不应触发护屏取消。"""


class RetryingRawInputMonitor(FakeRawInputMonitor):
    def __init__(self, stop_results: list[bool]) -> None:
        super().__init__()
        self._stop_results = iter(stop_results)

    def stop(self) -> bool:
        super().stop()
        return next(self._stop_results)


class FakeDisplayPowerMonitor:
    def __init__(self, start_result: bool = True) -> None:
        self.start_result = start_result
        self.start_count = 0
        self.stop_count = 0
        self.active = False
        self._on_monitor_power_on = None

    def start(self, on_monitor_power_on) -> bool:
        self.start_count += 1
        self._on_monitor_power_on = on_monitor_power_on
        self.active = self.start_result
        return self.start_result

    def stop(self) -> bool:
        self.stop_count += 1
        self.active = False
        return True

    def emit_power_on(self) -> None:
        callback = self._on_monitor_power_on
        if callback is not None:
            callback()


class RetryingDisplayPowerMonitor(FakeDisplayPowerMonitor):
    def __init__(self, stop_results: list[bool]) -> None:
        super().__init__()
        self._stop_results = iter(stop_results)

    def stop(self) -> bool:
        super().stop()
        return next(self._stop_results)


class FakeCountdownWindow:
    def __init__(self, show_result: bool = True) -> None:
        self.show_result = show_result
        self.show_calls: list[int] = []
        self.hide_count = 0
        self.close_count = 0
        self._on_cancel = None

    def show(self, seconds: int, on_cancel) -> bool:
        self.show_calls.append(seconds)
        self._on_cancel = on_cancel
        return self.show_result

    def hide(self) -> None:
        self.hide_count += 1

    def close(self) -> None:
        self.close_count += 1
        self._on_cancel = None

    def emit_cancel(self) -> None:
        callback = self._on_cancel
        if callback is not None:
            callback()


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
    power_monitor: FakeDisplayPowerMonitor | None = None,
    countdown_window: FakeCountdownWindow | None = None,
    timers: FakeTimerFactory | None = None,
) -> tuple[
    DisplayProtectionController,
    StubPower,
    FakeRawInputMonitor,
    FakeDisplayPowerMonitor,
    FakeCountdownWindow,
    FakeTimerFactory,
]:
    power = power or StubPower()
    monitor = monitor or FakeRawInputMonitor()
    power_monitor = power_monitor or FakeDisplayPowerMonitor()
    countdown_window = countdown_window or FakeCountdownWindow()
    timers = timers or FakeTimerFactory()
    controller = DisplayProtectionController(
        power=power,
        input_monitor=monitor,
        power_monitor=power_monitor,
        countdown_window=countdown_window,
        timer_factory=timers,
    )
    return controller, power, monitor, power_monitor, countdown_window, timers

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


class FakeRawInputUser32:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def GetRawInputData(self, _handle, _command, data, size, _header_size):
        if data is None:
            size._obj.value = len(self.payload)
        else:
            size._obj.value = len(self.payload)
            ctypes.memmove(data, self.payload, len(self.payload))
        return len(self.payload)


def make_raw_input_packet(
    device_type: int,
    *,
    flags: int = 0,
    message: int = display_protection.WM_KEYDOWN,
) -> bytes:
    header = display_protection._RawInputHeader(
        device_type,
        0,
        None,
        0,
    )
    if device_type != display_protection.RIM_TYPEKEYBOARD:
        return bytes(header)
    keyboard = display_protection._RawKeyboard(
        30,
        flags,
        0,
        65,
        message,
        0,
    )
    header.dwSize = ctypes.sizeof(header) + ctypes.sizeof(keyboard)
    return bytes(header) + bytes(keyboard)


def test_raw_input_only_reports_first_keyboard_key_down() -> None:
    monitor = WindowsRawInputMonitor()
    events: list[str] = []
    monitor._on_key_down = lambda: events.append("key_down")
    key_down = make_raw_input_packet(display_protection.RIM_TYPEKEYBOARD)
    key_up = make_raw_input_packet(
        display_protection.RIM_TYPEKEYBOARD,
        flags=display_protection.RI_KEY_BREAK,
        message=0x0101,
    )

    monitor._handle_raw_input(FakeRawInputUser32(key_down), 1)
    monitor._handle_raw_input(FakeRawInputUser32(key_down), 1)
    monitor._handle_raw_input(FakeRawInputUser32(key_up), 1)
    monitor._handle_raw_input(FakeRawInputUser32(key_down), 1)
    monitor._handle_raw_input(
        FakeRawInputUser32(
            make_raw_input_packet(display_protection.RIM_TYPEMOUSE),
        ),
        1,
    )

    assert events == ["key_down", "key_down"]


def test_display_power_monitor_only_reports_monitor_power_on() -> None:
    monitor = display_protection.WindowsDisplayPowerMonitor()
    events: list[str] = []
    monitor._on_monitor_power_on = lambda: events.append("power_on")
    setting = display_protection._PowerBroadcastSetting()
    setting.PowerSetting = display_protection.GUID_MONITOR_POWER_ON
    setting.DataLength = 4

    setting.Data[0] = 0
    monitor._handle_power_setting_change(ctypes.addressof(setting))
    setting.Data[0] = 1
    monitor._handle_power_setting_change(ctypes.addressof(setting))

    assert events == ["power_on"]


def test_display_protection_starts_five_second_countdown_and_reprotects_after_wake() -> None:
    controller, power, monitor, power_monitor, window, timers = make_controller()

    assert controller.arm() is True
    initial_timer = timers.timers[0]
    assert initial_timer.interval == INITIAL_PROTECTION_DELAY_SECONDS
    assert initial_timer.started is True
    assert window.show_calls == [5]
    assert monitor.start_count == 1
    assert power_monitor.start_count == 1

    initial_timer.fire()
    initial_timer.fire_even_if_cancelled()
    assert power.calls == 1
    assert monitor.stop_count == 0
    assert power_monitor.stop_count == 0

    power_monitor.emit_power_on()
    reprotection_timer = timers.timers[1]
    assert reprotection_timer.interval == REPROTECTION_DELAY_SECONDS
    assert window.show_calls == [5, 60]
    reprotection_timer.fire()
    assert power.calls == 2

    power_monitor.emit_power_on()
    second_reprotection_timer = timers.timers[2]
    assert second_reprotection_timer.interval == REPROTECTION_DELAY_SECONDS
    second_reprotection_timer.fire()
    assert power.calls == 3

    controller.close()


def test_countdown_window_cancel_prevents_initial_power_off() -> None:
    controller, power, monitor, power_monitor, window, timers = make_controller()

    assert controller.arm() is True
    timer = timers.timers[0]
    window.emit_cancel()
    timer.fire_even_if_cancelled()

    assert timer.cancelled is True
    assert power.calls == 0
    assert monitor.stop_count == 1
    assert power_monitor.stop_count == 1
    controller.close()


def test_keyboard_key_down_cancels_initial_countdown() -> None:
    controller, power, monitor, power_monitor, window, timers = make_controller()

    assert controller.arm() is True
    monitor.emit_key_down()
    timers.timers[0].fire_even_if_cancelled()

    assert power.calls == 0
    assert monitor.stop_count == 1
    assert power_monitor.stop_count == 1
    assert window.hide_count >= 2
    controller.close()


def test_mouse_input_does_not_cancel_countdown() -> None:
    controller, power, monitor, power_monitor, _, timers = make_controller()

    assert controller.arm() is True
    monitor.emit_mouse()
    timers.timers[0].fire()

    assert power.calls == 1
    assert monitor.stop_count == 0
    assert power_monitor.stop_count == 0
    controller.close()


def test_keyboard_wake_key_cancels_without_reprotection_countdown() -> None:
    controller, power, monitor, power_monitor, _, timers = make_controller()

    assert controller.arm() is True
    timers.timers[0].fire()
    monitor.emit_key_down()
    power_monitor.emit_power_on()

    assert power.calls == 1
    assert len(timers.timers) == 1
    controller.close()


def test_mouse_wake_starts_reprotection_countdown() -> None:
    controller, power, monitor, power_monitor, _, timers = make_controller()

    assert controller.arm() is True
    timers.timers[0].fire()
    monitor.emit_mouse()
    power_monitor.emit_power_on()
    timers.timers[1].fire()

    assert power.calls == 2
    controller.close()


def test_duplicate_power_on_notifications_do_not_create_duplicate_timer() -> None:
    controller, power, _, power_monitor, _, timers = make_controller()

    assert controller.arm() is True
    timers.timers[0].fire()
    power_monitor.emit_power_on()
    power_monitor.emit_power_on()

    assert len(timers.timers) == 2
    timers.timers[1].fire()
    assert power.calls == 2
    controller.close()


def test_cancel_after_wake_blocks_future_reprotection_cycles() -> None:
    controller, power, monitor, power_monitor, window, timers = make_controller()

    assert controller.arm() is True
    timers.timers[0].fire()
    power_monitor.emit_power_on()
    window.emit_cancel()
    timers.timers[1].fire_even_if_cancelled()
    power_monitor.emit_power_on()

    assert power.calls == 1
    assert len(timers.timers) == 2
    assert monitor.stop_count == 1
    controller.close()


def test_timer_display_power_failure_stops_both_listeners(caplog) -> None:
    controller, power, monitor, power_monitor, _, timers = make_controller(
        power=StubPower(result=False),
    )

    assert controller.arm() is True
    with caplog.at_level("ERROR"):
        timers.timers[0].fire()

    assert power.calls == 1
    assert monitor.stop_count == 1
    assert power_monitor.stop_count == 1
    assert "OLED 护屏定时关闭显示器失败" in caplog.text
    controller.close()


def test_rearming_cancels_old_cycle_and_starts_new_initial_countdown() -> None:
    controller, power, monitor, power_monitor, window, timers = make_controller()

    assert controller.arm() is True
    old_timer = timers.timers[0]
    assert controller.arm() is True
    new_timer = timers.timers[1]

    old_timer.fire_even_if_cancelled()
    new_timer.fire()

    assert old_timer.cancelled is True
    assert monitor.start_count == 2
    assert power_monitor.start_count == 2
    assert monitor.stop_count == 1
    assert power_monitor.stop_count == 1
    assert window.show_calls == [5, 5]
    assert power.calls == 1
    controller.close()


def test_close_cleans_timer_monitors_and_window_without_display_change() -> None:
    controller, power, monitor, power_monitor, window, timers = make_controller()

    assert controller.arm() is True
    timer = timers.timers[0]
    controller.close()
    timer.fire_even_if_cancelled()

    assert timer.cancelled is True
    assert monitor.stop_count == 1
    assert power_monitor.stop_count == 1
    assert window.close_count == 1
    assert power.calls == 0


def test_close_retries_when_monitor_stop_reports_failure() -> None:
    monitor = RetryingRawInputMonitor([False, True])
    power_monitor = RetryingDisplayPowerMonitor([False, True])
    controller, _, _, _, _, _ = make_controller(
        monitor=monitor,
        power_monitor=power_monitor,
    )

    assert controller.arm() is True
    controller.close()
    controller.close()

    assert monitor.stop_count == 2
    assert power_monitor.stop_count == 2


def test_monitor_start_failure_returns_false_and_cleans_up(caplog) -> None:
    monitor = FakeRawInputMonitor(start_result=False)
    controller, power, _, power_monitor, _, timers = make_controller(monitor=monitor)

    with caplog.at_level("ERROR"):
        assert controller.arm() is False

    assert timers.timers == []
    assert monitor.stop_count == 1
    assert power_monitor.start_count == 0
    assert power.calls == 0


def test_power_monitor_start_failure_returns_false_and_stops_raw_input(caplog) -> None:
    power_monitor = FakeDisplayPowerMonitor(start_result=False)
    controller, power, monitor, _, _, timers = make_controller(
        power_monitor=power_monitor,
    )

    with caplog.at_level("ERROR"):
        assert controller.arm() is False

    assert timers.timers == []
    assert monitor.stop_count == 1
    assert power_monitor.stop_count == 1
    assert power.calls == 0


def test_oled_saver_plugin_exposes_one_action_and_starts_protection() -> None:
    protection = StubProtection()
    plugin = OledSaverPlugin(protection)

    assert plugin.get_metadata()["label"] == "OLED 护屏"
    assert plugin.get_sub_actions() == [{"id": "turn_off", "label": "进入护屏"}]
    assert plugin.execute({"sub_action": "turn_off"}).to_dict() == {
        "success": True,
        "message": "已启动护屏，5 秒后关闭显示器",
        "data": None,
    }
    assert plugin.execute({"sub_action": "turn_on"}).success is False

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
