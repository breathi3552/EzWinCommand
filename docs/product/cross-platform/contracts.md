# 跨端契约

## 边界

Server 是业务协议来源；Android 与 Web 必须对状态、错误、鉴权和异步生命周期保持兼容。

## 功能点

- `XPLAT-PAIR-01`：配对请求/响应字段及错误语义一致。
- `XPLAT-AUTH-01`：Bearer 设备密钥的发送、撤销和失败处理一致。
- `XPLAT-CMD-01`：同步结果与 `202 + task status` 长任务语义一致。
- `XPLAT-MEDIA-01`：媒体 snapshot 的 snake_case wire、必需字段和范围一致。
- `XPLAT-SSE-01`：事件 id 与 revision 一致，断线恢复和撤销终止语义一致。

## 变更规则

协议字段、错误语义、状态机或安全边界变化属于重需求。必须更新两端契约测试、产品地图和版本日志，并运行跨端验证。
