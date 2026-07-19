# 测试记录: REQ-20260714-01-01

| ID | 描述 | 严重程度 | 状态 | 关闭依据 |
|---|---|---|---|---|
| T-006 | PolicyConfig COM interface 未显式、幂等且按序释放 | Major | 已关闭 | 服务测试断言 `Release` 幂等，并严格早于同一 EzMediaLoop 的 `CoUninitialize` |

本子任务无未关闭 Automated blocking 问题。Windows 真实 GSMTC/Core Audio 验证为 Manual pending。

| R1-REV-01 | Reviewer 首轮指出真实 uvicorn 测试存在预绑定 socket/线程退出断言缺口 | Major | 已关闭 | `agent://MediaStartupReview-2` PASS；预绑定 loopback socket、`thread.join(timeout=5)` 与 `not thread.is_alive()` 已补齐 |

本轮 Reviewer notes 已全部关闭；无未关闭 Automated blocking 问题。真实 Windows GSMTC/Core Audio 验证仍为 Manual pending。
 
| R3-SRV-001 | 媒体可靠性修复 targeted tests | Major | 已关闭 | Server targeted tests 27 passed；无未关闭 Automated blocking 问题 |
本轮 V-02/V-03 未执行；真实 Windows adapter 故障恢复仍 Manual pending。

## Spotify 多会话与封面验收（2026-07-15/16）

| ID | 描述 | 严重程度 | 状态 | 关闭依据 |
|---|---|---|---|---|
| S-01~S-06 | GSMTC 多会话选择、暂停保持、反向切换、双 PLAYING 稳定性、状态/封面/三键 selected 一致性、token 重绑与 close | — | 已关闭 | Server 测试 28 passed；真实随机端口单实例验证通过；compileall exit 0 |
| T-003 | STA `open_read_async` 封面读取挂起 | Blocking | 已关闭 | COVER-MTA 后真实服务 PID 32752；B站 title/volume/devices 正常，cover URL HTTP 200 `image/png` 20945 bytes 可解码；播放与音量往返 success；日志无 COM/RPC_E_CHANGED_MODE/Traceback/ERROR/异常/失败 |

本轮 Automated 41 passed（3 warnings，13.87s）；Reviewer 复审 PASS with notes。Android 封面显示仍 **Manual pending**。

| R5-SRV-001 | 事件驱动 dirty/refresh、原子 SSE 与 artwork generation | Major | 已关闭 | Server 定向测试 45 passed；受控 refresh 200、空闲 revision 4→4 且无重复读取 |

本轮 Windows 真实 callback、播放/音量命令仍 Manual pending；无未关闭 Automated blocking 问题。
***

| R6-SRV-001 | callback QueryInterface pointer identity、先新注册后旧注销、volume-only dirty 语义 | Major | 已关闭 | callback 专项 2 passed；Server 回归 47 passed/3 warnings；listener/audio read 行为断言通过 |
| R6-WIN-001 | 真实 endpoint 重绑定与音量发布闭环 | Major | 已关闭 | 受控 launch port 18937：80→65→80、revision 4→5；Focusrite→INZONE→Focusrite，音量 60→80、revision 5→8→9；无读取音频状态失败或 Interface not supported，服务已 stop |

R6 无未关闭 Automated 或真实 Windows blocking 问题；R5 的历史 Manual 状态不适用于 R6 最终证据。
