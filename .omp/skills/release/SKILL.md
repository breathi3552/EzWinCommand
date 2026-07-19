---
name: release
description: 用户要求 commit、push 或交付前，由 Main 手动调用以检查独立测试结论、目标审查、待人工验证项、产品资料、工作树归属和仓库边界；调用本身不授予提交权限。
disable-model-invocation: true
---

# Release 门禁

调用本 Skill 不等于授权 commit 或 push。commit 需要用户本轮明确要求；push 始终需要单独明确授权。

## 检查

1. 读取 `skill://release/references/repository-boundaries.md`。
2. 检查 Main 的风险分级与验证证据；重需求、协议或安全边界变化需要 Test Verifier 和 Goal Reviewer，低风险改动可由针对性自测与 diff 审查支撑。
3. 已调用的 Verifier 结论必须满足其协议，不得跳过已报告的关键失败或阻塞。
4. “通过（待人工验证）”应列出与本轮目标相关的人工覆盖范围；普通待办可随交付说明，未授权破坏性操作、不可恢复副作用或真实凭据风险不得放行。
5. 只有稳定产品事实、协议契约或长期验收缺口实际变化时才要求同步相应资料；可从代码可靠恢复的内部变化不为文档而文档。
6. 检查完整 diff、staged diff 和未跟踪文件。若开工时已有未提交变更，确认用户已经同意把它们统一纳入本轮范围。
7. staged 内容只能包含用户授权且属于本轮的路径；不得混入运行时密钥、设备状态、测试证据或 `.omp` 临时产物。
8. 同一关键失败达到三轮时停止机械重试，由 Main 缩小范围、调整方案或向用户报告。

## 输出

```text
Release 结论：就绪 | 阻塞
授权状态：已明确授权 commit | 已明确授权 push | 未授权
验证依据：Main 自测 | Test Verifier | Test Verifier + Goal Reviewer
测试结论：通过 | 通过（待人工验证） | 不适用 | 缺失
目标审查结论：通过 | 不适用 | 缺失
待人工验证：无 | ...
长期资料：已同步 | 不适用 | 漂移
暂存范围：干净 | 混入无关内容 | 为空
阻塞项：无 | ...
```

只有“Release 结论：就绪”且相应授权存在时，Main 才执行 Git 操作。
