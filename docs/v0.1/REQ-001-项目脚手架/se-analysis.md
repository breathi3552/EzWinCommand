# REQ-001 SE 分析

- **日期**: 2026-07-02
- **版本**: v0.1

## 架构决策

### 技术选型

| 维度 | 选择 | 理由 |
|---|---|---|
| Web 框架 | FastAPI | 异步原生支持、自动 OpenAPI 文档、Python 生态丰富 |
| ASGI 服务器 | Uvicorn | FastAPI 官方推荐，性能优异 |
| 配置管理 | python-dotenv + .env 文件 | 简单、通用、无需额外依赖 |
| Windows API | pywin32 + ctypes | pywin32 提供高层封装，ctypes 用于精细控制 |

### 分层架构

```
app.py (入口)
  ├── config.py (配置)
  ├── agent/api.py (REST 路由)
  ├── agent/dispatcher.py (命令分发)
  └── plugins/
        ├── base.py (BasePlugin + CommandResult)
        ├── loader.py (PluginLoader)
        ├── calculator.py (Demo 插件)
        └── volume.py (音量控制)
```

### 设计原则

1. **API 不直接执行命令** — 所有命令经 Dispatcher 分发到插件，新增插件无需修改 API 代码
2. **插件自动发现** — PluginLoader 遍历 plugins/ 目录，动态导入 BasePlugin 子类
3. **统一返回契约** — 所有插件返回 `CommandResult`（success + message + data）
4. **Web UI 纯静态** — 通过 StaticFiles 挂载，无额外前端构建步骤

### 关键决策

- 插件通过 `name` 属性注册路由键，由 Dispatcher 按名查找分发
- `CommandResult` 作为数据传输对象在 base.py 中定义，dispatcher 和所有插件共享
- 配置使用环境变量 + .env 文件，提供合理默认值（HOST=0.0.0.0, PORT=8080）
