# REQ-20260714-01: Android 媒体与音频控制合并

- **日期**: 2026-07-14
- **版本**: v0.2
- **流程**: Full
- **变更类型**: protocol | platform | behavior
- **USER_DEFECT**: yes
- **R3 状态**: 部分 E2E 通过，未完整验收；Manual pending
- **R3 用户缺陷**: 用户反馈“媒体插件经常失效”；原始媒体服务初始化超时已由真实 Server→Android 第三轮复测关闭。
- **R3 验证**: Server targeted tests 27 passed；Android targeted BUILD SUCCESSFUL；V-02/V-03/V-04 未执行；V-07 Manual pending。
- **Reviewer**: R3 代码审查通过（以本轮审查报告为准）；整体仍 Manual pending
- **Tester**: 第三轮真实 Server→Android 路径部分通过；SSE 内容更新及自动恢复未完整验证

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
- [ ] V-MAN-01..05 Windows/Android 真机与无障碍验证：Manual pending。

## 完成叙事

| 栏 | 状态 |
|---|---|
| Automated | R2 Server/API 20 passed；Android Media 测试通过；`assembleDebug` 成功；emulator-5554 UI 路径通过。 |
| Manual | 真实 Windows GSMTC/Core Audio：**Manual pending**。 |
| 非目标 | 真实 Windows 控制未验收；Web 完整媒体卡、formatter、lint、项目级全套测试、docs 提交、commit/push 均非本轮范围。 |
 
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
