# 设计: REQ-20260714-01-01（R2 timeout recovery）

- **子需求**: 媒体初始化串行可取消、首次超时后 HTTP 继续与晚恢复
- **日期**: 2026-07-14
- **Dev**: MediaTimeoutReplacement

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `EzWinCommand-server/media/service.py` | 修改 | 单个串行 attempt supervisor；首次 deadline 后取消并等待结束，后续成功自动清错 |
| `EzWinCommand-server/tests/test_media_service.py` | 修改 | 覆盖取消、late recovery、close once、线程亲和与有界 stop |
| `EzWinCommand-server/tests/test_media_api.py` | 既有测试 | 验证媒体初始化超时不阻断 HTTP `/ping` |

## 接口契约履行

- `MediaService.start() -> None`：首次 deadline 发布短错并返回，HTTP 持续可用；后续 attempt 成功自动清错。
- `_run` 同时最多一个 active attempt；首次超时取消并 `gather` 完成后才 retry，`active attempt=1`。
- adapter 仅在 initialize 成功后安装；未安装 adapter 的取消路径 finally 恰好 close 一次，成功 adapter 由 supervisor finally close。
- retry sleep、initialize 等待与 stop 均可取消；`stop` 有界并在线程内释放资源。

## 实现要点

`_run` 以单个 attempt 串行循环，首次 deadline 后取消并等待初始化结束，再进入可中断 retry。成功后 `_publish_error(None)` 并启动 poll；停止时取消 poll、唤醒 stop event，并在同一媒体线程 close 已安装 adapter。REST/SSE wire 与导出接口不变。

## 局部验证

| 项目 | 对应验证 | 结果 |
|---|---|---|
| Server 媒体单测 | `python -m pytest tests/test_media_service.py -q` | PASS，13 passed |
| Server/API 聚焦 | `python -m pytest tests/test_media_service.py tests/test_media_api.py -q` | PASS，20 passed |
| 真实 Windows GSMTC/Core Audio | Manual | Manual pending |

[x] 首刷取消资源 close、active attempt=1、stop 有界；真实 WinRT 行为仍需真实 Windows 验收。

[docs/v0.2/REQ-20260714-01-Android 媒体与音频控制合并/REQ-20260714-01-01-Windows 媒体服务与协议/test-records.md#17B7]
INS.TAIL:
+
| R2-001 | 首次 deadline 后取消未等待可能造成并发 attempt/资源重复释放 | Major | 已关闭 | `_run` 取消后 gather 再 retry；测试覆盖 active attempt=1、close once 与 stop 有界，Server 聚焦 20 passed |

本子任务无未关闭 Automated blocking 问题。真实 Windows GSMTC/Core Audio 验证为 Manual pending。
 
## R3 媒体可靠性修复同步

本轮最终设计清单共 11 个文件；本子任务负责其中 4 个 Server 文件：

| 文件 | 变更 |
|---|---|
| `EzWinCommand-server/agent/api.py` | 修改：媒体 dispatcher 调用移出 FastAPI event loop |
| `EzWinCommand-server/media/service.py` | 修改：连续全域失败触发 adapter 关闭、退避重建；封面 replay 缓存扩展 |
| `EzWinCommand-server/tests/test_media_api.py` | 修改：慢命令期间 ping/SSE 并发覆盖 |
| `EzWinCommand-server/tests/test_media_service.py` | 修改：持续失败重建、单域瞬时失败不重建、封面缓存覆盖 |

Server targeted tests：27 passed。真实 Windows adapter 故障注入 V-02/V-03 未执行；V-07 Manual pending。
