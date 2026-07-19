# defect-ledger: REQ-20260714-01

> 用户侧 / 契约失配 / 流程跳步 / 否决方案只写本表；测试执行中的实现/断言问题写各子任务 `test-records.md`。

## 缺陷账本

本轮 `USER_DEFECT=yes`，已记录用户反馈“媒体插件经常失效”及原始媒体初始化超时；原始 P0 已由第三轮真实 Server→Android 复测关闭，持续可靠性验证仍部分未执行。

| ID | 来源 | 用户侧 | 描述 | 严重程度 | 状态 | 关闭依据 |
|---|---|---|---|---|---|---|
| U-001 | 用户日志 | 是 | 媒体初始化/首次读取超时抛 `TimeoutError`，导致服务启动失败、`/ping` 不可达 | Blocking | 已关闭 | R1 测试覆盖 hanging initialize、晚恢复及真实 uvicorn `/ping`；第三轮 Server→Android 连续 state `error=null`、Android 无初始化超时 |
| U-002 | 用户 | 是 | 用户反馈“媒体插件经常失效”，表现为初始化 timeout 与媒体状态不可用 | P0 | 已关闭 | R3 修复后 Server targeted tests 27 passed；Android targeted BUILD SUCCESSFUL；第三轮真实路径状态可用 |

`DEFECT_LEDGER=updated`。V-02/V-03/V-04 未执行、V-07 Manual pending，不作为通过；测试实现问题记录于子任务 `test-records.md`。

## COVER-MTA 修复闭环（2026-07-16）

| ID | 来源 | 用户侧 | 描述 | 严重程度 | 状态 | 关闭依据 |
|---|---|---|---|---|---|---|
| T-003 | 用户现场证据 | 是 | STA 服务 `open_read_async` 封面读取挂起，导致服务端 cover 为空 | Blocking | 已关闭 | 模块级预载 `comtypes`，EzMediaLoop 显式 MTA init/uninit，manager token 逐项回滚；真实服务 PID 32752 的 B站 title/volume/devices 正常，cover URL HTTP 200 `image/png` 20945 bytes 可解码；播放/音量往返 success；日志筛查无 COM/RPC_E_CHANGED_MODE/Traceback/ERROR/异常/失败 |

Reviewer 复审 PASS with notes；Automated 41 passed（3 warnings，13.87s）。Android 页面实际封面显示未由用户确认，保持 **Manual pending**；docs 未获提交授权。

`DEFECT_LEDGER=updated`。T-003 服务端阻塞已关闭；Android 用户确认不属于测试问题，继续保留 Manual pending。

## R5 用户缺陷增补（2026-07-16）

用户反馈入账：周期性全量读取造成 revision/log/封面闪烁，并伴随 Spinner/Header/设备管理问题；本轮改为事件驱动 dirty 合并与按域 refresh，修正 UI 入口、BottomSheet 及设备浮层路径。

| ID | 来源 | 用户侧 | 描述 | 严重程度 | 状态 | 关闭依据 |
|---|---|---|---|---|---|---|
| U-R5-001 | 用户 | 是 | 周期全量读取引发 revision、日志与封面闪烁；Spinner/Header/设备管理入口不符合预期 | Blocking/P1 | 已关闭（自动化） | Server 45 passed；受控空闲 10 秒 revision 4→4 且无重复读取；独立 Robolectric 测试验证实际 Activity/root attach、`isAttachedToWindow`、VISIBLE、入口 a11y 属性及祖先 VISIBLE/非 NO_HIDE_DESCENDANTS；assembleDebug 成功 |

真实 Windows callback、设备浮层 rename/delete、TalkBack、当前设备删除确认与导航仍为 **Manual pending**；BottomSheet 已实际打开。`DEFECT_LEDGER=updated`。
***

## R6 用户缺陷增补（2026-07-16）

用户反馈与现场验收拆分为三项独立用户缺陷，均已关闭：

| ID | 来源 | 用户侧 | 描述 | 严重程度 | 状态 | 关闭依据 |
|---|---|---|---|---|---|---|
| U-R6-001 | 用户 | 是 | Android 设备管理 Popup 缺少清晰设备 row/本机 chip，rename/delete 操作入口不符合图标按钮契约 | Major | 已关闭 | emulator-5554 Popup 实测 `control_device_row`、本机 chip；rename/delete 为无按钮文本的 ImageButton，触控区 126px；ViewTest、testDebugUnitTest、assembleDebug 成功 |
| U-R6-002 | 用户 | 是 | Core Audio endpoint 切换 callback 重绑定顺序/pointer 不稳定，可能导致切换失败 | Blocking | 已关闭 | callback 专项 2 passed；QueryInterface 同 pointer、先新注册后旧注销；port 18937 Focusrite→INZONE→Focusrite，revision 5→8→9，无读取音频状态失败或 Interface not supported |
| U-R6-003 | 用户 | 是 | 音量 callback 误触发媒体读取/状态变化，音量更新闭环不可靠 | Major | 已关闭 | callback 测试断言 audio read +1、media read 不增加；真实 port 18937 音量 80→65→80、revision 4→5 且媒体不变；最终音量恢复 80 |

`DEFECT_LEDGER=updated`。R6 Windows 两项为真实 Pass；Android 仅重命名/删除提交与 TalkBack 保持 Manual pending，不影响上述三项缺陷关闭依据。

## R7 用户缺陷增补：LAN 自动发现、PC 配对验证码与缓存（2026-07-17）

本轮关联用户报告覆盖真实手机 LAN 自动发现、防火墙边界、PC 配对验证码显示与多卡隔离、设备列表 404/错误隔离及静态资源缓存版本。`USER_DEFECT=yes`。

| ID | 来源 | 用户侧 | 描述 | 严重程度 | 状态 | 关闭依据 |
|---|---|---|---|---|---|---|
| U-R7-001 | 用户/真实手机 | 是 | 同一 LAN 的 Android 设备无法自动发现或无法完成 identity 请求 | Blocking | 已关闭 | 真实手机 found=1、resolved=1、identity_success=1、servers=1；Server 收到真实手机 `/api/identity` 200；用户确认“发现了” |
| U-R7-002 | 用户/PC 页面 | 是 | PC 配对区域仅显示空蓝框，缺少四位验证码、倒计时及多设备区分；终态可能继续暴露验证码 | Blocking | 已关闭 | 真实 Edge/Playwright 空态、单 pending、多 pending、active+cancelled 四场景通过；多卡验证码数量与 pending 数一致，终态无 code DOM |
| U-R7-003 | 用户/PC 页面 | 是 | PC 初始化请求 `GET /api/devices` 404，并与 pairing 共用错误区造成错误串扰 | Major | 已关闭 | `GET /api/devices` 本机 200、远程未鉴权 401；设备与 pairing 错误隔离；fresh 运行 `/api/devices`、`/api/local/pairings`、`/api/actions` 均 200 |
| U-R7-004 | 用户/浏览器 | 是 | 静态 JS/CSS 缓存导致旧页面/旧配对 UI，即使普通 reload 也不能取得修复版本 | Major | 已关闭 | JS/CSS 使用 `?v=20260717`；HTML `no-cache, must-revalidate`；Edge 冷/热缓存及普通 reload 均命中新版本并渲染 pairing card/code |

### 用户报告、实际与预期

- 实际：手机自动发现链断裂；PC 页面出现空蓝框/404，验证码 UI 缺失或无法区分多 pairing；缓存可能继续加载旧资源。
- 预期：同 LAN 手机可自动发现并通过 identity；PC localhost 面板有明确空态、每个 pending/locked pairing 独立显示设备名、短 ID、四位大号验证码和剩余秒数，终态不显示验证码；设备列表与 pairing 错误独立；普通 reload 获取版本化资源。

### 根因、影响面与修复摘要

- 根因：Zeroconf `ServiceInfo` 缺少可解析地址；防火墙规则未满足 Private/LocalSubnet 的 UDP 5353 与业务 TCP 放行链；多 pairing clean cutover 未迁移旧验证码/倒计时样式与空态；PC 调用不存在的 `/api/devices` 且错误区复用；静态资源无发布版本参数。
- 影响面：真实手机发现、Server identity、PC 配对可见性/安全脱敏、设备初始化错误呈现及浏览器缓存一致性。
- 修复：补齐 publisher 可解析地址与最小防火墙规则；以 class 渲染多 pairing 卡和空态，pending/locked 才创建四位 code，终态不创建 code DOM；提供 `/api/devices` 并隔离错误；HTML 入口 revalidate，JS/CSS 增加统一版本参数。

### 回归证据与关闭状态

- 真实手机同 LAN：`adb-9266d82-qix70O._adb-tls-connect._tcp`，`192.168.31.25` → PC `192.168.31.87`；Zeroconf resolve、identity 200、用户确认“发现了”。
- 真实 Edge/Playwright：空态 0 card/0 code；单 pending 1/1；多 pending 2/2 且同名设备短 ID 不同；active+cancelled 终态仅 active 有 code；轮询约 1 秒。
- 设备与安全边界：本机 `/api/devices` 200、远程未鉴权 401；远程 `/api/local/pairings` 404；mDNS UDP 5353 与业务 TCP 均 Private + LocalSubnet。
- 缓存：带版本 JS/CSS、HTML revalidate，Edge 冷/热缓存及普通 reload 均正常渲染。
- 自动验证：Server 定向回归 `12 passed, 1 warning`；Android `testDebugUnitTest assembleDebug --no-configuration-cache` 为 `BUILD SUCCESSFUL`（46 tasks）。截图与临时日志仅作本地证据，未纳入业务提交。
- Quality Owner 最终结论：`BUG_VERDICT=PASS`；`MANUAL=none`；无 blocking。
- Commit 状态：`pending`（本归档仅更新本地 docs，不提交业务代码；docs 不进入业务 commit）。

`DEFECT_LEDGER=updated`。


## R8 用户缺陷增补：Android 正确配对码保存会话失败（2026-07-18）

`USER_DEFECT=yes`。用户报告：Android 客户端输入正确的四位配对码后提示“保存会话失败”。

### 用户报告、实际与预期

- 实际：服务端已成功完成配对并返回凭据，但 Android 新会话保存失败，用户无法进入插件页或在重启后恢复会话。
- 预期：正确码完成配对后按既有会话格式持久化并进入插件页；重启后直接恢复；错误码继续走原有错误路径且不保存会话。

### 根因、影响面与修复摘要

- 根因：Android Keystore AES/GCM 拒绝调用方提供的加密 IV；协议解析和服务端配对响应不是失败点。
- 影响面：仅影响 Android 新会话的加密保存及后续恢复；历史密文解密路径、协议、权限和安全边界不变。
- 修复：`KeystoreCipher.encrypt` 改由平台生成 IV，并在加密后保存 `cipher.iv`；解密仍使用持久化 IV。会话保存加密异常增加脱敏 traceback 阶段日志，不记录验证码、device key、alias 或密文。

### 回归证据与关闭状态

- 真实 LAN 回归（run_id `pair-session-regression-20260718T120300Z-lan`）：正确码 `POST /api/pairings/{id}/complete` 返回 201，随后 actions/devices/media state 均 200；插件页显示“计算器”“电竞模式”，未出现“保存会话失败”。force-stop/relaunch 后无需重新输入地址或验证码，插件页直接恢复且服务端再次收到相关 200 请求。
- 错误码邻近路径：fresh app data 输入错误四位码，complete 返回 403；重启后仍显示“暂无已配对服务端”，未进入插件页，未形成 session。
- 安全与构建证据：受控 Server 与目标 app UID 日志定向扫描未发现验证码、Bearer、device key 或内部异常泄漏；`ServerSessionStoreTest`、`ConnectionRepositoryCancellationTest`、`EzApiClientTest` 及 Server 定向契约/生命周期检查通过；fresh Android assembleDebug 成功。
- Quality Owner：`BUG_VERDICT=PASS`，`MANUAL=none`；无 blocking。Commit 状态：待 Main 自动提交（本归档仅更新本地 docs，docs 不进入业务代码提交）。

`DEFECT_LEDGER=updated`。

## R9 用户缺陷增补：Android 配对页与插件页内容共存、已配对设备撤销失败（2026-07-18）

`USER_DEFECT=yes`。本轮归档两项已通过真实 Android UI/HTTP 回归的用户 Bug；Quality Owner：`BUG_VERDICT=PASS`，`MANUAL=none`，无 blocking。

### U-R9-001：配对页与插件页内容共存

- 用户报告：Android 配对完成进入插件页后，配对页面内容与插件/控制页面同时显示，页面互斥预期被破坏。
- 实际/预期：修复前真实 hierarchy `D:/Temp/ezbug-pre-success2.xml` 同时包含 `scanStatusText`、`refreshButton`、`historyTitle`、`manualToggle` 等配对页锚点和控制页内容；预期插件页仅显示控制内容，返回配对页仅显示完整配对内容。
- 根因：`activity_main.xml` 将配对内容与 `controlContainer` 放在同一纵向容器中，缺少整体配对页容器；`openControl()` 只隐藏局部控件，未隐藏附近服务、历史服务和手动连接入口。
- 影响面：配对成功、恢复已有会话、从历史会话进入插件页均可能出现内容叠加；修复不改变导航状态机、协议或页面产品语义。
- 修复摘要：增加 `pairingContainer` 包裹现有配对页内容，与 `controlContainer` 保持兄弟容器；`openControl()` 隐藏 `pairingContainer`，`showMainScreen()` 与 `returnToPairing()` 恢复显示。
- 真实回归证据：fresh 初始 hierarchy `D:/Temp/ezbug-post-start.xml` 仅有配对页；真实 `GET /api/identity 200`、`POST /api/pairings 201`、`POST /api/pairings/{id}/complete 201` 后，`D:/Temp/ezbug-post-success.xml` 仅有控制页且不含 `titleText`、`scanStatusText`、`historyTitle`、`manualToggle`；点击“返回配对页”后的 `D:/Temp/ezbug-post-back.xml` 含完整 `pairingContainer` 且不含控制页内容；重启与失败恢复 hierarchy 也验证导航状态正确。Android 定向单测与 `assembleDebug` 均 `BUILD SUCCESSFUL`。
- Commit 状态：待 Main 自动提交（本归档仅更新本地 docs，docs 不进入业务代码提交）。

### U-R9-002：已配对设备删除提示撤销失败

- 用户报告：在设备管理中删除已配对 Android 设备时提示“撤销失败”，设备仍保留，当前会话无法正确结束。
- 实际/预期：修复前真实 access log 记录 `DELETE /api/devices/{device_key} 405 Method Not Allowed`，`GET /api/devices` 仍返回设备；预期鉴权删除成功、设备及其媒体流撤销，删除当前设备后本地 session 清理，失败时不误删会话。
- 根因：Server 只有同路径的鉴权 `PATCH` 重命名路由，缺少客户端调用所需的 `DELETE /api/devices/{device_key}`；客户端成功撤销当前设备后原实现未清理本地持久 session，失败分支还会无条件 reload。
- 影响面：所有 Android 设备撤销均因 Server 路由缺失失败；当前设备撤销后的重启恢复、活动 SSE 媒体流和失败状态一致性受到影响。
- 修复摘要：Server 新增鉴权 DELETE，复用 `AuthManager.remove_device()`，成功时按 SHA-256 摘要调用既有 `MediaEventHub.revoke(digest)` 并返回 `{success}`；Android 仅在成功撤销当前设备后调用 `ConnectionRepository.removeSession(serverId)` 并返回配对页；失败立即显示既有简短错误“错误：撤销失败。”，不删除本地 session、不执行误导性 reload。
- 真实回归证据：真实 UI 语义路径“设备管理 → 删除设备“Android” → 确认删除”触发 `DELETE /api/devices/{truncated-device-id} 200 OK`，随后 `GET /api/devices` 返回 `devices: []`；UI 返回配对页，force-stop/relaunch 后仍为配对页且无已配对服务端。停止受控 Server 后执行同一路径显示“错误：撤销失败。”，未进入成功/本地删除分支；Server 恢复后重启显示 `D:/Temp/ezbug-post-failure-recover.xml` 控制页，证明失败未误删 session。Server `tests/test_android_lan_contract.py`：8 passed（1 warning）；Android 定向验证与 `assembleDebug`：`BUILD SUCCESSFUL`。
- Commit 状态：待 Main 自动提交（本归档仅更新本地 docs，docs 不进入业务代码提交）。

`DEFECT_LEDGER=updated`。本次仅追加用户缺陷记录，未改写原 Acceptance、Design、Quality Plan 或原完成状态；docs 保持本地。