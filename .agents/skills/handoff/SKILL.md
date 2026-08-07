---
name: handoff
description: Compact the current conversation into a handoff document for another agent to pick up.
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
---

# Handoff

Write a portable Markdown handoff to `local://handoff.md`, or a more specific `local://<topic>-handoff.md` when several handoffs coexist. Do not add it to the repository.

Include:

- the next session's exact goal and completion criterion;
- settled user decisions and remaining decision frontier;
- current repo/worktree facts that cannot be recovered from the referenced sources;
- evidence already obtained and checks still required;
- a **Suggested skills** section using `skill://<name>` pointers.

Reference existing specs, plans, ADRs, issues, commits, diffs and other `local://` artifacts instead of copying them. Redact credentials, pairing material, personal data and machine identity. If the user supplied a next-session focus, prune the handoff to that branch.

Completion criterion: a fresh OMP session can resume the named goal without inventing a decision or repeating completed investigation.
