# EzWinCommand 变更日志

## 2026-07-19

### 移除

- 移除 Windows 计算器控制插件；Server 不再发现或执行 `calculator`，Web 与 Android 的动态动作列表不再显示计算器。

### 兼容

- 旧客户端提交 `calculator` 命令时保持现有未知命令响应语义：HTTP 200，`success=false`。
