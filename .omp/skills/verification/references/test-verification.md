# Test verification

## 前置测试分析

用于重需求、新业务路径、跨端契约或高风险修复。只基于需求契约和稳定产品/协议契约设计测试，避免被候选实现牵引。

1. 按模块、特性、功能点和用户路径拆分验证对象。
2. 覆盖正常、边界、失败、恢复、状态迁移、兼容和安全路径。
3. 映射已有验收覆盖，指出需要新增、修改或删除的业务证据。
4. 为每个用例选择单元、接口、UI/E2E、AI 环境或 Manual 层级。
5. 优先稳定、可重复的自动化；不要为了自动化而使用脆弱坐标或伪造环境结论。
6. 输出测试设计给 Main，由 Main 实现脚本并在独立验证前维护验收覆盖。

## 后置测试

1. 根据变更、需求契约和 `docs/tests/coverage-map.md` 选择测试，不仅依赖 Main 提供的命令；资料存在漂移时显式报告。
2. 检查前置测试设计是否落实；业务验收覆盖与当前产品行为是否一致。
3. 先运行单元、接口和构建检查，再运行 UI/E2E。
4. 新需求脚本尚未稳定或真实业务结果难以用固定断言表达时，可以由 AI 操作 Android/Windows 环境并保存可复核证据。
5. 无法自动化的少量路径列为 Manual；不得冒充执行。
6. 以本轮目标、变更面和已识别风险的覆盖充分性作为判断；代码行/分支覆盖率仅作诊断指标。

## EzWinCommand 基线

- Server：在 `EzWinCommand-server` 运行 `python -m pytest`。
- Android unit/Robolectric：在 `EzWinCommand-android` 运行 `./gradlew.bat testDebugUnitTest`。
- Android build：在 `EzWinCommand-android` 运行 `./gradlew.bat assembleDebug`。
- 跨端协议：配对、鉴权、设备、命令和媒体 wire 变化通常验证受影响的两端；纯兼容或单端内部变化可根据证据缩小范围。
- UI/E2E：需要证明真实交互时优先 Android 模拟器 + 可达 Server 主链；localhost、模拟器转发和可信局域网地址都可按场景使用。
- 复杂真实环境操作读取 `skill://e2e-runbook`。

不得仅因现有测试全绿就忽略明显风险，也不得因无法证明绝对完整而自动阻塞。Verifier 应基于本轮目标、diff、仓库事实和可复核证据作专业判断，并说明剩余风险。
