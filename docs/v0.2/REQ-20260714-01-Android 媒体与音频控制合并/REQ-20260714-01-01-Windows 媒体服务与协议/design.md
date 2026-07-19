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

## Spotify 多会话选择修复同步（2026-07-15）

本轮最终实现涉及 `EzWinCommand-server/media/service.py` 与 `EzWinCommand-server/tests/test_media_service.py`：枚举 GSMTC sessions，按 PLAYING 优先、已选稳定性、Windows current、稳定 source id 选择；状态、封面和三键命令共用 selected 引用；事件订阅与 token 在重绑/close 时完整清理。HTTP、JSON、SSE、`MediaService.submit` 与 Android schema 不变。

自动化验证：S-01~S-06 行为覆盖通过，Server 测试共 28 passed；`python -m compileall media/service.py tests/test_media_service.py` exit 0。

真实 E2E：随机端口、单 worker、无 reload 环境下 Server 多会话选择、暂停同步、三键目标与 token close 通过。旧固定端口 18080 命中旧实例属于环境错配，已撤回，不计为当前产品问题。真实 Spotify 封面仍出现 `cover=null`，thumbnail task 无结果，保持 blocking；Android 完整命令闭环为 Manual pending。

## 封面遗留风险归档（2026-07-16）

- T-003：STA 服务中的 `open_read_async` 挂起；显式 MTA 探针可取得 Spotify 128272-byte PNG、Edge/B站 25046-byte PNG。
- 状态：遗留风险/下一轮立即修复；本轮仅记录，不修改产品代码。
- Android 完整命令闭环保持 Manual pending。

## COVER-MTA 修复同步（2026-07-16）

- 模块级主线程预载 `comtypes`；EzMediaLoop 显式 MTA init/uninit，失败初始化不误反初始化；manager token 逐项回滚。
- T-003 服务端封面阻塞已关闭。真实 Evidence：PID 32752，B站 title、volume=56、5 render、8 capture；cover URL HTTP 200 `image/png` 20945 bytes 可解码；播放与音量往返 success；日志无 COM/RPC_E_CHANGED_MODE/Traceback/ERROR/异常/失败。
- Reviewer 复审 PASS with notes；Automated 41 passed。Android 封面显示仍 Manual pending。

## R5 事件驱动媒体与 UI 重构同步（2026-07-16）

- `media/service.py` 增量实现 dirty 合并、`request_refresh(domains)`、artwork identity/generation 与 MTA callback 生命周期；`agent/api.py` 增加 Bearer refresh API 和原子 SSE 注册。
- Server 定向测试 45 passed；受控 refresh 200，空闲 revision 4→4 且无重复读取。Windows 真实 callback 与播放/音量命令仍 Manual pending。
***

## R6 callback 重绑定设计与验证（2026-07-16）

- callback 通过 `QueryInterface` 获取的 pointer 在注册与注销阶段保持同一 identity；endpoint 替换顺序固定为先注册新 callback、再注销旧 callback；volume callback 只标记 audio dirty，不触发 media read。
- 自动化：Server 三媒体回归 47 passed/3 warnings；callback 专项 2 passed。
- 真实 Windows：受控 launch `127.0.0.1:18937`。第一轮 Focusrite 音量 80→65→80，revision 4→5 且媒体字段不变；第二轮 Focusrite→INZONE→Focusrite，INZONE 音量 60，最终恢复 80，revision 5→8→9；无“读取音频状态失败”或“Interface not supported”，服务已 stop。
