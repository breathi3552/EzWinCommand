# REQ-003-04: 无窗口启动

- **父需求**: REQ-003
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

提供 `start-hidden.bat` 入口脚本，通过 `pythonw.exe` 启动 `app.py`，确保启动时不弹出控制台窗口。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `start-hidden.bat` | 新增 | 无窗口启动入口脚本 |

## 实现要点

### 脚本内容

```bat
@echo off
start "" pyw "%~dp0app.py"
```

- `@echo off`：不显示命令本身
- `start ""`：在新进程中启动，空标题
- `pyw`：系统注册的 `.pyw` 文件关联（调用 `pythonw.exe`）
- `"%~dp0app.py"`：脚本所在目录的 `app.py` 绝对路径

### 与开机自启动的配合

`startup.py` 中 `_get_command()` 直接使用 `pythonw.exe` 绝对路径启动 `app.py`，不依赖 `.bat` 脚本。`start-hidden.bat` 作为用户手动启动的便捷入口。

### 无窗口原理

`pythonw.exe` 是 Python Windows 安装自带的特殊解释器，编译为 Windows GUI 子系统（`/SUBSYSTEM:WINDOWS`），运行时不会创建控制台窗口。`.pyw` 扩展名在 Python 安装时关联到 `pythonw.exe`。
