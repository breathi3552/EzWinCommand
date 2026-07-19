---
name: verification
description: EzWinCommand 候选交付的独立验证协议。仅供 Test Verifier、Goal Reviewer、Main 准备真实验证交接，或用户明确要求检查验证协议时使用；直接问答、纯调查和没有实际变更的任务不要使用。
---

# 独立验证协议

验证者只读，不修改代码、测试、文档或 Git 状态。验证依据按任务需要包含用户表达、明确决策、session 需求契约、候选 diff、相关长期契约和验收覆盖；不适用的材料不得仅因缺失而阻塞。

Test Verifier 读取 `skill://verification/references/test-verification.md`。Goal Reviewer 读取 `skill://verification/references/goal-review.md`。两者统一使用 `skill://verification/references/verdicts.md`。

Main 交接时使用以下中文字段：

```text
验证模式：前置测试分析 | 测试验证 | 目标审查
需求契约：local://requirement-contract.md | 无
变更路径：...
Git 开工检查：干净 | 用户已确认将现有变更纳入本轮
Main 自测：命令及结果；仅供参考
人工环境约束：...
长期资料：已更新的路径 | 不适用及原因
```

重需求或交接明确给出契约时直接读取 `local://requirement-contract.md`。未就绪且开放决策影响结论时返回“阻塞”；明确小需求、Bug 或非业务变更可根据用户指令、仓库事实和候选 diff 验证。

不要把 Main 的“已完成”“应该通过”等自我评价作为证据。
