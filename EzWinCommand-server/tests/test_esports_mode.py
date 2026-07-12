from types import SimpleNamespace
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from plugins import esports_mode


def test_build_yy_join_uri_exact():
    assert esports_mode._build_yy_join_uri("1450342043") == "yy://join:room_id=1450342043&sub_room_id=1450342043/"


@pytest.mark.parametrize("room_id", ["", " ", "abc", "1.2", "-1", None, 123])
def test_build_yy_join_uri_rejects_non_digits(room_id):
    with pytest.raises(ValueError):
        esports_mode._build_yy_join_uri(room_id)


def test_submit_uses_startfile_and_waits(monkeypatch):
    events = []
    monkeypatch.setattr(esports_mode.os, "startfile", lambda uri: events.append(("startfile", uri)))
    monkeypatch.setattr(esports_mode, "_wait_for_yy_ready", lambda: events.append("ready") or True)
    monkeypatch.setattr(esports_mode.time, "sleep", lambda seconds: events.append(("sleep", seconds)))
    ok, message = esports_mode._submit_yy_join_uri("123")
    assert (ok, message) == (True, "YY已发起进房")
    assert events == [("startfile", "yy://join:room_id=123&sub_room_id=123/"), "ready", ("sleep", 0.3)]


def test_startfile_exception_blocks(monkeypatch):
    monkeypatch.setattr(esports_mode.os, "startfile", lambda _: (_ for _ in ()).throw(OSError("no association")))
    wait = lambda: pytest.fail("等待不应发生")
    monkeypatch.setattr(esports_mode, "_wait_for_yy_ready", wait)
    ok, message = esports_mode._submit_yy_join_uri("123")
    assert not ok and "YY 启动失败" in message


def test_window_timeout_blocks(monkeypatch):
    events = []
    monkeypatch.setattr(esports_mode.os, "startfile", lambda uri: events.append(uri))
    monkeypatch.setattr(esports_mode, "_wait_for_yy_ready", lambda: False)
    ok, message = esports_mode._submit_yy_join_uri("123")
    assert not ok and "超时" in message
    assert events


def test_enter_order_message_and_steam(monkeypatch):
    events = []
    monkeypatch.setattr(config, "YY_ROOM_ID", "123")
    monkeypatch.setattr(config, "STEAM_PATH", "steam.exe")
    monkeypatch.setattr(esports_mode, "_set_default_audio_device", lambda _: events.append("audio") or (True, "ok"))
    monkeypatch.setattr(esports_mode, "_submit_yy_join_uri", lambda r: events.append("yy") or (True, "YY已发起进房"))
    monkeypatch.setattr(esports_mode.subprocess, "Popen", lambda argv: events.append(("steam", argv)))
    result = esports_mode.EsportsModePlugin().execute({})
    assert result.success
    assert "YY已发起进房" in result.message
    assert events == ["audio", "yy", ("steam", ["steam.exe", "-applaunch", "730", "-perfectworld"])]


def test_enter_yy_failure_blocks_steam(monkeypatch):
    events = []
    monkeypatch.setattr(config, "YY_ROOM_ID", "123")
    monkeypatch.setattr(config, "STEAM_PATH", "steam.exe")
    monkeypatch.setattr(esports_mode, "_set_default_audio_device", lambda _: (True, "ok"))
    monkeypatch.setattr(esports_mode, "_submit_yy_join_uri", lambda r: (False, "YY 进程启动超时"))
    monkeypatch.setattr(esports_mode.subprocess, "Popen", lambda argv: events.append(argv))
    result = esports_mode.EsportsModePlugin().execute({})
    assert not result.success and "YY" in result.message
    assert not events


def test_exit_closes_yy_cs2_not_steam(monkeypatch):
    calls = []
    monkeypatch.setattr(esports_mode.EsportsModePlugin, "_close_names", lambda names: calls.append(names) or 0)
    monkeypatch.setattr(esports_mode, "_set_default_audio_device", lambda _: (True, "ok"))
    result = esports_mode.EsportsModePlugin().execute({"sub_action": "exit"})
    assert result.success
    assert {"cs2.exe"} in calls and {"yy.exe"} in calls
    assert all("steam.exe" not in names for names in calls)


def test_no_desktop_input_apis():
    source = Path(esports_mode.__file__).read_text(encoding="utf-8")
    for forbidden in ("SetForegroundWindow", "GetForegroundWindow", "SetCursorPos", "mouse_event", "keybd_event", "AttachThreadInput"):
        assert forbidden not in source
