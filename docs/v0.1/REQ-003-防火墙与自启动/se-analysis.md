# REQ-003 SE 分析

- **日期**: 2026-07-02
- **版本**: v0.1

## 自启动方案对比

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| 注册表 Run 键 (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`) | 实现简单，无需管理员权限，用户级注册 | 仅当前用户登录后启动，无法在登录前启动 | ✅ 选用 |
| 任务计划程序 (Task Scheduler) | 可配置登录前启动、延迟启动等高级选项 | 配置复杂，需要 schtasks 或 COM 接口 | ❌ 过度设计 |
| Windows Service | 系统级启动，登录前即可运行 | 需要管理员权限安装，无法直接访问用户桌面会话 | ❌ 不适合桌面 Agent 场景 |

**决策理由**：EzWinCommand 作为用户级 Agent，仅需在当前用户登录后启动。注册表 Run 键是最轻量的方案，`winreg` 标准库即可操作，无需额外依赖或权限。

## 无窗口方案对比

| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| `pythonw.exe` | Python 官方提供，直接启动 `.py` 文件无窗口 | 需要单独指定解释器路径 | ✅ 选用 |
| `.pyw` 扩展名 | 双击即可无窗口启动 | 需要修改文件扩展名，不直观 | ❌ 不推荐 |
| `.vbs` Wrapper | 传统 Windows 方案 | 增加一层脚本包装，维护成本高 | ❌ 不必要 |

**决策理由**：`pythonw.exe` 是 Python Windows 安装自带的无窗口解释器，与 `sys.executable` 配合可自动定位，无需额外脚本层。配合 bat 包装脚本提供便捷入口。

## CLI 参数方案

选用 Python 标准库 `argparse`：

- `--install`：注册开机自启动（互斥组）
- `--uninstall`：注销开机自启动（互斥组）
- 自动生成 `--help` 帮助信息
- 输入非法参数时有友好的错误提示

`--install` 和 `--uninstall` 放在 `add_mutually_exclusive_group()` 中，防止用户同时指定。

## 编码问题

`netsh advfirewall` 在中文 Windows 上输出使用系统 ANSI 代码页（GBK/mbcs），而 `subprocess.run(capture_output=True)` 返回 `bytes`。

解决方案：
- 显式使用 `bytes.decode("mbcs", errors="replace")` 解码
- `errors="replace"` 防止异常字节导致崩溃
- 备选 `utf-8` 解码以应对非中文系统

## 拆分需求

| 编号 | 标题 | 范围 |
|---|---|---|
| REQ-003-01 | 防火墙自动配置 | `agent/firewall.py`：netsh 调用、规则检查、错误处理 |
| REQ-003-02 | 开机自启动 | `startup.py`：注册表 Run 键读写 |
| REQ-003-03 | CLI 参数集成 | `app.py`：argparse 集成、--install/--uninstall |
| REQ-003-04 | 无窗口启动 | `start-hidden.bat`：pythonw.exe 包装脚本 |
