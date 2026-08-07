# EzWinCommand 变更日志

## 2026-08-08

### 新增

- 新增 `OLED 护屏` 插件，Android 仅提供与电竞模式一致的矩形“进入护屏”按钮。
- 点击后启动一次性 60 秒定时器；键盘或鼠标 Raw Input 会取消定时器和监听，定时器到期后使用 Windows 原生 `SC_MONITORPOWER` 关闭显示器。

## 2026-07-19

### 变更

- localhost 管理页改用本机 SSE 接收配对和设备变更通知；移除空闲时每秒配对轮询和每 30 秒设备轮询，外部控制页及命令执行期间的有限轮询保持不变。

### 移除

- 移除 Windows 计算器控制插件；Server 不再发现或执行 `calculator`，Web 与 Android 的动态动作列表不再显示计算器。

### 兼容

- 旧客户端提交 `calculator` 命令时保持现有未知命令响应语义：HTTP 200，`success=false`。
