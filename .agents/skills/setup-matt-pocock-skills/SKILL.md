---
name: setup-matt-pocock-skills
description: Configure this repo for the engineering skills — set up its issue tracker, triage label vocabulary, domain-doc layout, and OMP project pointer. Run once before first use or when those choices change.
disable-model-invocation: true
---

# Setup Matt Skills for OMP

Configure the per-repo facts shared by the engineering Skills:

- issue tracker and its OMP access path;
- triage label mapping when `skill://triage` is installed;
- glossary, ADR and product-contract layout;
- the `## Skill 运行时` or `## Agent skills` pointers in `.omp/AGENTS.md`.

This is an interactive configuration Skill. Explore first, ask only for choices the repo cannot settle, show the proposed files, then write after approval.

## 1. Explore

Inspect:

- the current repository through `xd://github` repo view and `.git/config` when needed;
- `.omp/AGENTS.md`, plus root `AGENTS.md` or `CLAUDE.md` only if the repo already uses them;
- `CONTEXT.md`, `CONTEXT-MAP.md`, `docs/adr/`, `docs/product/` and `docs/agents/`;
- available Skills, especially `triage` and `domain-modeling`;
- monorepo signals in workspace configuration and populated package roots.

Completion criterion: the tracker, existing project instruction entry, installed dependent Skills and domain-doc topology are known.

## 2. Resolve configuration

### Issue tracker

Prefer the repository's actual remote. GitHub uses OMP `issue://`, `pr://` and `xd://github`; GitLab or another tracker records its available MCP/CLI interface; a repo without a remote may use `.scratch/<feature>/` local Markdown.

Record the result in `docs/agents/issue-tracker.md`. Leave external PRs/MRs out of the triage discovery surface unless the user explicitly enables them.

### Triage labels

When `triage` is installed, recommend the five canonical state labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Ask only if the tracker already uses another vocabulary. Record the mapping in `docs/agents/triage-labels.md`.

### Domain docs

Default to single-context: root `CONTEXT.md` plus `docs/adr/`. Offer multi-context only when the repository has genuine independent domain contexts. Preserve any existing product-contract layer; do not move stable behavior specifications into the glossary or ADRs. Record consumer rules in `docs/agents/domain.md`.

Completion criterion: every unresolved choice has one user-approved answer and no existing project document will be silently replaced.

## 3. Show the draft

Present the exact `.omp/AGENTS.md` pointer block and each `docs/agents/*.md` file to be created or changed. Keep pointers short: name the material and the branches that trigger reading it. Let the user edit the draft.

## 4. Write

Use `.omp/AGENTS.md` as the OMP project entry. If it does not exist, create it; preserve unrelated project instructions. Do not create a competing root `AGENTS.md` or `CLAUDE.md` solely for these Skills.

Start from the templates in this directory, then adapt them to the repo instead of copying command caches blindly:

- [issue-tracker-github.md](issue-tracker-github.md)
- [issue-tracker-gitlab.md](issue-tracker-gitlab.md)
- [issue-tracker-local.md](issue-tracker-local.md)
- [triage-labels.md](triage-labels.md)
- [domain.md](domain.md)

Completion criterion: `.omp/AGENTS.md` points to every created configuration file, every pointer target exists, and the documented tracker operations are executable in the current OMP runtime.

## 5. Report

List changed files and which Skills consume them. Re-running is necessary only when the tracker, label vocabulary or domain topology changes.
