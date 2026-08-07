---
name: research
description: Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent.
---

# Research

Dispatch one read-only `scout` through OMP `task` for a tightly scoped research question, while the main session continues independent work. If several questions are independent, dispatch them together in one batch with separate outputs and shared source-quality rules.

The research task must:

1. Follow each material claim to a primary source: official documentation, source code, specifications, standards or first-party APIs.
2. Prefer `read` for known URLs and `xd://github` or GitHub repository resources for hosted source; use web search only to locate unknown sources.
3. Distinguish observed facts from inference and cite every material claim with a stable URL.
4. Write one Markdown artifact in the repo's existing research-notes location. When no convention exists, return the proposed path to Main before creating a new documentation category.
5. Report unresolved uncertainty and the exact source gap.

Main verifies the delivered file and source links before treating the result as complete.
