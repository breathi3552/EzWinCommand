# 测试记录: REQ-20260714-01-02

| ID | 描述 | 严重程度 | 状态 | 关闭依据 |
|---|---|---|---|---|
| T-001 | `configureSpinner` 初始树编译不可解析 | Blocking | 已关闭 | `*Media*` 与 `assembleDebug --rerun-tasks` 成功 |
| T-002 | 连接循环初测仅静态 helper，未覆盖真实 Contract | Blocking | 已关闭 | fake client 驱动真实 controller 覆盖 Eof/NetworkError/5xx/401、snapshot→since、generation/Main/cover |
| T-003 | output/input device wire 缺少精确两 key 回归 | Major | 已关闭 | `MediaCommandRoutingTest` 补充两类 endpoint 命令并通过 |
| T-004 | SSE 后错误重置 retry，持续断线无法指数退避 | Major | 已关闭 | 删除 retry reset；事件后 Eof 行为测试断言 1/2/4 秒 |
| T-005 | 延迟 load identity gate 前可能重复 pending tracking | Major | 已关闭 | `ControlPageGate` 行为测试覆盖 gate 前后、旧 generation、STOP/detached |
| T-007 / T-010 | `activeReadyState` 与音量失败/idle 回调可能覆盖设备 pending | Blocking | 已关闭 | `MediaUiBehaviorTest` 覆盖 pending→volume failure/idle 保持→finally 清除 |
| T-008 | selected ID 为空/失效时无法可靠提交首个 endpoint | Blocking | 已关闭 | placeholder + `DeviceSelectionGate`；初始化 0 命令、首 endpoint 精确 1 命令 |
| T-009 | 既有测试未驱动真实 Spinner 与 contentDescription | Major | 已关闭 | Robolectric `MediaControlScreenViewTest` 验证真实 View；TalkBack 仍 Manual pending |

本子任务无未关闭 Automated blocking 问题。真机网络、视觉、TalkBack 与撤销 key 验证为 Manual pending。
| R2-AND-001 | 媒体恢复路径需防旧 revision/generation 回写并清除历史初始化错误、保留当前失败 | Major | 已关闭 | Android `*Media*` 单测、Debug APK 构建成功；emulator-5554 UI hierarchy 无“媒体服务初始化超时”，logcat 无 FATAL |

本轮无未关闭 Automated blocking 问题；真实 Windows GSMTC/Core Audio 与 Android 真机视觉/TalkBack 仍 Manual pending。
 
| R3-AND-001 | 媒体 scope/SSE close 与封面重试可靠性修复 | Major | 已关闭 | Android targeted BUILD SUCCESSFUL；生命周期与封面行为由 targeted tests 覆盖 |
本轮 V-04 未执行；V-07 Manual pending。

## COVER-MTA 依赖验证（2026-07-16）

本轮 Android 未修改代码；Windows 服务端 T-003 已关闭并提供可解码 cover URL。Android 页面实际封面显示未经用户确认，状态为 **Manual pending**；无新增 Automated blocking 问题。

| R5-AND-001 | Android 控制页 Header 设备入口无可访问节点；设备选择仍暴露 Spinner 语义（首轮） | Blocking/P1（首轮） | 已关闭（代码自动化）；真实 UI/TalkBack Manual pending | 独立 MediaControlScreenViewTest + assembleDebug 通过；测试断言 Button、contentDescription/clickable/focusable、BottomSheet 点击路径；生产 grep 确认无 Spinner。emulator-5554 uiautomator 环境持续 idle failure，rename/delete 视觉与 TalkBack 保持 Manual pending |

| R5-AND-001 | Header 设备入口层级可访问性与 BottomSheet 路径（首轮 Blocking/P1） | Blocking/P1 | 已关闭（自动化）；真实设备项 Manual pending | 独立 Robolectric `MediaControlScreenViewTest` 验证实际 Activity/root attach、`isAttachedToWindow`、入口 `VISIBLE`、`contentDescription/clickable/focusable`，祖先均 `VISIBLE` 且非 `NO_HIDE_DESCENDANTS`；指定测试与 assembleDebug BUILD SUCCESSFUL。真实设备浮层 rename/delete、TalkBack、当前设备删除导航仍 Manual pending |

本轮无未关闭 Automated blocking 问题；BottomSheet 已实际打开。
***

| R6-AND-001 | Popup 设备 row、本机 chip、rename/delete 图标按钮可访问性与触控尺寸 | Major | 已关闭（Evidence） | emulator-5554 实测 `control_device_row`、本机 chip；两个 `ImageButton` 无按钮文本、126px；ViewTest/testDebugUnitTest/assembleDebug 成功 |

R6 无未关闭 Automated blocking 问题；重命名/删除提交与 TalkBack 为唯一 Manual pending 项。
