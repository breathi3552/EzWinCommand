# REQ-003-02: 开机自启动

- **父需求**: REQ-003
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

通过 Windows 注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 键注册 EzWinCommand Agent，实现用户登录后自动启动。使用 `winreg` 标准库操作注册表，无需管理员权限。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `startup.py` | 新增 | 开机自启动管理模块 |

## 实现要点

### 注册表路径

- 根键：`HKEY_CURRENT_USER`
- 子键：`Software\Microsoft\Windows\CurrentVersion\Run`
- 值名：`EzWinCommandAgent`
- 值类型：`REG_SZ`

### 启动命令行构建

`_get_command()` 使用 `sys.executable` 定位 `pythonw.exe`，并拼接 `app.py` 的绝对路径：

```text
"C:\...\pythonw.exe" "C:\...\app.py"
```

- `pythonw.exe` 位于 `sys.executable` 同级目录，无控制台窗口
- 使用绝对路径避免工作目录问题

### install()

1. 构建启动命令行
2. 打开 Run 键（`KEY_WRITE` 权限）
3. 调用 `SetValueEx()` 写入注册表值
4. 关闭键句柄

### uninstall()

1. 打开 Run 键（`KEY_SET_VALUE` 权限）
2. 调用 `DeleteValue()` 删除注册表值
3. 若值不存在（`FileNotFoundError`），静默跳过
4. 关闭键句柄

### is_installed()

检查当前是否已注册开机自启动，供外部查询状态使用。
