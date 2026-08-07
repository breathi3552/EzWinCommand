# EzWinCommand 变更日志

## 2026-08-08

### 新增

- 新增 `OLED 护屏` 插件，Android 提供进入护屏和恢复显示两个图标操作。
- 使用 Windows 原生显示器电源消息关闭或恢复显示器，不调用 DDC/CI、Sleep/Hibernate 或输入设备监听。

## 2026-07-19

### 变更

- localhost 管理页改用本机 SSE 接收配对和设备变更通知；移除空闲时每秒配对轮询和每 30 秒设备轮询，外部控制页及命令执行期间的有限轮询保持不变。

### 移除

- 移除 Windows 计算器控制插件；Server 不再发现或执行 `calculator`，Web 与 Android 的动态动作列表不再显示计算器。

### 兼容

- 旧客户端提交 `calculator` 命令时保持现有未知命令响应语义：HTTP 200，`success=false`。
