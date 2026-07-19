# R3 媒体插件可靠性修复追加报告（2026-07-15）

## Automated

- Server targeted tests：27 passed。
- Android targeted BUILD SUCCESSFUL；APK 安装成功。
- V-02/V-03/V-04：未执行，不等同于通过。

## Manual

- V-07：Manual pending；真实播放器控制、设备切换与休眠恢复未执行。

## 非目标

- 未运行 formatter、lint、项目级全套测试；未 commit/push；docs 仅本地归档。

## 真实 Server→Android 第三轮

- 第三轮连续 state 采样 `available=true,error=null`，返回真实媒体标题/艺术家/音量/设备；Android 控制页无初始化超时，前后台无崩溃。
- 原始 P0 初始化超时已关闭；SSE 内容更新及自动恢复未完整验证。

## 结论

部分 E2E 通过，未完整验收；Manual pending。

## R2 追加验证（2026-07-14）

| 验证ID | 检查项 | 结果 | 证据 |
|---|---|---|---|
| V-R2-SRV | Server 媒体/API 聚焦 | 通过 | `python -m pytest tests/test_media_service.py tests/test_media_api.py -q`：20 passed |
| V-R2-AND | Android Media 行为与 revision/generation | 通过 | `testDebugUnitTest --tests *Media*` BUILD SUCCESSFUL |
| V-R2-BUILD | Debug APK | 通过 | `:app:assembleDebug` BUILD SUCCESSFUL；APK 已安装 |
| V-R2-EMU | emulator-5554 媒体卡恢复 | 通过 | 10.0.2.2:8765 `/ping` 正常；UI hierarchy 无“媒体服务初始化超时”；logcat 无 FATAL |

R2 用户缺陷复现基线：隔离 8765 API revision=1、SSE 无事件，模拟器可见 timeout；修复后成功状态自动清错且当前错误仍保留。

## R2 完成叙事

| 栏 | 状态 |
|---|---|
| Automated | Server 20 passed；Android Media 测试通过；Debug APK 构建通过；emulator UI 路径通过。 |
| Manual | 真实 Windows GSMTC/Core Audio：Manual pending。 |
| 非目标 | 真实 Windows 控制未验收；docs 仅本地不提交；不 push；不执行 formatter/lint/全套测试。 |

# 测试报告: REQ-20260714-01

- **日期**: 2026-07-14
- **Tester**: MediaRetest
- **结论**: Automated Pass；Manual pending

## Automated

| 验证ID | 命令/范围 | 结果 |
|---|---|---|
| V-SRV-02 / V-SRV-03 / V-CUT-01 | `python -m pytest tests/test_media_service.py tests/test_media_plugin.py tests/test_media_api.py tests/test_android_lan_contract.py -q`（服务端目录） | 22 passed，0 failed；1 条第三方弃用 warning |
| V-AND-01 / V-AND-02 | `gradlew.bat :app:testDebugUnitTest --tests "*Media*" --no-configuration-cache --rerun-tasks`（Android 目录） | 29 tests，0 skipped/failures/errors；BUILD SUCCESSFUL |
| V-BUILD-01 | `gradlew.bat :app:assembleDebug --no-configuration-cache --rerun-tasks` | BUILD SUCCESSFUL；38/38 actionable tasks 成功 |

Automated 覆盖 snapshot→SSE 与退避、generation/Main/page gate、SSE framing/termination、音量 actor 与 busy 合并、设备 pending、COM/PolicyConfig 生命周期与顺序、封面 token/replay/鉴权撤销、严格 wire 和媒体卡契约。

## Manual

| 验证ID | 检查项 | 状态 |
|---|---|---|
| V-MAN-01 | Windows 真实 GSMTC 媒体与三键控制、无媒体卡 | Manual pending |
| V-MAN-02 | 真实 Core Audio 音量、render/capture endpoint 与部分失败日志 | Manual pending |
| V-MAN-03 | Android 真机前后台、断网恢复、snapshot→replay | Manual pending |
| V-MAN-04 | 320dp/≥600dp 视觉与 TalkBack | Manual pending |
| V-MAN-05 | 撤销真实 device key 后 SSE/封面授权失效 | Manual pending |

## 问题

| ID | 归属 | 描述 | 严重程度 | 状态 | 关闭依据 |
|---|---|---|---|---|---|
| T-001 | Android | `configureSpinner` 初始树编译不可解析 | Blocking | 已关闭 | `*Media*` 与 `assembleDebug --rerun-tasks` 成功 |
| T-002 | Android | 连接循环初测仅静态 helper，未覆盖真实 Contract | Blocking | 已关闭 | fake client 驱动真实 controller 覆盖 Eof/NetworkError/5xx/401、snapshot→since、generation/Main/cover |
| T-003 | Android | output/input device wire 缺少精确两 key 回归 | Major | 已关闭 | `MediaCommandRoutingTest` 补充两类 endpoint 命令并通过 |
| T-004 | Android | SSE 后错误重置 retry，持续断线无法指数退避 | Major | 已关闭 | 删除 retry reset；事件后 Eof 行为测试断言 1/2/4 秒 |
| T-005 | Android | 延迟 load identity gate 前可能重复 pending tracking | Major | 已关闭 | `ControlPageGate` 行为测试覆盖 gate 前后、旧 generation、STOP/detached |
| T-006 | Server | PolicyConfig COM interface 未显式、幂等且按序释放 | Major | 已关闭 | 服务测试断言幂等 Release 且早于 `CoUninitialize` |
| A-REV-01 | Android | 双状态可能使 stale volume callback 覆盖设备 pending | Blocking | 已关闭 | `MediaUiBehaviorTest` 覆盖 pending→volume failure/idle 保持→finally 清除 |
| A-REV-02 | Android | selected ID 为空/失效时无法可靠提交首个 endpoint | Blocking | 已关闭 | placeholder + `DeviceSelectionGate`；真实 Spinner 测试断言初始化 0 命令、首 endpoint 精确 1 命令 |
| A-REV-03 | Android | 既有测试未驱动真实 Spinner 与 contentDescription | Major | 已关闭 | Robolectric `MediaControlScreenViewTest` 断言 description、≥48dp、placeholder 与 option description；真实 TalkBack 仍 Manual pending |

无未关闭 Automated blocking 问题。

## 完成叙事

| 栏 | 状态 |
|---|---|
| Automated | Reviewer PASS；服务端 22/22、Android Media 29/29 通过；assembleDebug 38/38 tasks 成功。 |
| Manual | Windows 真实媒体/Core Audio、Android 真机网络/视觉/TalkBack：Manual pending。 |
| 非目标 | 按任务要求未测试 docs/规范；跳过 formatter、lint、项目级全套测试；未 commit/push。 |

**Test Gate：PASS（Automated）；Manual pending。**

## R1 重开：媒体初始化不阻断启动

- Reviewer：`agent://MediaStartupReview-2` **PASS**；首轮两项测试 note 与设计范围 note 已关闭，无 blocking 问题。
- Automated：R1 聚焦服务端测试 20 passed；V-START-01/02/03/05/06 通过；V-START-04 当前源码 APK 构建、安装及 `10.0.2.2:8765` 连接路径通过并到达配对弹窗。
- Manual：V-MAN-01/02 真实 Windows GSMTC/Core Audio 与晚恢复仍为 **Manual pending**，未冒充通过。
- 非目标：本轮不改生产代码，仅补充测试；不执行 formatter、lint、项目级全套测试，不污染 README，不 push。
- R1 根因/契约：旧媒体 readiness `TimeoutError` 穿透 lifespan 导致 uvicorn 退出；R1 废弃该阻断契约，保留后台 bootstrap 并允许晚恢复。

## Spotify 多会话修复追加报告（2026-07-15）

### Automated
- Server S-01~S-06 通过；测试 28 passed；`python -m compileall media/service.py tests/test_media_service.py` exit 0。
- 真实随机端口、单 worker、无 reload：Spotify/Bilibili 多会话选择、暂停同步、三键目标通过。

### Manual
- Android 标题/艺术家与初始按钮语义已观察；完整命令闭环 **Manual pending**。

### 非目标
- 旧固定端口 18080 为环境错配并已撤回；不计为产品问题。未执行测试、formatter、lint、commit/push。

### Blocking
- 真实 Spotify 封面持续 `cover=null`，thumbnail task 无成功结果；需修复后复测，当前未关闭。

### 结论
- 代码待提交；验收未完成；Manual pending。

## 2026-07-16 封面遗留风险归档

### Automated
- 本次仅归档文档，未运行测试；既有 Server/Android 自动化证据保持原记录。
- 现场证据：Spotify 128272-byte PNG、Edge/B站 25046-byte PNG 均可由显式 MTA 探针取得；当前 STA 服务的 `open_read_async` 挂起。

### Manual
- Android 完整命令闭环：**Manual pending**。

### 非目标
- 不修改产品代码、测试、README、`.omp`；不运行 formatter、lint、测试、git commit/push。docs 仅本地归档，未获提交授权。

### 结论
- T-003 改列为遗留风险/下一轮立即修复；用户仅授权本次 `COMMIT_CODE` 两份代码文件还原点提交例外，不代表业务验收完成。

## 2026-07-16 COVER-MTA 修复追加

### Automated
- Automated：41 passed，3 warnings，13.87s；Reviewer 复审 PASS with notes。
- COVER-MTA：模块级主线程预载 `comtypes`；EzMediaLoop 显式 MTA init/uninit；manager token 逐项回滚；T-003 服务端封面阻塞关闭。

### 真实 Evidence
- 服务 PID 32752；B站 title 正常、volume=56、5 render、8 capture。
- cover URL 非空，HTTP 200，`image/png` 20945 bytes，可解码。
- 播放 `playing→paused→playing`，两次命令 success；音量 `56→55→56`，命令 success。
- 日志筛查无 `RPC_E_CHANGED_MODE`、COM、Traceback、ERROR、异常、失败。

### Manual
- Android 页面实际封面显示未经用户确认，精确状态：**Manual pending**。

### 非目标
- 不修改 HTTP/JSON/SSE 或 Android UI；docs 未获提交授权；不运行 formatter/lint/测试/git；不 commit/push。

### 结论
- T-003 服务端封面阻塞已关闭；Android 封面显示仍 Manual pending，本需求未宣称已完成/已可用。

## R5 事件驱动媒体与 Android UI 重构（2026-07-16）

### Automated

- Server：`tests/test_media_service.py`、`test_media_api.py`、`test_media_plugin.py` 定向测试 45 passed，3 warnings。
- 受控服务：`/ping`、state、`POST /api/media/refresh` 均 200；空闲 10 秒 revision 4→4，日志无重复媒体读取。
- Android：`testDebugUnitTest assembleDebug` BUILD SUCCESSFUL；emulator-5554 实际显示媒体卡，BottomSheet 已实际打开。
- R5-AND-001 已关闭：独立 Robolectric 测试在实际 Activity/root attach 层级验证 `isAttachedToWindow`、`VISIBLE`、入口 `contentDescription/clickable/focusable`，祖先均 `VISIBLE` 且非 `NO_HIDE_DESCENDANTS`；指定测试和 assembleDebug 成功。

### Manual

- Windows GSMTC/Core Audio callback 与真实播放/音量命令、真实设备浮层 rename/delete、TalkBack、当前设备删除确认与导航：**Manual pending**。
- BottomSheet 已实际打开，不属于 Manual pending。

### 非目标

- Web、formatter、lint、项目级全套测试、commit/push。

### 结论

Automated Pass；无未关闭 Automated blocking 问题；整体仍 Manual pending，不宣称已完成或已可用。
***

## R6 最终真实验证（2026-07-16）

### Automated

- Server 三媒体回归：`python -m pytest -q tests/test_media_service.py tests/test_media_api.py tests/test_media_plugin.py`，**47 passed，3 warnings**。
- callback 专项：2 passed；覆盖 QueryInterface 同 pointer、先注册新 endpoint 后注销旧 endpoint，以及 volume callback 仅 audio dirty。
- Android MediaControlScreenViewTest、`testDebugUnitTest`、`assembleDebug`：BUILD SUCCESSFUL。

### Android Evidence

- emulator-5554 为 `device`；通过 `content-desc=设备管理` 实际打开 Popup，观察到 `control_device_row`、本机 chip、rename/delete `ImageButton`；无按钮文本，触控区 126px。
- Manual 仅重命名/删除提交与 TalkBack：Manual pending。

### Windows Evidence（R6，真实 Pass）

- 受控 launch `127.0.0.1:18937`。第一轮默认 Focusrite：音量 80→65→80，revision 4→5，媒体字段不变。
- 第二轮 Focusrite→INZONE→Focusrite：INZONE 音量 60，最终恢复 Focusrite 音量 80，revision 5→8→9；无“读取音频状态失败”或“Interface not supported”，服务已 stop。
- R6-AUDIO-REBIND 与 R6-VOLUME-PUSH 均真实 Pass；R5 旧记录中的 Windows Manual pending 仅代表 R5 当时未执行状态，不适用于 R6。

### 非目标

Web、formatter、lint、项目级全套测试、commit/push；不修改代码/README/.omp。

### 结论

R6 自动化、Windows 两项真实闭环及 Android Popup Evidence 通过；无未关闭 blocking。Android 重命名/删除提交与 TalkBack 仍 Manual pending。
