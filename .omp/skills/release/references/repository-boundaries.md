# Repository boundaries

## 禁止提交

- 设备密钥、Bearer token、当前配对码或其他凭据。
- `EzWinCommand-server/agent/devices.json`、`command_tasks.json`、`server_identity.json` 等本机运行状态，除非仓库明确提供脱敏示例文件且用户指定。
- `.omp/local/`、`.omp/tmp/`、UI dump、截图、日志和临时测试报告。
- 与本轮目标无关的用户已有改动。

## 按意图提交

- 业务代码和自动化测试：仅在用户明确要求 commit 后。
- `docs/product/`、`docs/tests/`、`docs/versions/`：属于正式项目资产，可随对应业务变更提交。
- `.omp/` 工作流：仅在用户明确要求提交工作流变更时。
- push：始终单独授权。

提交前使用 `git status --short`、`git diff` 和 `git diff --cached` 检查归属；不要用清理、reset 或 checkout 来制造干净工作树。
