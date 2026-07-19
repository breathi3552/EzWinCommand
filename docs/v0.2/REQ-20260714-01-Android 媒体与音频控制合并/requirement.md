# REQ-20260714-01: Android 媒体与音频控制合并

- **日期**: 2026-07-14
- **版本**: v0.2
- **流程**: Full
- **变更类型**: protocol | platform | behavior
- **USER_DEFECT**: yes
- **R4 COVER-MTA 状态**：Windows 封面服务端修复已完成并通过 Reviewer 复审（PASS with notes）；Automated 41 passed；Android 页面实际显示仍 **Manual pending**，不得表述为需求已完成/已可用。
- **R4 真实证据**：服务 PID 32752；B站 title 正常、volume=56、5 render、8 capture；cover URL 非空并 HTTP 200，`image/png` 20945 bytes 且可解码；播放 `playing→paused→playing` 两次命令 success；音量 `56→55→56` 命令 success；日志无 `RPC_E_CHANGED_MODE`/COM/Traceback/ERROR/异常/失败。
- **Reviewer/Tester**：Reviewer 复审 PASS with notes；Automated 41 passed（3 warnings，13.87s）；Android UI 封面显示未获用户确认，保持 Manual pending。

## 原始需求

将旧 `player` 媒体插件和 `volume` 音量插件 clean cutover 为唯一 `media` 插件；Android 提供完整媒体卡，服务端接入 Windows GSMTC、Core Audio、REST/封面/SSE，并闭合文档与错误日志规范。

## 目标

- Android 完整媒体卡展示封面、歌曲、艺术家、播放态，控制上一首、播放/暂停、下一首、主音量和默认输入/输出设备。
- 服务端以单线程媒体服务持有 WinRT/COM 对象，仅状态变化时通过 SSE 推送；封面与状态 revision 解耦。
- 删除旧 `player`/`volume` 插件、action、配置键与兼容路径。
- 固定依赖 `winrt-Windows.Media.Control[all]==3.2.1`、`pycaw==20251023`。
- 客户端只显示短错；服务端保留 traceback 与必要非敏感上下文，不记录密钥或令牌。

## 非目标

- 本轮不把 Web 改造成 Android 同款完整媒体卡；Web 保持通用插件卡，未来收敛为管理后台入口。
- 不增加播放器选择器，始终使用 GSMTC 系统当前会话。
- 不改变电竞模式按显示名切换音频设备的既有语义。
- 不提交或推送代码/docs。
- 不执行 formatter、lint 或项目级全套测试。

## 完成条件

- [x] 服务端媒体服务、插件 clean cutover、REST/封面/SSE 自动化验证通过。
- [x] Android 严格协议、生命周期、媒体卡与音量 actor 自动化验证通过。
- [x] Android Debug APK 构建通过。
- [x] README 已记录 Android 完整媒体卡、固定依赖和 Web 管理后台 TODO。
- [x] `.omp/RULES.md` 已固化短错、traceback/非敏感上下文和敏感信息禁记规范。
- [x] 两个子任务的 design/test-records 与最终代码和测试状态同步。
- [x] V-R6 Windows Core Audio callback 重绑定与 volume-only callback 真实验证通过；Android Popup 设备行与图标按钮自动化/实机证据通过。
- [ ] Android 重命名/删除提交与 TalkBack 手动验收：Manual pending。

## R6 最终增量（2026-07-16）

- UI：设备 row、本机 chip、rename/delete ImageButton（无按钮文本，触控区 126px）已在 emulator-5554 Popup 实测。
- Core Audio：callback QueryInterface 与注册/注销使用同 pointer；先注册新 endpoint 后注销旧 endpoint；volume callback 仅标记 audio dirty。
- Automated：Server 三媒体回归 **47 passed，3 warnings**；callback 专项 2 passed；Android View/testDebugUnitTest/assembleDebug BUILD SUCCESSFUL。
- Windows 真实受控 launch port 18937：第一轮音量 80→65→80、revision 4→5、媒体不变；第二轮 Focusrite→INZONE→Focusrite，INZONE 音量 60，最终恢复 80，revision 5→8→9；无“读取音频状态失败”或“Interface not supported”，服务已 stop。

## R6 完成叙事

| 栏 | 状态 |
|---|---|
| Automated | Server 47 passed/3 warnings；callback 2 passed；Android View、testDebugUnitTest、assembleDebug 成功；Popup 真实观察到本机 chip 与 126px 图标按钮。 |
| Manual | 仅 Android 重命名/删除提交与 TalkBack：Manual pending；Windows 两项真实 callback/音量闭环均 Pass。 |
| 非目标 | Web、formatter、lint、项目级全套测试、commit/push；不改代码以外范围。 |

总体状态：R6 Windows 与 Automated 通过；Android 仅重命名/删除提交与 TalkBack 为 Manual pending。
 
## R3 问题发现与修复过程

- 审查发现四项可靠性问题：event loop 阻塞、运行期 adapter 不重建、封面失败不重试、Android media scope 无关闭路径。
- 首次 E2E 仍复现初始化超时；A/B 两轮定位记录 0.5s deadline、GSMTC 属性/thumbnail 约 0.8s、Core Audio 约 0.8s 的延迟因素。
- 第三轮关闭原始 P0；V-02/V-03/V-04 未执行，V-07 Manual pending，V-06 SSE 更新/自动恢复未完整验证。

## 拆分需求列表

| 编号 | 标题 | 状态 |
|---|---|---|
| REQ-20260714-01-01 | Windows 媒体服务、插件 clean cutover 与 REST/SSE | Automated Pass；Manual pending |
| REQ-20260714-01-02 | Android 媒体协议、生命周期与专用媒体卡 | Automated Pass；Manual pending |

## R1 归档补充：媒体初始化不阻断启动

- **根因**：旧 lifespan 将媒体 readiness 当作 HTTP 启动前置条件，`start()` 超时抛出 `TimeoutError`，导致 uvicorn 退出。
- **Supersession**：R1 废弃“媒体初始化超时则整个服务启动失败”及向 lifespan 穿透 readiness `TimeoutError` 的契约；后台 bootstrap 晚完成后同进程恢复。
- **本轮代码范围**：生产代码未修改；仅修改 `EzWinCommand-server/tests/test_media_service.py` 与 `EzWinCommand-server/tests/test_media_api.py` 的验证覆盖。
- **完成条件**：R1 V-START-01/02/03/04/05/06 Automated Pass；Reviewer-2 PASS；V-MAN-01/02 真实 GSMTC/Core Audio 仍为 **Manual pending**。

## COVER-MTA 修复归档（2026-07-16）

- 模块级预载 `comtypes`；`EzMediaLoop` 在线程内显式 `COINIT_MULTITHREADED` init/uninit，初始化失败不误反初始化；manager token 逐项保存并在部分失败时逐项回滚。
- T-003 服务端封面阻塞已关闭：真实服务 PID 32752，B站 title 正常、volume=56、5 render、8 capture；cover URL 非空，HTTP 200，`image/png` 20945 bytes 且可解码；播放与音量往返命令均 success。
- Reviewer 复审 PASS with notes；Automated 41 passed，3 warnings，13.87s；日志筛查无 `RPC_E_CHANGED_MODE`/COM/Traceback/ERROR/异常/失败。
- Android 页面实际封面显示未由用户确认，保持 **Manual pending**；本需求不得写作“已完成/已可用”。docs 未获提交授权。

完成条件更新：Windows 服务端封面与命令/音量证据 ✓；Android 完整命令及页面封面显示 ✗（Manual pending）。

## R5 事件驱动媒体与 Android UI 重构（2026-07-16）

- 服务端事件驱动 dirty 合并、`POST /api/media/refresh`、原子 SSE snapshot、Windows callback 生命周期及 artwork generation 已实现；Android onOpen/生命周期与命令后 refresh、封面 generation、BottomSheet、固定 Header 和设备浮层已同步。
- R5-AND-001 首轮 Blocking/P1 已关闭：独立 Robolectric `MediaControlScreenViewTest` 在实际 Activity/root 层级验证入口已 attach（`isAttachedToWindow`）、`VISIBLE`，入口 `contentDescription/clickable/focusable`，且祖先均 `VISIBLE`、无 `NO_HIDE_DESCENDANTS`；指定测试与 `assembleDebug` 成功。
- R5 自动化与真实证据：Server 45 passed；受控 `/ping`/state/refresh 200，空闲 10 秒 revision 4→4 且无重复读取；Android `testDebugUnitTest assembleDebug` 成功；emulator-5554 实际显示媒体卡且 BottomSheet 已打开。

### R5 完成叙事

| 栏 | 状态 |
|---|---|
| Automated | Server 45 passed；受控 API refresh 200、空闲 revision 4→4、无重复读取；Android 单测与 assembleDebug 成功；R5-AND-001 自动化关闭。 |
| Manual | Windows callback/播放音量真实操作、真实设备浮层 rename/delete、TalkBack、当前设备删除确认与导航：**Manual pending**；BottomSheet 已实际打开，不属于 pending。 |
| 非目标 | Web、formatter、lint、项目级全套测试、commit/push。 |

总体状态：Automated Pass；Manual pending。不得表述为整体已完成或已可用。
***
