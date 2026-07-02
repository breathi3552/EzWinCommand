# REQ-003-01: 防火墙自动配置

- **父需求**: REQ-003
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

在 Server 启动时自动检测并添加 Windows 防火墙入站规则，确保局域网设备可以访问 EzWinCommand 服务。通过 `subprocess` 调用 `netsh advfirewall` 命令，封装规则存在性检查和添加逻辑。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `agent/firewall.py` | 新增 | 防火墙自动配置模块 |
| `app.py` | 修改 | `main()` 中调用 `add_rule()` |

## 实现要点

### netsh 调用封装

`_run_netsh(args)` 为内部函数，封装 `subprocess.run(["netsh", "advfirewall", "firewall", *args])`：
- `capture_output=True`：捕获标准输出和错误
- `timeout=10`：防止命令挂起
- 返回 `(bool, str)`：成功标志和输出文本

### 编码处理

Windows 中文系统上 `netsh` 输出使用 mbcs（GBK）编码。使用 `bytes.decode("mbcs", errors="replace")` 解码：
- 优先 `mbcs`，失败回退 `utf-8`
- `errors="replace"` 防止异常字节导致 `UnicodeDecodeError`

### 规则检查

`rule_exists()` 通过 `netsh show rule name=...` 检查规则是否已存在，避免重复添加。

### 规则添加

`add_rule(port)` 创建入站 TCP 规则：
- 规则名称：`EzWinCommand 8080`
- 方向：`dir=in`
- 动作：`action=allow`
- 协议：`protocol=tcp`
- 端口：`localport={port}`

失败时输出友好提示，引导用户以管理员身份手动执行。

### 启动集成

`app.py` 的 `main()` 在启动 uvicorn 前调用 `add_rule(config.PORT)`，实现零配置防火墙打通。
