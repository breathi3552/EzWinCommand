# Domain docs

Engineering Skills read only the knowledge layer relevant to the current task.

## Read branches

- Domain naming: the relevant `CONTEXT.md`.
- Architectural trade-offs: relevant ADRs under `docs/adr/` or context-local ADR directories.
- Stable user behavior, protocol or safety contracts: the repository's existing product-contract location, when present.
- Long-lived business verification: the repository's acceptance-coverage document, when present.

Missing files are not setup errors. `skill://domain-modeling` creates glossary and ADR files lazily when terms or qualifying decisions crystallize.

## Topology

Record either:

- **Single context:** root `CONTEXT.md` plus `docs/adr/`.
- **Multiple contexts:** root `CONTEXT-MAP.md` points to each context's `CONTEXT.md`; system ADRs stay at root and context ADRs stay with their context.

Preserve existing product-contract documentation as a separate layer. Do not migrate behavior specifications into a glossary or ADR.

## Vocabulary

Use glossary terms in issue titles, specs, tests and design proposals. If a needed term is absent, decide whether it is invented implementation language or a real domain gap; only the latter goes to `skill://domain-modeling`.

## ADR conflicts

Call out a conflict with an existing ADR explicitly. Reopen the decision only when new evidence or real friction justifies it.
