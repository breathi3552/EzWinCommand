---
name: release
description: 用户要求 commit、push 或交付前，由 Main 手动调用以检查独立测试结论、目标审查、待人工验证项、产品资料、工作树归属和仓库边界；调用本身不授予提交权限。
disable-model-invocation: true
---

# Release 门禁

调用本 Skill 不等于授权 commit 或 push。commit 需要用户本轮明确要求；push 始终需要单独明确授权。

## 检查

1. 读取 `skill://release/references/repository-boundaries.md`。
2. Test Verifier 结论必须为“通过”或“通过（待人工验证）”。
3. Goal Reviewer 结论必须为“通过”。
4. “通过（待人工验证）”必须列出全部未自动化项目及其人工覆盖范围；不得存在未知或无归属缺口。涉及安全、鉴权、数据破坏或不可恢复副作用时不得放行。
5. 产品行为、协议或功能点变化时，产品地图、覆盖矩阵和版本日志必须同步。
6. 检查完整 diff、staged diff 和未跟踪文件。若开工时已有未提交变更，确认用户已经同意把它们统一纳入本轮范围。
7. staged 内容只能包含用户授权且属于本轮的路径；不得混入运行时密钥、设备状态、测试证据或 `.omp` 临时产物。
8. 任一 Verifier 同类失败达到三轮时不得绕过门禁。

## 输出

```text
Release 结论：就绪 | 阻塞
授权状态：已明确授权 commit | 已明确授权 push | 未授权
测试结论：通过 | 通过（待人工验证） | 缺失
目标审查结论：通过 | 缺失
待人工验证：无 | ...
暂存范围：干净 | 混入无关内容 | 为空
阻塞项：无 | ...
```

只有“Release 结论：就绪”且相应授权存在时，Main 才执行 Git 操作。
