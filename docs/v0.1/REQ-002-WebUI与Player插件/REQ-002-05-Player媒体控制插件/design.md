# REQ-002-05: Player 媒体控制插件

- **父需求**: REQ-002
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

新增 `player.py` 插件，通过 Windows `keybd_event` API 模拟多媒体键盘按键，实现播放/暂停、上一曲、下一曲三个媒体控制操作。架构上复用 volume 插件的 `ctypes.windll.user32.keybd_event` 模式。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `EzWinCommand-server/plugins/player.py` | 新增 | 52 行，PlayerPlugin 完整实现 |

## 实现要点

### 类结构

```python
class PlayerPlugin(BasePlugin):
    name = "player"
    label = "媒体控制"

    VK_MEDIA_PLAY_PAUSE = 0xB3
    VK_MEDIA_NEXT_TRACK  = 0xB0
    VK_MEDIA_PREV_TRACK  = 0xB1
    KEYEVENTF_KEYUP      = 0x0002
```

### 子操作声明

```python
def get_sub_actions(self) -> list[dict[str, str]]:
    return [
        {"id": "play_pause", "label": "播放/暂停"},
        {"id": "prev",       "label": "上一曲"},
        {"id": "next",       "label": "下一曲"},
    ]
```

三个子操作通过 `params.sub_action` 分派：`play_pause`、`prev`、`next`。默认值为 `play_pause`。

### execute 分派

```python
def execute(self, params: dict[str, Any]) -> CommandResult:
    sub_action = params.get("sub_action", "play_pause")

    mapping: dict[str, tuple[int, str]] = {
        "play_pause": (self.VK_MEDIA_PLAY_PAUSE, "播放/暂停"),
        "next":       (self.VK_MEDIA_NEXT_TRACK,  "下一曲"),
        "prev":       (self.VK_MEDIA_PREV_TRACK,  "上一曲"),
    }

    if sub_action not in mapping:
        return CommandResult(success=False, message=f"未知操作: {sub_action}")

    vk_code, label = mapping[sub_action]
    return self._send_key(vk_code, label)
```

使用 `dict` 映射 + 查表模式，避免冗长的 `if/elif` 链。

### keybd_event 发送

```python
@staticmethod
def _send_key(vk_code: int, label: str) -> CommandResult:
    try:
        import ctypes
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(
            vk_code, 0, PlayerPlugin.KEYEVENTF_KEYUP, 0
        )
        return CommandResult(success=True, message=label)
    except Exception as exc:
        return CommandResult(success=False, message=f"媒体控制失败: {exc}")
```

- `ctypes` 为延迟导入，仅在执行时加载，不影响插件加载阶段。
- 两次 `keybd_event` 调用模拟完整的按键按下+释放序列（按下 `dwFlags=0` → 释放 `dwFlags=KEYEVENTF_KEYUP`）。
- 与 volume 插件的 `_send_key` 结构完全一致，仅错误消息前缀不同。

### 虚拟键码对照

| 子操作 | 虚拟键码 | 常量 | 说明 |
|---|---|---|---|
| `play_pause` | `0xB3` | `VK_MEDIA_PLAY_PAUSE` | 播放/暂停切换 |
| `next` | `0xB0` | `VK_MEDIA_NEXT_TRACK` | 下一曲 |
| `prev` | `0xB1` | `VK_MEDIA_PREV_TRACK` | 上一曲 |

### 插件自动发现

`player.py` 放在 `plugins/` 目录下，由 `PluginLoader.discover()` 通过 `importlib` 扫描并注册。`name = "player"` 即为路由标识符，前端通过 `POST /api/command` 发送 `{"action": "player", "params": {"sub_action": "play_pause"}}` 即可调用。
