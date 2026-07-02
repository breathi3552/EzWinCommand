# REQ-001-04: 插件系统

- **父需求**: REQ-001
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

实现可扩展的插件系统，包含：抽象基类 `BasePlugin`、统一返回类型 `CommandResult`、自动发现加载器 `PluginLoader`，以及 Demo 插件 `CalculatorPlugin`。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| EzWinCommand-server/plugins/__init__.py | 新增 | plugins 包初始化 |
| EzWinCommand-server/plugins/base.py | 新增 | BasePlugin 抽象基类 + CommandResult |
| EzWinCommand-server/plugins/loader.py | 新增 | PluginLoader 自动发现与加载 |
| EzWinCommand-server/plugins/calculator.py | 新增 | Demo 插件：打开/关闭 Windows 计算器 |

## 实现要点

### CommandResult — 统一返回类型

```python
class CommandResult:
    success: bool        # 是否执行成功
    message: str         # 人类可读描述
    data: dict | None    # 附加结构化数据

    def to_dict(self) -> dict  # 序列化为字典
```

定义在 `plugins/base.py` 中，Dispatcher 和所有插件共享此类型。

### BasePlugin — 抽象基类

```python
class BasePlugin(ABC):
    name: str = ""              # 路由键（必需）
    label: str = ""             # 人类可读名称

    def get_sub_actions(self) -> list[dict[str, str]]:  # 返回子操作列表
        return []

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> CommandResult: ...

    def get_status(self) -> dict[str, Any] | None:      # 可选状态采集
        return None
```

**约定**：
- 子类必须设置 `name` 属性，否则 PluginLoader 跳过该插件
- 子类必须实现 `execute(params)` 方法
- `get_sub_actions()` 返回空列表表示简单触发型插件，返回非空表示有子操作（如 volume 的 up/down/mute）

### PluginLoader — 自动发现

```python
class PluginLoader:
    plugins: dict[str, BasePlugin]  # name → 实例

    def discover(self, plugin_dir: str) -> None
    def get(self, name: str) -> BasePlugin | None
```

**discover 流程**：
1. 遍历 `plugin_dir` 下所有 `.py` 文件（跳过 `_` 开头的私有模块）
2. 通过 `importlib.import_module()` 动态导入
3. 遍历模块属性，查找 `BasePlugin` 的非抽象子类
4. 实例化插件，检查 `name` 非空后注册到 `self.plugins`
5. 同名插件后加载覆盖先加载，记录 warning 日志

### CalculatorPlugin — Demo 插件

- 路由键 `name = "calculator"`，显示名 `label = "计算器"`
- 子操作：`open`（打开 calc.exe）、`close`（终止 CalculatorApp.exe 进程）
- `_open()`：通过 `subprocess.Popen("calc.exe")` 启动计算器
- `_close()`：通过 `psutil.process_iter()` 遍历进程，按进程名 `calculatorapp.exe` 匹配后 `kill()`
