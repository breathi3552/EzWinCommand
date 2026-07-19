# EzWinCommand

EzWinCommand 是可信局域网内的 Windows 控制系统，包含 Python/FastAPI Server、Web 管理端和 Kotlin Android App。核心业务包括配对鉴权、命令执行、媒体与音频控制、SSE、局域网发现及 Windows 集成。

## Main

- 对用户目标、实现、测试资产和最终交付端到端负责；可以按需调用子 Agent，但不转移业务所有权。
- 直接问答和现状解释直接回答；纯调查只读取必要事实。没有实际变更时，不加载业务流程、不建 todo、不跑测试、不启动验证者。
- 修改代码、配置、工作流或正式文档时读取 `skill://workflow`。只有实际改变产品行为或契约时才读取 `skill://requirement-intake`。
- 开工前检查一次 Git；若有未提交变更，请用户决定。用户确认继续后，统一视为本轮范围。
- 产品事实或长期测试资产变化时使用 `skill://product-model`。
- 候选交付依次交给 Test Verifier 和 Goal Reviewer；前置测试分析由 Main 判断，用户可以指定。
- 只有用户要求提交时才读取 `skill://release`。
- 用户说“继续”时先确认是否仍有未完成事项；任务已完成则直接说明，不重复流程。

## 项目入口

- Server：`EzWinCommand-server/app.py`；测试：`python -m pytest`
- Android：`EzWinCommand-android/app`；测试：`./gradlew.bat testDebugUnitTest`
- 产品与测试资料：`docs/product/`、`docs/tests/`、`docs/versions/`
