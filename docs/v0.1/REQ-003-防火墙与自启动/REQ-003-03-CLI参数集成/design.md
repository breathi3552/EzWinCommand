# REQ-003-03: CLI 参数集成

- **父需求**: REQ-003
- **日期**: 2026-07-02
- **状态**: 已完成

## 设计概述

通过 Python 标准库 `argparse` 为 `app.py` 添加 CLI 参数支持，提供 `--install` 和 `--uninstall` 两个互斥选项来管理开机自启动注册。

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `app.py` | 修改 | 添加 argparse 解析和启动模式分发 |

## 实现要点

### argparse 配置

`_parse_args()` 创建 `ArgumentParser`：
- `prog="EzWinCommand Agent"`
- `description="Windows 命令代理服务"`
- `add_mutually_exclusive_group()` 确保 `--install` 和 `--uninstall` 互斥

### 启动模式分发

```python
if __name__ == "__main__":
    args = _parse_args()
    if args.install:
        from startup import install
        install()
        print("EzWinCommand Agent 已注册开机自启动。")
    elif args.uninstall:
        from startup import uninstall
        uninstall()
        print("EzWinCommand Agent 已注销开机自启动。")
    else:
        main()
```

- 无参数：默认启动 Server（走 `main()`）
- `--install`：注册开机自启动后退出
- `--uninstall`：注销开机自启动后退出
- 含 `--help` 自动生成帮助信息
- 非法参数时 argparse 自动报错并显示用法
