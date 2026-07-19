# Android：连接与控制

## 职责

发现或连接局域网 Server，完成配对和会话保存，并向用户提供命令、媒体与音频控制界面。

## 特性与功能点

- `ANDROID-CONN-01`：接受可信局域网 HTTP 地址并拒绝不可信 HTTP 主机。
- `ANDROID-CONN-02`：发现 Server、选择地址并处理连接失败与恢复。
- `ANDROID-PAIR-01`：输入配对码和设备名，保存成功会话。
- `ANDROID-PAIR-02`：配对失败后保持可恢复输入和清晰错误状态。
- `ANDROID-SESSION-01`：安全保存设备会话，撤销或认证失败后退出失效状态。
- `ANDROID-MEDIA-01`：展示媒体卡并执行播放控制。
- `ANDROID-AUDIO-01`：展示和修改音量、输入设备与输出设备。
- `ANDROID-SSE-01`：消费媒体事件，处理断线、恢复、取消和过期状态。

## 主要测试

参见 `TC-ANDROID-*`、`TC-MEDIA-*`、`TC-AUDIO-*` 和 `TC-XPLAT-*`。
