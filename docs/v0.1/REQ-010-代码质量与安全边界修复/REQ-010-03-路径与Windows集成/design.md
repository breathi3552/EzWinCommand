# REQ-010-03: 路径与 Windows 集成

- **父需求**: REQ-010
- **日期**: 2026-07-06
- **状态**: 已完成

## 设计概述

消除当前工作目录对运行时路径的影响，并让 Windows 防火墙与托盘入口跟随实际端口配置。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `EzWinCommand-server/app.py` | 修改 | 定义 `BASE_DIR`，注入插件目录、设备文件路径、托盘 URL |
| `EzWinCommand-server/agent/dispatcher.py` | 修改 | `discover_plugins()` 支持 `Path` 和 package |
| `EzWinCommand-server/plugins/loader.py` | 修改 | 插件发现使用传入路径，导入包名独立于路径 |
| `EzWinCommand-server/agent/firewall.py` | 修改 | 防火墙规则名按端口生成 |
| `EzWinCommand-server/tray.py` | 修改 | `SystemTray` 支持 `web_url` 注入 |

## 接口契约

### 导出

```python
class Dispatcher:
    def discover_plugins(self, plugin_dir: str | Path = "plugins", package: str = "plugins") -> None: ...

class PluginLoader:
    def discover(self, plugin_dir: str | Path, package: str = "plugins") -> None: ...

class SystemTray:
    def __init__(self, on_exit: Callable[[], None], tooltip: str = "EzWinCommand Agent", web_url: str = "http://127.0.0.1:8080") -> None: ...

def add_rule(port: int) -> bool: ...
```

### 依赖

| 依赖子需求 | 需要的接口 |
|---|---|
| 无 | 无 |

## 实现要点

- `BASE_DIR = Path(__file__).resolve().parent`。
- `DeviceStore(BASE_DIR / "agent" / "devices.json")` 防止从仓库根目录启动时生成根 `agent/devices.json`。
- 插件扫描路径为 `BASE_DIR / "plugins"`，导入包仍为 `plugins.<module>`。
- 防火墙规则名使用 `EzWinCommand {port}`。
- 托盘打开地址使用 `http://127.0.0.1:{config.PORT}`。

## 完成定义

- [x] `design.md` 与代码一致
- [x] 接口契约全部履行
- [x] Reviewer 审批通过
- [x] Test 测试通过，无未关闭的 `test-records` 条目
- [x] 父需求 `se-analysis.md` 状态已同步
