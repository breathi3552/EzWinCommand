# EzWinCommand

EzWinCommand 是可信局域网内的 Windows 控制系统，包含 Python/FastAPI Server、Web 管理端和 Kotlin Android App。核心业务包括配对鉴权、命令执行、媒体与音频控制、SSE、局域网发现及 Windows 集成。

## 项目入口

- Server：`EzWinCommand-server/app.py`
- Android：`EzWinCommand-android/app`
- 产品契约：`docs/product/`
- 业务验收覆盖：`docs/tests/coverage-map.md`
- 版本资料：`docs/versions/` 与 `docs/changelog.md`

## Skill 运行时

`.agents/skills/` 是本仓库唯一的项目 Skill 目录。执行 Skill 时遵循 OMP 原生接口：
- 当前任务按本文件、`.agents/skills/`、`docs/agents/` 与当前产品、ADR、长期测试资料执行；`docs/v*/REQ-*` 仅在用户明确要求历史复盘、迁移核查或恢复旧决策时读取。
- Skill 间调用读取 `skill://<name>`；EzWinCommand 真实环境验证读取 `skill://ezwin-e2e`；文档中的 Skill 名称不是 shell slash command。
- 需要并行独立上下文时使用 `task`；只读探索使用 `scout`，审查使用 `reviewer`，实现工作仅在没有更具体 agent 时使用通用 task agent。
- session 交接与临时契约使用 `local://`，不写入仓库。
- GitHub issue 与 PR 优先读取 `issue://`、`pr://`，写操作与搜索使用 `xd://github`；具体约定见 `docs/agents/issue-tracker.md`。
- Harness 的工具政策、授权边界和验证要求始终高于 Skill 中的通用示例。

用 `skill://ask-matt` 选择工程路径。流程按规模自适应：明确小修直接实现并验证；复杂需求使用 grilling、spec 与 tickets；困难 Bug 使用 diagnosing-bugs；只有实际需要测试先行时使用 tdd；审查按目标与风险选择 code-review。不得把整条主链当成每次改动的固定门禁。

## 项目知识

领域词汇、架构决策与产品契约职责分离：

- `CONTEXT.md` 仅保存 ubiquitous language；不存在时由 `skill://domain-modeling` 在首个术语真正确定后创建。
- `docs/adr/` 仅保存难以逆转、缺少上下文会令人意外、且源于真实权衡的决策。
- `docs/product/` 保存无法从代码可靠恢复的稳定产品与协议事实；`docs/tests/coverage-map.md` 保存长期业务验收覆盖；版本资料只记录增量，不记录过程流水账。
- 消费规则见 `docs/agents/domain.md`。

## 安全与交付证据

- 不记录或输出设备密钥、Bearer token、当前配对码、服务端私钥或其他凭据。日志保留必要诊断信息和 traceback，但敏感值必须脱敏。
- `EzWinCommand-server/agent/devices.json`、`plugins.json`、`command_tasks.json`、`server_identity.json` 是本机状态，不属于交付物。
- 跨端 wire、配对、鉴权、设备、命令或媒体行为变化时，验证受影响的两端；仅有证据证明单端内部变化时才缩小范围。
- UI/E2E 结果明确标记为 Automated、AI-assisted 或 Manual。未执行的人工项目写“待人工验证”，不得表述为通过。
- 交付前从目标到实现检查遗漏，从变更到目标检查 scope creep；测试通过不能代替目标核对。
- 截图、UI dump、日志和临时测试报告是证据产物，不进入正式项目资料。
