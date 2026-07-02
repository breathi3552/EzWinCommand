# REQ-001-05: 音量控制插件

- **父需求**: REQ-001
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

实现 `VolumePlugin`，通过模拟 Windows 键盘多媒体按键（音量加、音量减、静音）来控制系统音量。依赖 pywin32 提供的 ctypes 底层调用。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| EzWinCommand-server/plugins/volume.py | 新增 | 音量控制插件 |

## 实现要点

### VolumePlugin 类

- 路由键 `name = "volume"`，显示名 `label = "音量控制"`
- 子操作列表：
  ```python
  [
      {"id": "up",   "label": "+"},
      {"id": "down", "label": "-"},
      {"id": "mute", "label": "静音"},
  ]
  ```

### 多媒体按键模拟

通过 `ctypes.windll.user32.keybd_event()` 模拟按键：

| 操作 | VK 码 | 值 | 说明 |
|---|---|---|---|
| 静音 | `VK_VOLUME_MUTE` | 0xAD | 切换静音状态 |
| 音量减 | `VK_VOLUME_DOWN` | 0xAE | 降低音量 |
| 音量加 | `VK_VOLUME_UP` | 0xAF | 增大音量 |

每次按键需要两个 `keybd_event` 调用：
1. 按下：`keybd_event(vk_code, 0, 0, 0)` — 第四个参数为 0 表示 KEYEVENTF_KEYDOWN（默认）
2. 释放：`keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)` — 第四个参数为 `0x0002`

### execute(params) 流程

1. 从 `params` 中读取 `sub_action`，默认 `"up"`
2. 根据 `sub_action` 映射到对应 VK 码和 label
3. 调用 `_send_key(vk_code, label)` 执行按键模拟
4. 未知 `sub_action` 返回 `CommandResult(success=False, message="未知操作: {sub_action}")`

### 异常处理

- `_send_key` 内部 try/except 捕获 `ctypes` 调用异常
- 失败时返回 `CommandResult(success=False, message="音量控制失败: {exc}")`
