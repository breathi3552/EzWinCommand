# EzWinCommand 测试覆盖矩阵

业务覆盖是交付门禁；行/分支覆盖率只作为诊断指标。用例随产品演进维护，过时用例应修改或废弃。

| 用例 ID | 模块/功能点 | 层级 | 自动化实现或状态 |
|---|---|---|---|
| TC-PAIR-001 | PAIR-01/02 配对生命周期 | Server interface | `EzWinCommand-server/tests/test_pairing_lifecycle.py` |
| TC-AUTH-001 | AUTH-01/02 鉴权、撤销与流终止 | Server interface | `EzWinCommand-server/tests/test_pairing_lifecycle.py` |
| TC-WEB-LOCAL-001 | PAIR-01/AUTH-04 本机管理事件、敏感边界与空闲无轮询 | Server interface/static contract | `EzWinCommand-server/tests/test_android_lan_contract.py` |
| TC-CMD-001 | CMD-02/03 同步与异步命令 | Server interface | `EzWinCommand-server/tests/test_async_command.py` |
| TC-MEDIA-001 | MEDIA-01/02/03 媒体状态、控制与事件 | Server unit/interface | `test_media_service.py`, `test_media_api.py`, `test_media_plugin.py` |
| TC-AUDIO-001 | AUDIO-01 音量与设备 | Server unit/interface | `test_media_service.py`, `test_media_api.py` |
| TC-ANDROID-001 | ANDROID-CONN/PAIR/SESSION | Android JVM/Robolectric | `app/src/test/.../network`, `state`, `storage` |
| TC-ANDROID-002 | ANDROID-MEDIA/AUDIO UI 行为 | Android JVM/Robolectric | `app/src/test/.../ui/control` |
| TC-XPLAT-001 | XPLAT-PAIR/AUTH 协议 | Cross-platform contract | Server `test_android_lan_contract.py` + Android network tests |
| TC-XPLAT-002 | XPLAT-MEDIA/SSE wire 与恢复 | Cross-platform contract | Server media API tests + Android media/network tests |
| TC-E2E-001 | Web 生成配对码 → Android 配对 → 控制页 | Android UI/E2E | 自动化框架待建设 |
| TC-E2E-002 | 媒体/音量/设备真实控制 | AI 辅助/人工 | Windows + Android 真实环境；待人工验证 |
| TC-WIN-001 | 防火墙、UAC、自启、托盘 | AI 辅助/人工 | Windows 真实环境；待人工验证 |

## 待建设

- Android 模拟器 + 真实 Server 的稳定 UI 自动化驱动层。
- Web 管理端 UI 自动化。
- Python 与 Android 覆盖率采集和趋势输出。
- AI 环境测试的证据目录、脱敏和结果格式。
