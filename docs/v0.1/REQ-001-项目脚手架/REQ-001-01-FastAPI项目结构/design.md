# REQ-001-01: FastAPI 项目结构

- **父需求**: REQ-001
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

搭建 EzWinCommand 项目的 Python 项目骨架，包含 FastAPI 入口文件 `app.py`、环境变量配置管理 `config.py` 以及 Python 依赖声明 `requirements.txt`。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| EzWinCommand-server/app.py | 新增 | FastAPI 应用入口，初始化 Dispatcher、挂载路由与静态文件 |
| EzWinCommand-server/config.py | 新增 | 读取 .env 配置并提供默认值 |
| EzWinCommand-server/requirements.txt | 新增 | Python 依赖清单 |

## 实现要点

### app.py — 应用入口

- 创建 `FastAPI` 实例，title 设为 `"EzWinCommand Agent"`
- 初始化 `Dispatcher` 实例并调用 `discover_plugins("plugins")` 扫描插件目录
- 将 Dispatcher 存入 `app.state.dispatcher`，供 API 路由通过 `Request` 访问
- 注册 API 路由：`app.include_router(api_router)`
- 挂载 Web UI：`app.mount("/", StaticFiles(directory="web", html=True), name="webui")`
- `main()` 函数：启动时配置防火墙规则后通过 `uvicorn.run()` 启动服务
- `__name__ == "__main__"` 时调用 `main()`
- 日志使用 `logging` 标准库，输出格式含时间戳和模块名

### config.py — 配置管理

- 使用 `python-dotenv` 的 `load_dotenv()` 加载 `.env` 文件
- 三个配置项均为模块级常量：
  - `HOST` — 默认 `"0.0.0.0"`，允许局域网访问
  - `PORT` — 默认 `8080`，转为 int
  - `BEARER_TOKEN` — 默认空字符串，后续迭代启用鉴权

### requirements.txt — 依赖清单

| 依赖 | 版本 | 用途 |
|---|---|---|
| fastapi | >=0.115.0 | Web 框架 |
| uvicorn[standard] | >=0.30.0 | ASGI 服务器 |
| psutil | >=6.0.0 | 系统状态采集 |
| pywin32 | >=306 | Windows API 封装 |
| python-dotenv | >=1.0.0 | .env 配置加载 |
