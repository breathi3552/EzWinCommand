# REQ-006-01: 添加 .omp/RULES.md 固化开发规范

## 背景

EzWinCommand 采用 Oh My Pi 编排框架。该框架的 `.omp/` 目录支持 sticky rules 机制：目录中放置 `RULES.md` 文件并注册为 `always-apply`，系统会在每个 turn 自动将规则内容注入到 Agent 的上下文。

本需求利用该机制，将项目约定的开发流程、Git 纪律和设计原则固化为自动执行的规范。

## 设计方案

### 文件位置

`.omp/RULES.md`

### 规范内容

| 章节 | 内容 |
|---|---|
| **多 Agent 开发流程** | 强制 SE → Dev → Test 三阶段，禁止跳过。定义各角色职责与输出物。 |
| **Git 提交纪律** | 每次编辑后立即 commit、原子化提交、`feat:`/`fix:`/`refactor:`/`chore:` 前缀。 |
| **设计原则** | 零额外依赖优先、Windows 原生 > 第三方、方案对比量化。 |
| **技术栈** | Python 3.13 / Windows 11、FastAPI + Uvicorn、pywin32、纯静态 HTML+JS。 |

### 注入机制

Oh My Pi 框架将 `.omp/RULES.md` 作为 `always-apply` sticky rule，在每个 turn 的系统 prompt 中自动注入规范内容，无需手动引用 `rule://`。

## 实现记录

- 直接创建 `.omp/RULES.md`，内容一次性固化
- Commit: `da2ddf4`
