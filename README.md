# EzWinCommand

EzWinCommand 是一个运行在 Windows PC 上的本地控制台。PC 端启动 Agent 后，手机浏览器可通过局域网访问 Web UI，完成配对后控制 Windows 常用操作。

当前形态：**Windows Agent + 响应式 Web UI**。Android App 尚未实现。

## 功能

- PC 管理面板：生成配对码、管理设备、执行控制命令。
- 手机控制面板：输入 PC 显示的配对码后控制 Windows。
- 设备配对鉴权：4 位配对码、设备 Key、撤销/重命名设备。
- 插件化命令：当前内置计算器、媒体控制、音量控制。
- Windows 集成：系统托盘、静默启动、开机自启、防火墙规则同步。

## 快速开始

要求：Windows 10/11，Python 3.13。

```bat
cd EzWinCommand-server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

打开 PC 管理面板：

```text
http://localhost:8080
```

手机访问：

```text
http://<PC局域网IP>:8080
```

首次运行会自动创建本地配置文件：

```text
EzWinCommand-server/config.local.env
```

默认内容：

```env
HOST=0.0.0.0
PORT=8080
```

配置优先级：

```text
CLI 参数 > config.local.env > 默认值
```

临时改端口，不写回配置文件：

```bat
cd EzWinCommand-server
python app.py --port 9090
```

注意：如果把 `HOST` 改成 `127.0.0.1`，手机将无法访问；局域网访问应保持 `HOST=0.0.0.0`。

## 常用脚本

根目录提供几个双击脚本：

| 脚本 | 用途 |
|---|---|
| `run-admin.bat` | 管理员启动，保留控制台，适合排查防火墙/日志问题 |
| `run-admin_no_console.bat` | 管理员静默启动，不保留控制台 |
| `install-startup.bat` | 注册开机自启动 |
| `uninstall-startup.bat` | 注销开机自启动 |

服务目录内还有：

```text
EzWinCommand-server/start_daemon.pyw
```

双击后用 `pythonw.exe` 后台启动服务，不显示控制台窗口。

## 配对流程

1. PC 打开 `http://localhost:<PORT>`。
2. 点击“生成配对码”。配对码只在 localhost 管理面板显示。
3. 手机访问 `http://<PC局域网IP>:<PORT>`。
4. 输入 PC 显示的 4 位配对码和设备名。
5. 配对成功后，手机进入控制面板。

配对安全策略：

- 配对码：`0-9a-z`，4 位，5 分钟有效。
- 连续 5 次失败会锁定 30 秒。
- 非 localhost 页面不会回显真实配对码。
- 已配对设备保存在本机运行时文件 `EzWinCommand-server/agent/devices.json`，该文件不提交。

## 手机打不开时怎么查

优先检查以下项：

1. PC 本机是否可访问：
   ```text
   http://localhost:<PORT>/ping
   ```
   应返回：
   ```json
   {"status":"ok"}
   ```
2. 手机和 PC 是否在同一局域网。
3. `config.local.env` 中是否为：
   ```env
   HOST=0.0.0.0
   ```
4. Windows 防火墙是否允许当前端口。

防火墙规则名格式：

```text
EzWinCommand <PORT>
```

普通权限启动时，程序会尝试弹出 UAC 来同步防火墙规则。若你拒绝 UAC，手机端可能打不开。

可用管理员脚本启动一次：

```text
run-admin.bat
```

或静默管理员启动：

```text
run-admin_no_console.bat
```

手动检查规则：

```bat
netsh advfirewall firewall show rule name="EzWinCommand 9090"
```

手动添加规则：

```bat
netsh advfirewall firewall add rule name="EzWinCommand 9090" dir=in action=allow protocol=tcp localport=9090 profile=any enable=yes
```

把 `9090` 换成你的实际端口。

## API 概览

公开端点：

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/ping` | 健康检查 |
| `GET` | `/api/pairing-code` | 配对码状态；仅 localhost 响应包含真实 `code` |
| `POST` | `/api/authorize` | 提交配对码和设备名，获取设备 Key |
| `POST` | `/api/pairing-code/refresh` | 刷新配对码，仅 localhost 可用 |

鉴权端点：

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/status` | CPU / 内存状态快照 |
| `GET` | `/api/actions` | 列出可用插件操作 |
| `POST` | `/api/command` | 执行命令 |
| `GET` | `/api/devices` | 已配对设备列表 |
| `PATCH` | `/api/devices/{device_key}` | 重命名设备 |
| `DELETE` | `/api/devices/{device_key}` | 移除设备 |

命令示例：

```json
{
  "action": "player",
  "params": {
    "sub_action": "play_pause"
  }
}
```

## 项目结构

```text
.
├── EzWinCommand-server/
│   ├── app.py                 # Agent 入口
│   ├── config.py              # 本地配置加载
│   ├── start_daemon.pyw       # 静默启动器
│   ├── startup.py             # 开机自启管理
│   ├── agent/                 # API、鉴权、设备存储、分发、防火墙
│   ├── plugins/               # 插件系统与内置插件
│   └── web/                   # Web UI
├── install-startup.bat
├── uninstall-startup.bat
├── run-admin.bat
├── run-admin_no_console.bat
└── README.md
```

## 当前限制 / TODO

- [ ] HTTP 仅适合可信局域网；公网访问前需要 HTTPS 或隧道。
- [ ] 防火墙失败目前主要靠 UAC/日志提示，后续可在 Web UI 显示明确告警。
- [ ] `/api/status` 仍是 CPU / 内存快照，后续可改成插件状态聚合。
- [ ] 插件参数仍是自由字典，后续可引入参数 Schema。
- [ ] Android App 未实现，当前移动端入口是手机浏览器。
- [ ] 可增加更多插件：锁屏、睡眠、Steam、OBS、宏命令。

## 许可证

当前仓库未声明开源许可证。使用、分发或二次开发前，请先补充明确的 LICENSE。
