# EzWinCommand 变更日志

## 2026-08-13

### 变更

- Server、Android 与 Web 的设备管理统一切换为稳定非敏感 `device_id`；设备列表仅返回名称、创建时间、最后活动时间、`is_current` 和 `device_id`，localhost 不标记当前设备，远端按鉴权请求标记。
- localhost 与任一已配对设备均可按 `device_id` 重命名、撤销全部设备；不存在目标返回明确失败，Android 自撤销后清除会话并回到配对页，撤销其他设备后重新读取权威列表。
- 撤销改由设备关系 module 发布带类型、非敏感的失效事实，按固定顺序终止目标媒体流并通知本机管理页重新读取；Android 在确认 Server identity 后统一处理授权失效，同一身份且凭据失效时删除会话，不同身份或不可达时保留记录并显示不可操作的终止错误。
## 2026-08-09

### 变更

- Windows media integration 在空闲时仅等待真实 dirty event；初始化失败使用可取消且有上限的指数退避，媒体恢复和关闭不会阻断基础 HTTP，并清理 adapter 与待处理刷新。
- Android 音量与输入、输出设备操作统一通过权威 Media Snapshot/SSE 收敛；音量保留即时节流和失败回滚，设备选择移除 pending 状态，并移除命令完成后的重复 refresh。
- Android `MediaConnectionController` 在控制页存活期间保留最后有效媒体快照并静默退避重连；SSE 恢复先应用恢复快照再处理事件，集中抑制旧 revision、迟到封面和销毁后的回调。

## 2026-08-08

### 变更

- OLED 护屏改为 5 秒初始倒计时；倒计时窗口提供“取消”按钮，取消按钮和任意键盘 Key Down 都会结束整个护屏循环，鼠标移动和普通点击不会取消。
- 显示器关闭后监听 `GUID_MONITOR_POWER_ON`；显示器重新亮起时启动 60 秒倒计时，倒计时到期再次关闭显示器并继续循环。关屏后的第一个键盘唤醒按键直接取消，鼠标唤醒继续进入下一轮倒计时。

## 2026-07-19

### 变更

- localhost 管理页改用本机 SSE 接收配对和设备变更通知；移除空闲时每秒配对轮询和每 30 秒设备轮询，外部控制页及命令执行期间的有限轮询保持不变。

### 移除

- 移除 Windows 计算器控制插件；Server 不再发现或执行 `calculator`，Web 与 Android 的动态动作列表不再显示计算器。

### 兼容

- 旧客户端提交 `calculator` 命令时保持现有未知命令响应语义：HTTP 200，`success=false`。
