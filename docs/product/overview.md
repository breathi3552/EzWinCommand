# EzWinCommand 产品地图

EzWinCommand 面向可信局域网，把 Windows PC 的常用控制能力提供给 Web 管理端和 Android App。产品事实按模块维护；需求历史不替代当前产品定义。

## 模块

| 模块 | 主要职责 | 详细文档 |
|---|---|---|
| Server / 配对鉴权 | 本地管理、配对码、设备身份、请求鉴权与撤销 | [server/pairing-auth.md](server/pairing-auth.md) |
| Server / 命令与媒体 | 插件命令、异步任务、媒体状态与控制 | [server/command-media.md](server/command-media.md) |
| Android / 连接与控制 | 服务发现、地址连接、配对、会话保存和控制界面 | [android/connection-control.md](android/connection-control.md) |
| 跨端契约 | Android/Web 与 Server 之间的 HTTP、鉴权和状态协议 | [cross-platform/contracts.md](cross-platform/contracts.md) |
| Windows 集成 | 媒体/Core Audio、系统托盘、自启、防火墙和进程能力 | [windows/integration.md](windows/integration.md) |

## 产品级边界

- HTTP 仅面向 localhost 或可信局域网；公网使用不在当前安全模型内。
- 配对码只在 PC 本机管理端显示，远端客户端提交配对码但不读取真实值。
- 已配对设备使用设备密钥鉴权；密钥和本机运行状态不得进入仓库或测试证据。
- Android 是主要移动控制体验，Web 保留本机管理和浏览器控制能力。
- 真实 Windows 系统能力和跨设备网络可能需要 AI 环境测试或人工验证；未执行项明确标记为“待人工验证”。

## 维护规则

改变产品能力、用户行为、协议、安全边界或模块职责时更新对应模块文档，并同步 `docs/tests/coverage-map.md` 与当前版本日志。
