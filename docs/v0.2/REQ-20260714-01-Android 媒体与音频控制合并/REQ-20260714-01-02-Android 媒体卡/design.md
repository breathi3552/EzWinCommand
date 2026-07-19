# 设计: REQ-20260714-01-02

- **子需求**: Android 媒体协议、生命周期与专用媒体卡（R2 错误恢复）
- **日期**: 2026-07-14
- **Dev**: MediaAndroidDev / MediaTimeoutReplacement

## 涉及文件

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `app/build.gradle.kts` | 修改 | 显式 lifecycle runtime ktx |
| `app/src/main/java/**/model/ApiModels.kt` | 修改 | 严格 wire 数据模型，MediaState revision |
| `app/src/main/java/**/network/EzApiClient.kt` | 修改 | Bearer state/cover/SSE 与严格解析 |
| `app/src/main/java/**/ui/control/Control{Models,Controller,Screen}.kt` | 修改 | Ready 媒体状态、命令路由与专用卡 |
| `app/src/main/java/**/ui/control/Media{Volume,Connection,DisplayState}.kt` | 新增/修改 | actor、snapshot→SSE 生命周期、revision/generation、权威 error 合并 |
| `app/src/main/java/**/MainActivity.kt` | 修改 | STARTED 生命周期、页面 identity gate 与失效顺序 |
| `app/src/main/res/**` | 修改/新增 | 可见/无障碍文案、尺寸与媒体图标 |
| `app/src/test/java/**/*Media*Test.kt` | 新增/修改 | 严格解析、SSE、生命周期、actor、卡片、revision 与 error 行为测试 |

## 契约履行

- REST/SSE wire 与导出接口不变；`MediaState.revision` 单调，旧 generation/revision 事件不得回写。
- 权威成功状态的 `error=null` 清除历史初始化错误；权威当前失败继续显示，不继承 displayed 旧错误。
- 连接循环每轮 snapshot→since，重试 1/2/4/8 秒；页面/controller/base URL identity 隔离旧回调。
- STOPPED、返回配对页、切换地址与 destroy 先使旧 generation 失效，再关闭 SSE、load 和音量 actor。
- 音量拖动原地更新，actor 单 in-flight/latest-wins；设备 pending 独立维护。

## 环境与限制

- Android API 23，使用现有 `HttpURLConnection`、AndroidX 与 kotlinx.coroutines；不引入第三方 EventSource。
- 不持久化封面 bytes，不记录或展示 Bearer。
- Windows/Android 真机网络、视觉、TalkBack 与撤销 key 端到端行为为 Manual pending。

## 验证

- `*Media*` 单测通过，覆盖失败→成功清错、当前失败保留及旧 revision/generation 防护；`assembleDebug` 成功；emulator UI 路径通过。
- R2 Tester：Android Media 测试/build 通过，emulator-5554 媒体卡无“媒体服务初始化超时”，logcat 无 FATAL。
- 真实 Windows GSMTC/Core Audio：Manual pending。

[x] revision/generation 防护与权威 error 行为已与最终代码同步。
 
## R3 媒体可靠性修复同步

本轮最终设计清单共 11 个文件；本子任务负责 7 个 Android 文件：`EzApiClient.kt`、`ControlController.kt`、`MediaConnectionController.kt`、`MainActivity.kt` 及对应 `EzApiClientTest.kt`、`ControlControllerTest.kt`、`MediaConnectionControllerTest.kt`。实现显式 close、媒体 scope/SSE 取消、封面有限退避重试及 generation/path 隔离。

Android targeted BUILD SUCCESSFUL；V-04 未执行；V-07 Manual pending。真实 Server→Android 第三轮媒体状态路径部分通过，SSE 内容更新及自动恢复未完整验证。

## 封面遗留风险归档（2026-07-16）

- Windows STA `open_read_async` 挂起导致真实封面仍不可验收；显式 MTA 探针可取得 Spotify 128272-byte PNG、Edge/B站 25046-byte PNG。
- Android 完整命令闭环保持 **Manual pending**，本轮不修改代码。

## COVER-MTA 依赖状态（2026-07-16）

- Android 不改代码；继续消费既有 cover URL。
- Windows 服务端 T-003 阻塞已关闭，真实 cover URL 200 且图片可解码；Android 页面实际显示未由用户确认，保持 **Manual pending**。

## R5 事件驱动媒体与 UI 重构同步（2026-07-16）

- `EzApiClient.kt`/`MediaConnectionController.kt` 增加 onOpen、生命周期与命令后 refresh；`ControlScreen.kt` 使用固定 Header、深色 BottomSheetDialog 及设备浮层 rename/delete；封面以 generation 隔离旧任务。
- Android `testDebugUnitTest assembleDebug` BUILD SUCCESSFUL；emulator-5554 实际显示媒体卡且 BottomSheet 已打开。
- R5-AND-001 已关闭：独立 Robolectric 测试验证实际 Activity/root attach、`isAttachedToWindow`、入口 VISIBLE 与 contentDescription/clickable/focusable，祖先 VISIBLE 且非 NO_HIDE_DESCENDANTS。真实设备浮层 rename/delete、TalkBack、当前设备删除导航仍 Manual pending。
***

## R6 设备 Popup UI 证据（2026-07-16）

- Popup 通过 `content-desc=设备管理` 实际打开；uiautomator 观察 `control_device_row`、本机 chip，以及 rename/delete `android.widget.ImageButton`。
- 两个图标按钮无按钮文本，触控区均 126px（≥48dp）；emulator-5554 为 `device`，Debug APK 安装启动成功。
- MediaControlScreenViewTest、`testDebugUnitTest`、`assembleDebug` 均成功。重命名/删除提交与 TalkBack 保留 Manual pending。
