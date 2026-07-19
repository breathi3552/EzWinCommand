# SE 分析: REQ-20260714-01

- **需求**: REQ-20260714-01 — Android 媒体与音频控制合并
- **日期**: 2026-07-14
- **流程**: Full（跨 Windows 平台 API、服务生命周期、外部协议与 Android UI）
- **方案来源**: 批准的 `local://merged-media-plugin-plan.md`

## 方案

采用唯一 `media` 插件和进程级 `MediaService`。服务在 `EzMediaLoop` 单线程内持有 asyncio、COM、GSMTC 与 Core Audio 对象，500ms 刷新音频，仅规范状态变化时增加 revision。FastAPI lifespan 管理启停并桥接完整快照、封面缓存和 SSE replay。Android 每轮先取 snapshot，再以 revision 建立 SSE；连接 generation 隔离旧回调，音量 actor 执行 100ms single-in-flight/latest-wins；完整媒体卡仅在 Android 呈现。

## 选型与边界

| 决策 | 采用 | 未采用及原因 |
|---|---|---|
| Windows 媒体 | GSMTC + WinRT 固定依赖 | 不回退虚拟键、PowerShell 轮询或空实现 |
| 音频 | pycaw + Core Audio；默认设备使用最小 IPolicyConfig 封装 | 不复用电竞模式按显示名切换逻辑 |
| 同步 | snapshot + SSE + 64 revision replay | 不轮询重复业务状态，不内联 base64 封面 |
| 客户端 | Android 专用卡，Web 通用卡保持 | Web 完整卡非目标，未来收敛为管理后台 |
| 错误 | 客户端短错；服务端 traceback + 非敏感上下文 | 不向客户端回传内部异常，不记录密钥/令牌 |

## 子任务拆分

| 编号 | 子需求 | Owner | 依赖 | 状态 |
|---|---|---|---|---|
| REQ-20260714-01-01 | Windows 媒体服务、插件 clean cutover 与 REST/SSE | MediaServerDev | 固定 Windows 依赖 Gate | Automated Pass；Manual pending |
| REQ-20260714-01-02 | Android 媒体协议、生命周期与专用媒体卡 | MediaAndroidDev | 01-01 wire 契约 | Automated Pass；Manual pending |

## 接口契约

### 服务端

- `MediaState` 是完整不可变快照；revision 仅在规范字段变化时递增，cover URL 仅随 MIME/图片 bytes token 改变。
- `MediaService.start/stop/snapshot/submit/add_listener` 由唯一后台线程承载平台对象。
- `media` 公开子操作精确为 `play_pause`、`prev`、`next`；执行接口另接受带值的 `set_volume`、`set_output_device`、`set_input_device`。
- `GET /api/media/state`、`GET /api/media/cover/{token}`、`GET /api/media/events` 均使用既有 Bearer 边界；SSE 按 revision replay、订阅者 latest-wins，保活不重复业务状态。
- 结构/类型/范围错误返回 422，失效或错 flow endpoint 返回 409，平台运行失败保持 `200 success=false`。

### Android

- `AudioEndpoint`、`MediaState` 严格解析；缺 revision、越界 volume、未知 playback 均拒绝。
- `getMediaState/openMediaEvents/getMediaCover` 携带 Bearer；SSE 区分 Eof、NetworkError、HttpError、ClosedByCaller。
- STARTED 内执行 snapshot→since；Eof/网络/5xx 以 1/2/4/8 秒退避，401/403 回配对，旧 generation/base URL/controller 回调丢弃。
- `MediaVolumeActor` 单 in-flight、latest-wins、请求起点间隔至少 100ms，失败回退确认值。
- 专用卡保留无媒体时的音量/设备控件；媒体按钮图标化并具备资源化无障碍文案。

## 验证矩阵

| 验证ID | 类别 | 内容 | 最终状态 |
|---|---|---|---|
| V-SRV-01 | Automated Gate | Windows Python 3.13 x64 固定依赖安装/import | Dev 上游确认通过 |
| V-SRV-02 / V-SRV-03 / V-CUT-01 | Automated | 服务、插件、API/SSE、LAN/clean cutover | 22 passed |
| V-AND-01 / V-AND-02 | Automated | Android Media 协议、生命周期、UI 模型、音量与真实 Spinner View | 29 passed |
| V-BUILD-01 | Automated | Android `assembleDebug` | 38/38 actionable tasks 成功 |
| V-MAN-01..05 | Manual | Windows 真实媒体/Core Audio；Android 真机网络、视觉、TalkBack、撤销 key | Manual pending |

## 可落地主路径

1. 固定并验证 WinRT/pycaw 依赖。
2. 实现单线程媒体服务与真实 Windows adapter。
3. clean cutover 为唯一 `media` 插件并显式装配。
4. 建立 state/cover/SSE 协议与 replay。
5. Android 落地严格协议、生命周期、专用卡和音量 actor。
6. 自动化与构建通过后同步 README、规范源和本地 docs；真机项保持 Manual pending。

## 风险

- `IPolicyConfig` 是 Windows 未公开稳定接口，真实设备行为仍需 Manual。
- GSMTC 播放器差异、Core Audio endpoint、Android 后台网络和 TalkBack 只能由真实环境最终验收。
- HTTP 仍仅适合可信局域网；公网安全不在本需求范围。

## R1 supersession：媒体初始化不阻断启动

- `SUPERSEDES`: 本父需求原始启动契约及子任务 01 设计中的“媒体 readiness 作为 lifespan 前置条件”表述；权威补充为 `local://se-analysis-reopen-media-startup.md`。
- 根因：旧 `MediaService.start()` 在约 5 秒后抛出 `TimeoutError`，异常穿透 FastAPI lifespan，uvicorn 随之退出。
- R1 方案：deadline 后发布短错并保留后台 bootstrap；晚完成同进程清错恢复，HTTP `/ping` 始终可达。
- R1 状态：唯一子任务 REQ-20260714-01-01 的测试补充已完成；生产代码未修改；Reviewer-2 PASS；V-START-01..06 Automated Pass，V-MAN-01/02 Manual pending。

## R2 用户缺陷返工闭环

- 根因：媒体初始化 attempt 超时后未形成串行、可取消且可等待的生命周期，可能永久停留 timeout；Android 需以 revision/generation 隔离迟到状态并以权威 error 覆盖显示错误。
- 修复：单个 active attempt；首次 deadline 后取消并等待，再 retry；HTTP 继续；后续成功 `_publish_error(None)`；Android 成功清除历史错误、当前失败继续显示。
- 状态：REQ-20260714-01-01 已完成 Automated；REQ-20260714-01-02 已完成 Automated；两者真实 Windows/真机项 Manual pending。
- R2 验证：Server/API 20 passed；Android Media 单测与 `assembleDebug` 通过；emulator-5554 UI 无历史 timeout。
- 非目标：真实 Windows GSMTC/Core Audio 未验收；docs 不提交、不 push。

G-R2-01=PASS
 
## R3 媒体可靠性问题发现与返工时间线（2026-07-15）

- 审查确认四项可靠性问题：FastAPI event loop 被同步媒体命令阻塞；运行期 Windows adapter 失效后不重建；封面瞬时失败后不重试；Android `EzApiClient` 媒体 scope 缺少关闭路径。
- 首次真实 E2E 仍复现媒体初始化超时。A/B 两轮返工定位到：初始化需 0.5s deadline；GSMTC 属性/thumbnail 读取存在约 0.8s 阻塞；Core Audio 读取约 0.8s，旧生命周期会将这些延迟表现为永久 timeout。
- 第三轮真实 Server→Android 复测关闭原始 P0：连续 state 采样 `available=true,error=null`，Android 控制页无初始化超时；Server targeted tests 27 passed，Android targeted BUILD SUCCESSFUL。
- 尚未完整验收：V-02/V-03/V-04 未执行；V-07 为 Manual pending；V-01 未注入可控慢命令；V-06 的 SSE 内容更新及自动恢复未完整验证。
- 当前总体状态保持“部分 E2E 通过，未完整验收；Manual pending”。

## Spotify 多会话修复状态同步（2026-07-15）

- REQ-20260714-01-01 Windows：Automated Pass（S-01~S-06、28 tests、compileall）；真实多会话/暂停同步/三键通过；封面 `cover=null` blocking；Android 命令闭环 Manual pending。
- REQ-20260714-01-02 Android：标题/艺术家已观察，完整命令闭环 Manual pending。
- 旧 18080 固定端口问题为环境错配，已撤回，不计入当前产品问题。
- 总体：代码待提交；验收未完成；Manual pending。
***
## COVER-MTA 修复状态（2026-07-16）

- 模块级预载 `comtypes`；EzMediaLoop 在线程内显式 `COINIT_MULTITHREADED` init/uninit，失败初始化不误反初始化；manager token 逐项回滚。
- COVER-MTA 子任务：Automated 已完成；Reviewer 复审 PASS with notes；T-003 服务端封面阻塞已关闭。
- 真实 Evidence：服务 PID 32752；B站 title 正常、volume=56、5 render、8 capture；cover URL 非空、HTTP 200、`image/png` 20945 bytes 且可解码；播放/音量往返命令 success；日志无 `RPC_E_CHANGED_MODE`/COM/Traceback/ERROR/异常/失败。
- Android 封面页面实际显示未由用户确认，V-04 保持 **Manual pending**；总体不得叙述为已完成/已可用。

## R5 事件驱动媒体与 Android UI 重构（2026-07-16）

### 增量契约与文件清单

- `request_refresh(domains) -> Future[MediaState]` 合并 dirty，按 devices→audio→media→artwork 执行并不等待 artwork；`POST /api/media/refresh` 保持 Bearer 边界，成功返回 `MediaState`，不可用返回 503 短错。
- 原子 SSE 在 event loop 内先注册 queue 再取得 snapshot/replay；Windows callback 仅 thread-safe 标记 dirty，并由 `EzMediaLoop` MTA 线程持有/释放。
- Artwork identity 为 `(source_app_user_model_id,title,artist)+generation`，切歌先发布 `cover=null`，同 generation 只读一次；Android onOpen、STARTED/恢复、媒体/音量/设备命令后主动 refresh，旧 generation 不得回写。
- Android UI 使用编程式 View：深色 Material BottomSheetDialog、FrameLayout 固定 Header、top-end 设备浮层 rename/delete 与删除确认。涉及 `media/service.py`、`agent/api.py`、Android `EzApiClient.kt`/`MediaConnectionController.kt`/`MainActivity.kt`/`ControlScreen.kt`、资源与定向测试；不修改 `activity_control.xml`、docs 以外代码范围及 `.omp`。

### R5 验证与子任务状态

- Server 定向测试 45 passed；受控 `/ping`、state、refresh 均 200，空闲 10 秒 revision 4→4 且无重复媒体读取；Android `testDebugUnitTest assembleDebug` BUILD SUCCESSFUL。
- emulator-5554 已安装启动并实际显示媒体卡；BottomSheet 已实际打开。R5-AND-001 首轮 Blocking/P1 已关闭：独立 Robolectric 测试验证实际 Activity/root attach、`isAttachedToWindow`、入口 `VISIBLE`、`contentDescription/clickable/focusable`，祖先 `VISIBLE` 且非 `NO_HIDE_DESCENDANTS`。
- 子任务 REQ-20260714-01-01、REQ-20260714-01-02：Automated Pass；Windows callback/真实设备浮层 rename/delete、TalkBack、当前设备删除与导航均 Manual pending。

### R5 完成叙事

| 栏 | 状态 |
|---|---|
| Automated | Server 45 passed；受控 API/idle revision 证据；Android 单测、assembleDebug 与 emulator 媒体卡/BottomSheet 路径通过。 |
| Manual | Windows callback/真实播放音量、设备浮层 rename/delete、TalkBack、当前设备删除确认与导航：**Manual pending**；BottomSheet 已打开。 |
| 非目标 | Web、formatter、lint、项目级全套测试、commit/push。 |
***

## R6 最终增量与状态（2026-07-16）

- 子任务 01 已完成：Core Audio callback QueryInterface 与注册/注销使用同 pointer；endpoint 重绑定先注册新后注销旧；volume callback 仅标记 audio dirty。真实受控 launch port 18937 两轮通过：80→65→80（revision 4→5，媒体不变）；Focusrite→INZONE→Focusrite，INZONE 音量 60，最终恢复 80（revision 5→8→9），无“读取音频状态失败”或“Interface not supported”。
- 子任务 02 已完成 Automated/UI Evidence：Popup 实测 `control_device_row`、本机 chip、rename/delete `ImageButton`，无按钮文本，触控区 126px；Android View/testDebugUnitTest/assembleDebug 成功。重命名/删除提交与 TalkBack 仍为 Manual pending。
- R6 验证矩阵：Server 三媒体回归 47 passed/3 warnings；callback 专项 2 passed；Windows 两项真实通过；Android Popup Evidence 通过。总体不再保留 R6 Windows Manual pending。
