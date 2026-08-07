---
name: ask-matt
description: 为当前工程任务选择合适的 Skill 或组合路径。
disable-model-invocation: true
---

# OMP 工程 Skill 路由

先识别当前任务的形状，再推荐最短的充分路径。Skill 通过 `skill://<name>` 读取；它们不是 shell slash command。不要把完整主链当成固定门禁。

## 主路径：想法到交付

### 明确的小改动

目标、边界和验收已经清楚，且一轮实现可以完成：直接实施并运行覆盖该行为的验证。用户明确要求测试先行时读取 `skill://tdd`；需要独立双轴审查时读取 `skill://code-review`。

### 仍需决策的需求

1. `skill://grill-with-docs`：在仓库内澄清设计树，并按需维护 glossary 或 ADR。
2. 有些问题必须运行后才能回答：使用 `skill://prototype` 做一个只回答该问题的 throwaway prototype，再把结论带回需求讨论。
3. 一轮可以完成：直接实施。
4. 需要多轮或多人协作：用 `skill://to-spec` 固化已讨论内容，再用 `skill://to-tickets` 切成有 blocking edges 的 tracer-bullet tickets；每个 ticket 使用 `skill://implement`。

`skill://implement` 按行为切片实现，按需读取 `skill://tdd`，完成后根据风险读取 `skill://code-review`。commit 与 push 始终服从当前用户授权，不由 Skill 自动授予。

## 入口

- **困难 Bug、性能回退、偶发失败** → `skill://diagnosing-bugs`。先建立能对准确症状变红的 tight loop，再诊断和修复。
- **外部 issue 堆积** → `skill://triage`。它处理未经整理的 incoming issue；`skill://to-tickets` 生成的 ticket 已经 agent-ready，无需再次 triage。
- **巨大且路径仍在迷雾中的工作** → `skill://wayfinder`。先在 issue tracker 上解决 decision tickets；路径清晰后进入 `skill://to-spec`，不直接跳到实现。
- **模块接口、seam 或可测试性问题** → `skill://codebase-design`。要扫描全仓 deepening 候选时使用 `skill://improve-codebase-architecture`。
- **外部资料或 API 事实** → `skill://research`。
- **正在解决 merge/rebase conflict** → `skill://resolving-merge-conflicts`。
- **Android、ADB、Windows Server、Web、局域网配对、媒体或 Core Audio 的真实环境验证** → `skill://ezwin-e2e`。

## 支撑 Skill

- `skill://domain-modeling`：维护 ubiquitous language 与少量真正成立的 ADR。
- `skill://grilling`：设计树访谈原语；仓库内通常从 `skill://grill-with-docs` 进入，仓库外从 `skill://grill-me` 进入。
- `skill://handoff`：需要跨 session、目录、harness 或人员传递时生成 `local://` 交接文档。
- `skill://writing-for-agents`：编写 Skill、`.omp/AGENTS.md` 或 Agent 可消费文档。
- `skill://setup-matt-pocock-skills`：首次安装或更换 issue tracker、triage labels、领域资料布局时运行。

## 阶段边界

阶段结束时优先继续当前 session；只有独立且范围明确的并行切片才使用 OMP `task`。需要跨边界携带信息时使用 `skill://handoff`，并通过引用现有 spec、issue、ADR、diff 或 `local://` 资产避免重复。完整决策树见 [PHASE-BOUNDARIES.md](PHASE-BOUNDARIES.md)。
