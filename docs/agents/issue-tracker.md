# Issue tracker：GitHub

本仓库的 issue 与 PRD 存放在 GitHub Issues。读取与写入优先使用 OMP 的 GitHub 资源和工具，不把本机 `gh` CLI 当作前提。

## OMP 接口

- 读取 issue：`issue://<number>`；需要完整讨论时保留 comments。
- 读取 PR：`pr://<number>`；diff 使用 `pr://<number>/diff`。
- 列出近期 issue 或 PR：分别读取 `issue://`、`pr://`，按 state、label、author 等参数过滤。
- 搜索 issue、PR、commit 或代码，以及创建 PR、checkout、push、观察 Actions：使用 `xd://github` 对应 operation。
- 当前 `xd://github` 不提供 issue 评论、标签、关闭或创建 issue 的写 operation。遇到这些操作时，使用可用的 GitHub MCP/CLI；执行写操作前明确列出将发生的远程变更。

仓库为 `breathi3552/EzWinCommand`。裸编号 `#42` 可能是 issue 或 PR；先读取 `pr://42`，不存在时再读取 `issue://42`。

## Pull Request 作为 triage 入口

**PRs as a request surface: no.**

设为 `yes` 后，`skill://triage` 才把外部 PR 纳入发现队列；显式指定的 PR 始终可以审查。外部 PR 指 author association 为 `CONTRIBUTOR`、`FIRST_TIME_CONTRIBUTOR` 或 `NONE`，不包括 `OWNER`、`MEMBER` 或 `COLLABORATOR` 的进行中工作。

## Skill 约定

- “publish to the issue tracker”：创建 GitHub issue。
- “fetch the relevant ticket”：读取 issue 正文、labels 和完整 comments。
- `skill://to-spec` 与 `skill://to-tickets` 发布前，先展示将创建的远程对象；用户批准方案不等于授权额外的 commit 或 push。

## Wayfinding

`skill://wayfinder` 使用一个带 `wayfinder:map` 标签的 issue 作为 map，以 child issues 表示 decision tickets：

- 优先使用 GitHub sub-issues 与 native issue dependencies。
- 若仓库未启用相应能力，在 map task list 与 child 正文的 `Part of` / `Blocked by` 字段中保留关系。
- Frontier 是没有 open blocker 且无人领取的第一个 open child。
- Claim、comment、close、依赖关系和 label 都是远程写操作；执行前说明具体对象和变更。
