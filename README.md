# EzWinCommand

EzWinCommand 是一个面向 Windows 的本地自动化控制台：在 PC 上运行 Agent，在手机浏览器中打开 Web UI，即可通过局域网控制 Windows 的常用操作。

当前仓库以 **Windows Agent + 响应式 Web UI** 为主；Android 客户端仍在规划中。

## 功能状态

- FastAPI Agent：提供 REST API、托管 Web UI、分发控制命令。
- Web UI 双模式：
  - `localhost` 访问时显示 PC 管理面板，可生成配对码、管理设备、直接控制 PC。
  - 局域网设备访问时显示配对页，配对成功后进入移动端控制面板。
- 设备配对鉴权：4 位一次性配对码、Bearer Token、设备列表、设备重命名与移除。
- 插件化命令：API 只分发命令，具体能力由插件实现。
- 已内置插件：
  - `calculator`：打开 / 关闭 Windows 计算器。
  - `player`：播放 / 暂停、上一曲、下一曲。
  - `volume`：音量增大、音量减小、静音切换。
- Windows 集成：系统托盘、静默启动、注册表开机自启动、防火墙入站规则配置。

## 架构

```text
手机浏览器 / PC 浏览器
        │
        │  HTTP + 设备配对鉴权
        ▼
+---------------------------+
| EzWinCommand Agent         |
| FastAPI + Web UI + REST API|
+-------------+-------------+
              │
              ▼
       Command Dispatcher
              │
              ▼
          Plugin System
              │
              ▼
       Windows API / 进程控制
```

核心原则：**PC 是大脑，Mobile 是遥控器。**

## 仓库结构

```text
.
├── EzWinCommand-server/
│   ├── app.py                 # Agent 入口，启动 FastAPI、托盘、防火墙配置
│   ├── config.py              # HOST / PORT / 环境变量配置
│   ├── start_daemon.pyw       # 无控制台静默启动器
│   ├── startup.py             # 注册表 Run 键开机自启动管理
│   ├── install-startup.bat    # 开机自启动安装脚本
│   ├── requirements.txt       # Python 依赖
│   ├── agent/
│   │   ├── api.py             # REST API 路由
│   │   ├── auth.py            # 配对码与 Bearer 鉴权中间件
│   │   ├── device_store.py    # devices.json 持久化存储
│   │   ├── dispatcher.py      # 命令分发器
│   │   └── firewall.py        # Windows 防火墙规则配置
│   ├── plugins/
│   │   ├── base.py            # BasePlugin / CommandResult 契约
│   │   ├── loader.py          # 插件自动发现与加载
│   │   ├── calculator.py      # 计算器插件
│   │   ├── player.py          # 媒体控制插件
│   │   └── volume.py          # 音量控制插件
│   └── web/
│       ├── index.html         # Web UI 页面
│       └── static/            # 前端脚本与样式
├── EzWinCommand-client/       # 客户端预留目录
└── plan.md                    # 项目 README
```

## 运行环境

- Windows 10 / Windows 11
- Python 3.13（项目当前按 Python 3.13 运行）
- 局域网访问场景

Python 依赖见 `EzWinCommand-server/requirements.txt`：

```text
fastapi
uvicorn[standard]
psutil
pywin32
python-dotenv
```

## 快速开始

```bash
cd EzWinCommand-server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

默认监听：

```text
http://0.0.0.0:8080
```

本机管理面板：

```text
http://localhost:8080
```

手机端访问：

```text
http://<PC 局域网 IP>:8080
```

如需修改监听地址或端口，复制并编辑 `.env`：

```bash
copy .env.example .env
```

```env
HOST=0.0.0.0
PORT=8080
```

## 设备配对流程

1. 在 PC 上打开 `http://localhost:8080`。
2. 点击生成配对码。
3. 手机访问 `http://<PC 局域网 IP>:8080`。
4. 输入配对码和设备名。
5. Agent 返回设备 Key，前端后续请求携带 `Authorization: Bearer <key>`。
6. 已配对设备持久化到运行时文件 `agent/devices.json`。

安全策略：

- 配对码字符集：`0-9a-z`。
- 配对码长度：4 位。
- 配对码有效期：5 分钟。
- 连续 5 次失败后锁定 30 秒。
- `localhost` 请求自动放行，方便 PC 管理面板操作。
- `/ping`、`/api/pairing-code`、`/api/authorize` 为公开端点。

## API

### 公开端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/ping` | 健康检查 |
| `GET` | `/api/pairing-code` | 获取当前配对码状态 |
| `POST` | `/api/authorize` | 提交配对码和设备名，换取设备 Key |

### 鉴权端点

鉴权方式：`Authorization: Bearer <device-key>`；`localhost` 请求由中间件放行。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/status` | CPU / 内存状态快照 |
| `POST` | `/api/command` | 统一命令入口 |
| `GET` | `/api/actions` | 列出已加载插件和子操作 |
| `GET` | `/api/devices` | 列出已配对设备 |
| `DELETE` | `/api/devices/{device_key}` | 移除设备 |
| `PATCH` | `/api/devices/{device_key}` | 重命名设备 |
| `POST` | `/api/pairing-code/refresh` | 刷新配对码 |

### 命令请求示例

```http
POST /api/command
Content-Type: application/json
Authorization: Bearer <device-key>
```

```json
{
  "action": "player",
  "params": {
    "sub_action": "play_pause"
  }
}
```

响应：

```json
{
  "success": true,
  "message": "播放/暂停",
  "data": null
}
```

## 插件系统

API 不直接执行 Windows 操作，而是通过 Dispatcher 分发到插件：

```text
API → Dispatcher → Plugin → Windows API / 进程控制
```

插件契约：

```python
from typing import Any
from plugins.base import BasePlugin, CommandResult

class MyPlugin(BasePlugin):
    name = "my_plugin"    # 命令 action 标识
    label = "我的插件"      # Web UI 显示名称

    def get_sub_actions(self) -> list[dict[str, str]]:
        return [
            {"id": "do_something", "label": "执行操作"},
        ]

    def execute(self, params: dict[str, Any]) -> CommandResult:
        return CommandResult(success=True, message="完成")

    def get_status(self) -> dict[str, Any] | None:
        return None
```

加载规则：

- `PluginLoader` 扫描 `EzWinCommand-server/plugins/*.py`。
- 文件名以下划线开头的模块会被跳过。
- 模块内继承 `BasePlugin` 的类会被实例化。
- `name` 为空的插件会被跳过。
- `name` 冲突时后加载插件覆盖先加载插件，并写入日志。

当前 `/api/actions` 返回：

```json
{
  "actions": [
    {
      "name": "player",
      "label": "媒体控制",
      "sub_actions": [
        {"id": "play_pause", "label": "播放/暂停"},
        {"id": "prev", "label": "上一曲"},
        {"id": "next", "label": "下一曲"}
      ]
    }
  ]
}
```

## Windows 集成

### 系统托盘

`app.py` 启动时会创建系统托盘图标。托盘菜单提供：

- 打开 Web UI。
- 查看服务状态。
- 退出 Agent。

托盘启动失败时，Agent 会继续以无托盘模式运行。

### 静默启动

双击运行：

```text
EzWinCommand-server/start_daemon.pyw
```

该脚本使用 `pythonw.exe` 启动 `app.py`，不显示控制台窗口。

### 开机自启动

注册：

```bash
cd EzWinCommand-server
python app.py --install
```

注销：

```bash
python app.py --uninstall
```

实现方式：写入当前用户注册表 Run 键：

```text
HKCU\Software\Microsoft\Windows\CurrentVersion\Run\EzWinCommandAgent
```

也可以运行：

```text
EzWinCommand-server/install-startup.bat
```

### 防火墙规则

Agent 启动时会尝试通过 `netsh` 添加入站规则，允许 `8080` 端口局域网访问。该操作通常需要管理员权限；失败时应检查日志并手动放行端口。

## 当前限制

- 通信仍为 HTTP，适合可信局域网；公网暴露前需要 HTTPS 或专用隧道。
- 插件参数目前是自由字典，尚未接入 Pydantic Schema 校验。
- `/status` 当前返回 CPU / 内存快照，尚未改为插件领域状态聚合。
- Android App 尚未实现，当前移动端入口是手机浏览器。
- `BEARER_TOKEN` 环境变量保留但当前鉴权以设备配对 Key 为准。

## 路线图

### P0：插件规范化

- [ ] 为插件参数引入 Pydantic Schema。
- [ ] 让 `/api/actions` 返回参数定义，供前端动态渲染表单。
- [ ] 将 `/status` 改为 Dispatcher 聚合插件 `get_status()`。

### P1：插件生态基础

- [ ] 插件 Manifest：版本、权限、依赖声明。
- [ ] PluginLoader 集成 Manifest 校验与权限校验。
- [ ] 插件开发模板与文档。

### P2：功能扩展

- [ ] 新增锁屏、睡眠、Steam、OBS 等插件。
- [ ] Dispatcher 层宏编排：声明式 JSON 工作流、等待、条件执行。
- [ ] Android App：Kotlin + Jetpack Compose。

### P3：安全与运维

- [ ] HTTPS 支持。
- [ ] 按需支持 Tailscale / Cloudflare Tunnel。

## 许可证

当前仓库未声明开源许可证。使用、分发或二次开发前，请先补充明确的 LICENSE。
