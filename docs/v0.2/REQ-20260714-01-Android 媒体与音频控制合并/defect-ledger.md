# defect-ledger: REQ-20260714-01

> 用户侧 / 契约失配 / 流程跳步 / 否决方案只写本表；测试执行中的实现/断言问题写各子任务 `test-records.md`。

## 缺陷账本

本轮 `USER_DEFECT=yes`，已记录用户反馈“媒体插件经常失效”及原始媒体初始化超时；原始 P0 已由第三轮真实 Server→Android 复测关闭，持续可靠性验证仍部分未执行。

| ID | 来源 | 用户侧 | 描述 | 严重程度 | 状态 | 关闭依据 |
|---|---|---|---|---|---|---|
| U-001 | 用户日志 | 是 | 媒体初始化/首次读取超时抛 `TimeoutError`，导致服务启动失败、`/ping` 不可达 | Blocking | 已关闭 | R1 测试覆盖 hanging initialize、晚恢复及真实 uvicorn `/ping`；第三轮 Server→Android 连续 state `error=null`、Android 无初始化超时 |
| U-002 | 用户 | 是 | 用户反馈“媒体插件经常失效”，表现为初始化 timeout 与媒体状态不可用 | P0 | 已关闭 | R3 修复后 Server targeted tests 27 passed；Android targeted BUILD SUCCESSFUL；第三轮真实路径状态可用 |

`DEFECT_LEDGER=updated`。V-02/V-03/V-04 未执行、V-07 Manual pending，不作为通过；测试实现问题记录于子任务 `test-records.md`。
