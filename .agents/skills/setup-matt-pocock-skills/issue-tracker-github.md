# Issue tracker: GitHub

Issues and planning artifacts live in this repository's GitHub Issues.

## OMP access

- Read issue: `issue://<number>`.
- Read PR: `pr://<number>`; diff: `pr://<number>/diff`.
- List recent issues or PRs through the bare resource with state, label, author and limit filters.
- Search issues, PRs, commits or code; create/check out/push PRs; watch Actions: use the matching `xd://github` operation.
- For issue writes not exposed by `xd://github`, use an available GitHub MCP or `gh` only as a fallback. State the exact remote mutation before executing it.

Record the repository owner/name explicitly so the config does not depend on the working directory.

## Pull requests as a triage surface

**PRs as a request surface: no.** Set to `yes` only when external PRs should appear in `skill://triage` discovery.

When enabled, include only external contributors in discovery. A PR explicitly named by the user can always be triaged.

## Skill operations

- **Publish to the issue tracker:** create an issue.
- **Fetch the relevant ticket:** read its body, labels and full comments.
- **Bare `#N`:** try `pr://N`, then `issue://N`.

## Wayfinding

Used by `skill://wayfinder`. One issue labelled `wayfinder:map` holds the map; child issues hold decisions.

Prefer GitHub sub-issues and native issue dependencies. Where unavailable, link children in the map task list and use `Part of` / `Blocked by` fields. The frontier is the first open child with no open blocker and no assignee. Claim, comment, close, dependency and label operations are remote writes and must follow the current authorization boundary.
