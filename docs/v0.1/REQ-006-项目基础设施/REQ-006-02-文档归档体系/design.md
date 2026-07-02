# REQ-006-02: 建立 docs/ 文档归档目录和编号体系

## 背景

开发过程需要可追溯的文档归档。本需求建立从版本→原始需求→拆分需求的三级目录体系，并定义全局唯一的编号规则。

## 设计方案

### 目录结构

```
docs/
  README.md                                   # 归档规范总则
  v{major}.{minor}/                           # 版本目录（当前：v0.1）
    _templates/                               # 文件模板
    REQ-{NNN}-{原始需求简称}/                  # 原始需求
      requirement.md                          # 原始需求描述
      se-analysis.md                          # SE 分析文档
      REQ-{NNN}-{MM}-{拆分需求简称}/           # 拆分需求
        design.md                             # 设计 / 实现文档
        test-records.md                       # 测试记录
```

### 编号规则

| 层级 | 格式 | 说明 |
|---|---|---|
| 原始需求 | `REQ-{NNN}` | 三位数字，按创建顺序递增（001 起） |
| 拆分需求 | `REQ-{NNN}-{MM}` | 前三位引用原始需求，后两位为子序号（01 起） |

每个 ID 全局唯一，不可重复使用。

### 模板文件

`_templates/` 目录提供 `requirement.md`、`sub-requirement.md`、`test-records.md` 三个模板，统一归档内容格式。

### 工作流

1. 用户下发需求 → 创建 `REQ-{NNN}` 目录，填写 `requirement.md`
2. SE 分析 → 产出 `se-analysis.md`，列出拆分需求编号
3. 每个拆分需求 → 创建 `REQ-{NNN}-{MM}` 子目录
4. Dev 实现 → 填写 `design.md`
5. Test 测试 → 问题记录到 `test-records.md`
6. 全部完成 → 更新 `requirement.md` 状态为"已完成"

## 实现记录

- 创建 `docs/README.md`（归档规范总则）
- 创建 `docs/v0.1/_templates/` 及三个模板文件
- Commit: `da2ddf4`
