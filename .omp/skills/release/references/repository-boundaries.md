# Repository boundaries

## 禁止提交

- 设备密钥、Bearer token、当前配对码或其他凭据。
- `EzWinCommand-server/agent/devices.json`、`command_tasks.json`、`server_identity.json` 等本机运行状态，除非仓库明确提供脱敏示例文件且用户指定。
- `.omp/local/`、`.omp/tmp/`、`.omp/lsp.json`、UI dump、截图、日志、临时测试报告和 `docs/v*/` 历史过程资料。
- 与本轮目标无关的用户已有改动。

## 按意图提交

- 业务代码和自动化测试：仅在用户明确要求 commit 后。
- `docs/README.md`、`docs/changelog.md`、`docs/product/`、`docs/tests/`、`docs/versions/`：属于正式项目资产，可随对应业务变更提交。
- `.omp/AGENTS.md`、`.omp/RULES.md`、`.omp/agents/`、`.omp/skills/` 和可复用工具源码：仅在用户明确要求提交工作流或工具链变更时。
- push：始终单独授权。

提交前使用 `git status --short`、`git diff` 和 `git diff --cached` 检查归属；不要用清理、reset 或 checkout 来制造干净工作树。
