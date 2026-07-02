# REQ-006-03: 完善文档归档规范至 .omp/RULES.md

## 背景

REQ-006-02 建立了 `docs/README.md` 作为归档规范总则，但该文件不在 `.omp/` sticky rules 范围内，无法在每个 turn 自动注入。本需求将归档规范的摘要追加到 `.omp/RULES.md`，确保归档纪律与开发纪律一起持久化生效。

## 设计方案

### 修改内容

在 `.omp/RULES.md` 末尾追加 `## 文档归档` 章节，包含：

- 存放路径约定（`docs/{版本号}/`）
- 目录命名规则（`REQ-{NNN}-{简称}/` 和 `REQ-{NNN}-{MM}-{简称}/`）
- 文件说明（`requirement.md`、`se-analysis.md`、`design.md`、`test-records.md`）
- 编号规则（三位 / 两位递增）
- 引用 `docs/README.md` 作为详细规范源

### 关键决策

- **不替换 `docs/README.md`**：该文件保留为完整规范，`.omp/RULES.md` 仅置入摘要
- **引用而非复制**：通过 `详细规范见 docs/README.md` 避免两份规范不同步

## 实现记录

- 在 `.omp/RULES.md` 中追加"文档归档"章节
- Commit: `c66226e`
