---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

# Implement

Implement the user-authorized spec or ticket as the smallest complete behavioral slices.

1. Read the full source ticket or spec, including comments and blocking decisions. Resolve facts from the repo; ask only for decisions that materially change the result.
2. Identify the highest existing test seam that can observe each behavior. When the user requested test-first work, or the source spec explicitly requires it, read `skill://tdd` and drive one red-green slice at a time.
3. Implement each slice through every affected layer. Run its targeted check and exercise the changed path before starting the next slice.
4. After the behavior works, run the affected contract tests and one end-to-end smoke of the changed path. Run broader suites only when the change can plausibly affect them.
5. Update `docs/product/`, `docs/tests/coverage-map.md`, ADRs or version materials only when their durable facts actually changed; follow `docs/agents/domain.md`.
6. Use `skill://code-review` when the user requested review or the change's breadth, contract impact, security boundary or evidence uncertainty warrants an independent Standards/Spec review.

Completion criterion: every acceptance criterion maps to observed behavior and evidence; every changed behavior maps back to the authorized source; no actionable failure remains.

Commit or push only when the user explicitly authorizes that Git operation. Skill invocation never grants authorization.
