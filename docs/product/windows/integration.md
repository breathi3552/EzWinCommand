# Windows 集成

## 特性与功能点

- `WIN-MEDIA-01`：读取和控制 Windows 系统媒体会话。
- `WIN-AUDIO-01`：读取和控制 Core Audio 音量与默认设备。
- `WIN-FW-01`：为当前监听端口同步防火墙规则，必要时通过 UAC 提权。
- `WIN-START-01`：安装和注销开机自启。
- `WIN-TRAY-01`：托盘入口、打开管理端和退出 Server。
- `WIN-ESPORTS-01`：异步执行电竞模式的音频、YY URI 和 Steam/CS2 链路。

## 验证边界

适配层可用单元测试和替身覆盖，但真实 Windows Media、Core Audio、UAC、防火墙、YY 和 Steam 结果必须由 AI 环境测试或人工验证证明。未执行时记录“待人工验证”。
