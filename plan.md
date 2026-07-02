# EzWinCommand 项目计划

## 项目目标

EzWinCommand 是一个用于 **通过移动端控制 Windows** 的个人自动化平台。

设计目标： - 手机一键控制 Windows - 响应速度快（局域网毫秒级） - Windows
后台占用低 - 可扩展插件 - API 与客户端解耦

------------------------------------------------------------------------

## 总体架构

``` text
Android App
        │
 HTTPS + Bearer Token
        │
        ▼
+----------------------+
| EzWinCommand Agent   |
| FastAPI              |
| Web UI               |
| REST API             |
+----------+-----------+
           |
     Command Dispatcher
           |
   +-------+--------+
   |                |
 Plugins      Windows API
   |                |
 Steam  Player  音量 锁屏 睡眠...
```

------------------------------------------------------------------------

## 组成

### Windows Agent

-   Python 3.13
-   FastAPI
-   Uvicorn
-   psutil
-   pywin32

职责： - 提供 REST API - 托管 Web UI - 命令分发 - 插件管理 - 状态采集

### Android App

首次配置： - Server URL - Bearer Token - 测试连接

功能： - 控制按钮 - 查看状态 - 后续支持桌面小组件、快捷方式

------------------------------------------------------------------------

## API

### GET /ping

健康检查

### GET /status

返回： - CPU - 内存 - 音量 - 当前播放器状态 - Steam/OBS 状态

### POST /api/command

``` json
{
  "action":"player"
}
```

------------------------------------------------------------------------

## Dispatcher

API 不直接执行命令。

流程：

API -\> Dispatcher -\> Plugin -\> Windows

新增插件无需修改 API。

------------------------------------------------------------------------

## 插件目录

``` text
plugins/
    calculator.py
    player.py
    steam.py
    obs.py
    volume.py
    macro.py
```

统一入口：

``` python
def execute(data):
    pass
```

------------------------------------------------------------------------

## Web UI

Agent 同时提供网页：

-   打开播放器
-   Steam
-   OBS
-   静音
-   音量
-   锁屏
-   睡眠

以及系统状态显示。

------------------------------------------------------------------------

## Android

优先开发原生 Android（Kotlin + Jetpack Compose）。

App 仅负责： - 保存服务器地址 - 保存 Token - 请求 API - 展示状态

业务逻辑全部保留在 PC。

------------------------------------------------------------------------

## 安全

第一阶段： - 仅局域网

第二阶段： - Bearer Token

第三阶段： - HTTPS - Tailscale / Cloudflare Tunnel（按需）

------------------------------------------------------------------------

## 部署

第一阶段： 直接运行：

``` bash
python app.py
```

后续： 注册为 Windows Service，实现开机自启动。

------------------------------------------------------------------------

## 开发路线

-   [ ] 建立 FastAPI 项目
-   [ ] GET /ping
-   [ ] POST /api/command
-   [ ] 打开计算器 Demo
-   [ ] Dispatcher
-   [ ] 插件系统
-   [ ] Web UI
-   [ ] Android App
-   [ ] 状态接口
-   [ ] Windows Service
-   [ ] HTTPS 与鉴权
-   [ ] 宏（Game Mode / Work Mode）
-   [ ] 插件生态

------------------------------------------------------------------------

## 项目命名

项目：EzWinCommand

模块： - EzWinCommand Agent - EzWinCommand Mobile - EzWinCommand API -
EzWinCommand Plugins

设计原则：

**PC 是大脑，Mobile 是遥控器。**
