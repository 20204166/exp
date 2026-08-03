# Context Compression

This file provides the detailed compression rules for always-loaded repo context.

## Discovery and classification

Search for context and skill files across `CLAUDE.md`, `AGENTS.md`, `SKILL.md`, `.opencode/*`, `.cursor/*`, `.codex/*`, `.claude/*`, `.agents/*`, and skill directories. Grep for agent and context keywords such as persona, OpenCode, OpenClaw, MCP, LR, repo truth, no regression, and do not hallucinate.

Classify each file as one of:

- always-loaded root context
- tool-specific context
- skill instruction
- shared persona context
- agent Markdown instruction
- long-form project docs
- historical plan/report
- generated output
- unrelated Markdown

Do not assume `CLAUDE.md` is the only context file.

## Priority model

Core: keep in always-loaded context.

Pointer: keep one short line plus a link to a deeper doc.

Move: remove from always-loaded context and place or link in docs.

Archive: mark historical or superseded; do not use as current truth.

Delete candidate: only if duplicate, obsolete, and safely preserved elsewhere.

Use this decision rule:

- If a rule affects many future edits or prevents severe regression, keep it in core context.
- If a detail matters only for one subsystem, keep a short pointer and link to the subsystem doc.
- If a detail matters only for one task, keep it out of always-loaded context.
- If a claim is stale, replace only the verified stale sentence.

## Low-value-context removal

Compress, move, or de-emphasise context that is:

- rarely used
- overly broad
- duplicated in multiple places
- stale or contradicted by repo truth
- old implementation detail from a completed phase
- full plan text copied into always-loaded context
- long file inventories without decision rules
- long historical logs
- temporary debugging notes
- one-task reminders
- specific old branch names
- expired migration instructions
- old command output
- raw research notes
- screenshots or terminal dumps
- provider-specific tables that belong in subsystem docs

Replace useful low-value detail with:

- one short durable lesson
- one link to the source doc or path
- a status label: `implemented`, `planned`, `historical`, `superseded`, or `needs validation`
- one sentence explaining when to read the full doc

Example:

```markdown
- Object storage: keep local fallback until R2 staging migration is validated. Read `docs/phase2_object_storage_staging_rollout_validation_plan.md` before storage changes.
```

## Staleness and contradiction handling

For each contradiction, record:

```text
old claim:
current repo truth:
evidence:
action:
```

Allowed actions:

- mark stale
- add status note
- replace only the stale sentence if truth is verified
- move historical detail to linked docs
- keep historical context with a clear label
- add a current-truth pointer above the old detail

Forbidden actions:

- delete old safety constraint without replacement
- mark planned work as implemented
- invent current repo truth
- use docs or plans as implementation proof unless the claim is planning-only

Use notes such as:

```markdown
> **Status update:** This was accurate when written, but repo truth has changed. Current status: ...
```

```markdown
> **Planning-only note:** This is documented as planned work, not current implementation.
```

```markdown
> **Historical context:** Kept for background; do not treat as current repo truth.
```

## Context-file smells

Detect and report:

- Context Bloat
- Conflicting Instructions
- Stale Implementation Claim
- Skill Leakage
- Plan Leakage
- Lint/Test Leakage
- Security Dilution
- Tool Confusion
- Scope Creep
- Overfitting

For each smell, record:

```text
file:
section:
smell:
risk:
fix:
```

## Line-count budgets

For always-loaded context files:

- hard max: 1000 lines
- target max: 600 lines
- ideal: 200–450 high-signal lines

Suggested allocation:

- Top 50 lines: absolute hard rules and repo workflow
- Next 100–200 lines: architecture boundaries and safety contracts
- Next 100–200 lines: LR/check workflow and tool orchestration
- Remaining: feature-specific read-this-doc pointers

Avoid large architecture diagrams, full file inventories, deep implementation details, full test lists, full phase plans, historical logs, old command outputs, and giant tables in always-loaded files.

If an always-loaded context file is over 1000 lines, reduce it below 1000 before completion while preserving the hard rules.

For silent/opportunistic updates, follow `persona_maintenance.md`; compression rules here do not authorize interruptive or hidden edits.
