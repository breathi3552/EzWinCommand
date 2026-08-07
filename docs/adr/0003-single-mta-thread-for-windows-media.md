# Windows 媒体集成由单一 MTA 线程持有

EzWinCommand 由单一 MTA 线程创建、使用并释放 Windows 媒体与 Core Audio 对象，再把规范化状态提供给 HTTP 和事件层。直接在请求线程或多个工作线程间共享 WinRT/COM 对象会模糊 apartment、回调和关闭顺序；PowerShell 或虚拟媒体键虽然隔离简单，却无法稳定提供完整、连续的媒体和音频状态。

## Consequences

Windows adapter 的生命周期必须服从所属线程，初始化、恢复和关闭不能阻塞普通 HTTP 可用性。API 与客户端只消费规范化状态，不取得或跨线程传递平台对象。
