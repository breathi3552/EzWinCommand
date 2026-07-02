# EzWinCommand 开发资料归档规范

## 目录结构

```
docs/
  v{major}.{minor}/                          # 版本目录（当前：v0.1）
    REQ-{NNN}-{原始需求简称}/                 # 原始需求
      requirement.md                         # 原始需求描述（用户下发）
      se-analysis.md                         # SE 分析文档
      REQ-{NNN}-{MM}-{拆分需求简称}/          # 拆分需求
        design.md                            # 设计 / 实现文档
        test-records.md                      # 测试记录（表格）
      REQ-{NNN}-{MM+1}-{拆分需求简称}/
        ...
    REQ-{NNN+1}-{原始需求简称}/
      ...
```

## 编号规则

| 层级 | 格式 | 说明 |
|---|---|---|
| 原始需求 | `REQ-{NNN}` | 三位数字，按创建顺序递增（001, 002, …） |
| 拆分需求 | `REQ-{NNN}-{MM}` | 前三位引用原始需求，后两位为子序号（01, 02, …） |

每个 ID 全局唯一，不可重复使用。

## 文件模板

### `requirement.md` — 原始需求

```markdown
# REQ-{NNN}: {标题}

- **日期**: YYYY-MM-DD
- **版本**: v{major}.{minor}
- **状态**: 进行中 / 已完成

## 原始需求
（用户下发的完整需求描述）

## 拆分需求列表
| 编号 | 标题 | 状态 |
|---|---|---|
| REQ-{NNN}-01 | ... | ... |
```

### `se-analysis.md` — SE 分析

SE 角色产出的分析文档，包含方案对比、架构决策等。
命名可为 `se-analysis.md` 或 `se-design-{主题}.md`。

### `design.md` — 拆分需求设计

Dev 角色的设计 / 实现文档，记录具体修改方案。

### `test-records.md` — 测试记录

| ID | 问题描述 | 严重程度 | 状态 | 修复 commit | 日期 |
|---|---|---|---|---|---|
| T-001 | ... | 严重/一般/轻微 | 已修复/待修复/不予修复 | `abc1234` | YYYY-MM-DD |

## 工作流

1. 用户下发需求 → 创建 `REQ-{NNN}` 目录，填写 `requirement.md`
2. SE 分析 → 产出 `se-analysis.md`，列出拆分需求编号
3. 每个拆分需求 → 创建 `REQ-{NNN}-{MM}` 子目录
4. Dev 实现 → 填写 `design.md`
5. Test 测试 → 问题记录到 `test-records.md` 表格中
6. 全部完成 → 更新 `requirement.md` 状态为"已完成"
