# EzWinCommand

EzWinCommand 是一个运行在 Windows PC 上的本地控制台。PC 端启动 Server 后，手机浏览器可通过局域网访问 Web UI，完成配对后控制 Windows 常用操作。

当前形态：**Windows Server + 响应式 Web UI + Android App**。Android App 已支持通过局域网连接现有 Windows Server，并提供完整媒体与音频控制卡。

## 功能

- PC 管理面板：生成配对码、管理设备、执行控制命令。
- 手机控制面板：输入 PC 显示的配对码后控制 Windows。
- Android App：在同一局域网内输入 PC 地址并完成配对，随后通过完整媒体卡查看封面、歌曲、艺术家和播放状态，控制上一首/播放暂停/下一首、主音量及默认输入/输出设备。
- 设备配对鉴权：4 位配对码、设备 Key、撤销/重命名设备。
- 插件化命令：当前内置计算器，以及合并后的媒体与音频控制。
- Windows 集成：系统托盘、静默启动、开机自启、防火墙规则同步。

## 快速开始

要求：Windows 10/11，Python 3.13。

首次使用先安装依赖：

```bat
cd EzWinCommand-server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

媒体与音频控制固定依赖 `winrt-Windows.Media.Control[all]==3.2.1` 和 `pycaw==20251023`，均由 `requirements.txt` 安装；无需手动安装未声明依赖。

推荐从仓库根目录双击脚本启动：

| 脚本 | 用途 |
|---|---|
| `run-admin.bat` | 管理员启动，保留控制台，适合首次运行和排查防火墙/日志问题 |
| `run-admin_no_console.bat` | 管理员静默启动，不保留控制台，适合日常使用 |
| `install-startup.bat` | 注册开机自启动 |
| `uninstall-startup.bat` | 注销开机自启动 |

也可以在服务目录手动启动：

```bat
cd EzWinCommand-server
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

Android App 连接地址同样使用：

```text
http://<PC局域网IP>:<PORT>
```

这里的 `<PC局域网IP>` 必须是 PC 在当前局域网中的实际 IP，例如 `192.168.1.10`；Android 里的 `localhost` 只代表手机自己，不是 PC。

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

注意：如果把 `HOST` 改成 `127.0.0.1`，手机和 Android App 都将无法访问；局域网访问应保持 `HOST=0.0.0.0`。

## 电竞模式配置

在 `EzWinCommand-server/config.local.env` 中配置以下键：

| 配置键 | 用途 |
|---|---|
| `YY_ROOM_ID` | YY 目标房间号，仅允许纯数字，例如 `1450342043` |
| `STEAM_PATH` | Steam 可执行文件路径 |
| `AUDIO_ENTER_DEVICE` | 进入电竞模式时使用的音频设备名称 |
| `AUDIO_EXIT_DEVICE` | 退出电竞模式时恢复的音频设备名称 |

系统需要注册 `yy://` 协议。进入电竞模式时依次切换进入音频设备、构造并提交精确的 `yy://join` URI，等待 YY 进程就绪（短暂调度延迟）后启动 Steam/CS2。Steam 随 URI 已提交启动，不以每次进房确认作为启动门禁；YY 登录或验证码仍由用户人工完成，最终房间状态以 YY 页面观察为准。

已验证的真实 Manual：房间 `1450342043` 在 YY 未运行时启动新进程（PID `23852`），用户确认已成功进入房间。该记录证明本次受控流程，不代表每次进入都无需用户确认。

电竞模式属于长任务：手机/浏览器点击后服务端立即受理（HTTP 202），客户端轮询执行结果，而不是在单次短超时请求里等完整流程结束。若提示“仍在服务端执行”，可稍后在同一客户端继续查询；最终是否进房仍以 YY 页面为准。

`AUDIO_ENTER_DEVICE` 和 `AUDIO_EXIT_DEVICE` 必须逐字匹配 Windows“声音设置”中显示的设备名称。修改配置后请重启 Server，配置才会加载。电竞模式仅建议在可信的 Windows 本机或可信局域网中使用。

旧版 YY UI 搜索框、坐标输入与窗口自动化方案已废弃，当前实现无 fallback。

## Android App 局域网连接

1. 在 PC 端打开 `http://localhost:<PORT>`。
2. 点击“生成配对码”。配对码只在 PC 管理面板显示，Android App 不会从服务端读取真实配对码。
3. 在 Android App 中输入 `http://<PC局域网IP>:<PORT>`，例如 `http://192.168.1.10:8080`。
4. 在 Android App 中输入 PC 显示的 4 位配对码和设备名。
5. 配对成功后，Android App 会保存设备 Key，后续操作自动带上授权。

### Android 媒体卡

Android 控制页提供完整媒体卡：显示 Windows 当前系统媒体会话的封面、歌曲、艺术家与播放状态，并可控制上一首、播放/暂停、下一首、主音量及默认输入/输出设备。没有活动媒体时，音量与设备控件仍可使用。

自动化测试与 Android Debug 构建已通过；Windows 真实播放器/Core Audio、Android 真机网络恢复、视觉与 TalkBack 验证状态为 **Manual pending**。

失败排查顺序：

1. 先确认 PC 本机能访问 `http://localhost:<PORT>/ping`，并返回 `{"status":"ok"}`。
2. 确认手机/Android App 与 PC 在同一局域网，且输入的是 PC 局域网 IP，不是 `localhost`、`127.0.0.1` 或别名主机名。
3. 确认 `config.local.env` 或启动参数中保持 `HOST=0.0.0.0`。
4. 确认端口正确，`/ping` 能访问，且 Windows 防火墙已放行当前端口。

防火墙 / UAC / netsh 兜底：

- 普通权限启动时，程序会尝试弹出 UAC 同步防火墙规则。若弹窗出现，请允许。
- 如果你更习惯保留控制台，可使用 `run-admin.bat`；日常静默运行可用 `run-admin_no_console.bat`。
- 如果普通权限路径仍然失败，以管理员身份执行 `netsh` 手动放行端口，例如：

```bat
netsh advfirewall firewall add rule name="EzWinCommand 8080" dir=in action=allow protocol=tcp localport=8080 profile=any enable=yes
```

把 `8080` 换成你的实际端口。

## 静默启动

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
- 已配对设备保存在本机运行时文件 `EzWinCommand-server/agent/devices.json`。

## 手机无法访问时

先确认：

1. PC 本机可访问 `http://localhost:<PORT>/ping`，并返回 `{"status":"ok"}`。
2. 手机和 PC 在同一局域网。
3. `config.local.env` 中保持 `HOST=0.0.0.0`。
4. 防火墙已放行当前端口。

普通权限启动时，程序会尝试弹出 UAC 同步防火墙规则。若手机仍打不开，可双击根目录脚本：

```text
run-admin.bat
run-admin_no_console.bat
```

仍不行时，以管理员身份手动放行端口：

```bat
netsh advfirewall firewall add rule name="EzWinCommand 9090" dir=in action=allow protocol=tcp localport=9090 profile=any enable=yes
```

把 `9090` 换成你的实际端口。

## 项目结构

```text
.
├── EzWinCommand-server/
│   ├── app.py                 # Server 入口
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
- [x] `/api/status` 已移除（CPU/内存快照不再轮询），`psutil` 保留供 calculator 插件使用。
- [x] WebView 插件布局已调优：共享渲染函数、mobile-first grid、兼容新旧插件字段。
- [ ] 插件参数仍是自由字典，后续可引入参数 Schema。
- [x] Android App 已支持局域网连接和完整媒体卡；手机浏览器入口仍可继续使用。
- [ ] 未来将 Web 收敛为管理后台入口；完整媒体控制体验以 Android App 为主。

- [x] 电竞等长任务改为异步受理 + 状态轮询（`202` + `/api/commands/{id}`）；完整真机手测仍建议用户在可信局域网自行确认。
- [ ] 可增加更多插件：锁屏、睡眠、Steam、OBS、宏命令。

## 许可证

本项目使用 MIT License。详见 `LICENSE`。