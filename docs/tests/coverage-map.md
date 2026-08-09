# EzWinCommand 长期业务验收地图

本地图记录必须跨任务持续守住的高风险业务路径、适合的验证层级和当前证据缺口。普通单元测试目录、类名和短期执行报告不在此维护；代码覆盖率只作为诊断指标。

| 验收路径 | 必须保持的结果 | 最低验证层级 | 当前证据与缺口 |
|---|---|---|---|
| Server 发现与身份确认 | 发现结果必须经 Server 身份确认；地址变化不应被误判为新 Server；过期发现回调不能覆盖当前扫描 | Server/Android contract + 真实网络 | 自动化覆盖协议与状态；真机、路由器和防火墙组合仍需环境验证 |
| 配对请求生命周期 | 远端不能读取真实配对码；失败、锁定、取消和过期不产生设备权限；成功只建立一个设备关系 | Server/Android contract | 自动化覆盖主要状态；PC 多请求呈现和 Android 生命周期需保留 UI/E2E 门禁 |
| Android 配对恢复 | 重复提交、页面重建或暂时失败不得产生幽灵设备；失败后用户可修正输入，成功且安全保存后才进入控制状态 | Android state/UI + Server contract | JVM/Robolectric 有覆盖；视觉、输入法和 TalkBack 仍需设备或模拟器验证 |
| 设备会话与撤销 | 有效会话可在重启后恢复；撤销成功使请求和活动流失效；撤销失败不误删仍有效的本地会话 | Cross-platform contract + UI/E2E | 自动化覆盖存储、鉴权和撤销；真实 Keystore 与跨设备撤销需环境验证 |
| 本地管理安全边界 | 配对码和设备管理只对 PC 本机开放；管理事件不携带敏感值；断线后以权威快照恢复 | Server interface + Web browser | 接口与静态契约有覆盖；真实浏览器断线及多配对卡交互仍需 UI 验证 |
| 插件加载与启用边界 | 只有已启用且成功加载的本地受信任插件动作可执行；单个插件失败不破坏其他能力 | Server interface | 自动化应覆盖禁用、加载失败和动作可见性；远程插件分发不属于验收范围 |
| 异步命令生命周期 | 任务所有者隔离、重复提交收敛、重启和过期产生明确状态，公开结果不泄露内部诊断 | Server/Web/Android contract | 自动化覆盖 Server 与客户端状态；真实浏览器 soft timeout 和 Android 断网恢复仍需 E2E |
| 媒体启动与恢复 | Windows 媒体初始化、超时、迟到成功和重建不能阻断基础 HTTP；资源只按所属生命周期关闭 | Server unit/interface + Windows environment | Automated：覆盖事件驱动 idle、初始化超时与可取消指数退避、adapter 清理，以及媒体失败时 HTTP、设备和动作 API 仍可用；真实 GSMTC/Core Audio 故障恢复仍需环境验证 |
| 媒体快照与事件同步 | Snapshot 与 SSE 之间不丢变化；修订号单调；慢客户端和断线恢复得到最新状态；旧封面不能回写 | Cross-platform contract + UI/E2E | Server/Android 自动化覆盖主要状态；真实播放器、封面与长时间断线仍需环境验证 |
| 音频设备控制 | 没有活动媒体时音量和输入、输出设备仍可控制；平台回调只更新相关状态且设备切换后继续有效 | Server unit/interface + Windows environment | 替身覆盖接口；真实 Core Audio 设备、角色与 callback 重绑定仍需环境验证 |
| 电竞模式进入与退出 | 进入按受控顺序执行并在首个失败处停止；退出恢复音频并只关闭受管进程，不结束游戏平台 | Server unit + Windows environment | 自动化覆盖顺序与失败停止；YY、Steam、CS2 和真实音频设备的完整链路待环境验证 |
| Windows 生命周期集成 | 托盘、防火墙、自启和退出行为在当前登录用户会话内一致，提权或外部命令失败可诊断且不伪成功 | Windows environment | 普通替身测试不能替代 UAC、防火墙、登录启动和托盘交互验证 |
| OLED 护屏与输入取消 | 用户点击后显示 5 秒倒计时并关闭显示器；显示器重新亮起后启动 60 秒倒计时并可无限循环；任意键盘 Key Down 或倒计时窗口“取消”按钮结束整个流程，鼠标移动和普通点击不取消；不使用 Sleep/Hibernate，Server 重启不主动改变显示器状态 | Server unit/interface + Android UI + Windows environment | Automated：Server 单测覆盖状态机循环、5/60 秒定时器、键盘 Key Down 去重、鼠标忽略、取消按钮、显示器电源通知去重、重复点击和关闭清理；Android JVM 覆盖单一矩形进入按钮。Automated Windows smoke：Raw Input、显示器电源通知和 Win32 倒计时窗口启动/停止及控制器资源清理成功。Manual — 待人工验证：真实显示器黑屏/亮起、键盘/鼠标唤醒差异、多显示器行为，以及 Android 真机/模拟器跨端交互。 |

## 证据规则

- 自动化通过只证明其实际覆盖的层级，不能替代真实 Windows、真实网络或 UI 行为。
- 环境验证必须记录运行身份、关键输入、可复核输出和未执行项；敏感设备密钥、配对码及本机身份文件不得进入证据。
- 产品原则或高风险路径发生变化时更新本地图；仅重命名测试文件或调整内部实现无需修改。
