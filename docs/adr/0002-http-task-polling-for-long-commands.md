# 长命令使用 HTTP Task 与轮询

EzWinCommand 将不能在普通请求周期内可靠完成的命令建模为独立 HTTP Task：Server 受理后返回任务标识，Web 和 Android 轮询任务状态。同步长请求无法区分网络中断与后台执行结果，WebSocket 或 SSE 双向任务通道又会为少量长命令引入更重的连接生命周期；持久化 Task 在断线、页面重建和 Server 恢复之间提供了明确边界。

## Consequences

任务状态不依赖最初的 HTTP 连接。Server 必须隔离任务所有者、限制公开结果并处理过期与重启恢复；客户端必须保存尚未终结的任务标识，并区分暂时不可达与任务已经消失。
