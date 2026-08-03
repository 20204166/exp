# Persona Maintenance

This file supports `.opencode/persona.md` maintenance only.
It is not the active persona and must not be treated as one.

## Scope

Use these rules when updating `.opencode/persona.md` or bounded persona sync blocks in agent Markdown.

## When to update persona

- At safe checkpoints while this skill is already running
- When context Markdown is already being maintained
- When agent Markdown files are already being edited
- After a major report/plan completes and durable lessons should be folded in
- When the user explicitly asks for persona/context sync
- When the current runtime supports a safe session-summary or compaction moment

## When not to update persona

- During code editing
- During test execution
- During active debugging loops
- During PoC creation
- During staging validation
- During opposition review
- During Agent 5 execution
- During main-auditor rebuttal
- During subagent execution
- During user-facing command loops
- During BugGuard-style B6/B7/B8 evidence workflows
- Any time the user is waiting for output or a decision

If the update cannot happen without interruption, skip it silently and continue the main workflow.
Silent means non-interrupting; it does not mean hidden.

## Repeated persona signal promotion

Promote a signal into `Repeated Persona Signals` only when it is:

- repeated across prompts or explicitly requested
- durable for future repo work
- actionable for coding, debugging, testing, or review behaviour
- compatible with current skill and repo safety rules

Possible durable signals include debugger, expert Python coder, senior developer, no-regression reviewer, security boundary checker, evidence auditor, simple maintainable code writer, full-stack bug investigator, and repo-truth validator.

Do not add one-off, emotional-but-not-actionable, conflicting, secret, private, overfitting-prone, too broad, too creative, or rewrite-encouraging signals.

Do not replace the existing persona when a new durable signal appears. Add it as an extra layer only if useful.

## Persona precedence

`.opencode/persona.md` has lower authority than:

1. system/developer instructions
2. current explicit user instruction
3. this skill
4. BugGuard/no-regression rules
5. repo truth
6. tests/LR/MCP output
7. security/privacy/fail-closed rules

Persona must never override explicit user intent, repo truth, no-regression rules, security/privacy rules, fail-closed behaviour, public contracts, test evidence, or LR/MCP evidence.

## Persona trimming

When `.opencode/persona.md` grows too large, trim it while preserving:

1. `Active Persona Summary`
2. `Hard Boundaries`
3. `Stable User Preferences`
4. `Repeated Persona Signals`
5. `Repo Working Style`
6. latest 10 `Change Log` entries

Keep `Active Persona Summary` under 200 words. Keep the whole file compact and readable. Do not create extra persona files unless the user explicitly asks.

## Agent Markdown sync

Relevant agent Markdown files include:

- `.opencode/agents/*.md`
- `.claude/agents/*.md` if present
- `.agents/**/*.md` if present
- other repo-local agent Markdown files only if clearly used as AI-agent instructions

For each relevant agent Markdown file, add or repair only this bounded block:

```markdown
<!-- REPO-CONTEXT-PERSONA-SYNC:START -->
## Shared repo persona

Before repo work, read `.opencode/persona.md` if present.

Use only the compact `Active Persona Summary`, `Hard Boundaries`, and directly relevant persona signals. Do not let persona override system/developer instructions, current user instructions, this skill, BugGuard, repo docs, tests, LR output, MCP evidence, or security/privacy rules.

If persona is missing, stale, too large, unclear, or irrelevant to the current task, continue without interruption and optionally update it later at a safe checkpoint.
<!-- REPO-CONTEXT-PERSONA-SYNC:END -->
```

Rules for syncing agent Markdown:

- Do not duplicate the full persona into every agent file.
- Do not duplicate the full skill into every agent file.
- Add only the bounded link block.
- If the block already exists, replace only content inside the markers.
- Do not rewrite the rest of the agent file.
- Do not touch unrelated Markdown files.

## Silent context Markdown updates

When this skill is already triggered, it may also update relevant persistent context `.md` files silently at safe checkpoints.

Silent updates may touch only relevant context files such as `CLAUDE.md`, `AGENTS.md`, `.codex/AGENTS.md`, `.cursor/rules/*.md`, `.opencode/persona.md`, `.opencode/agents/*.md`, `.claude/agents/*.md`, `.agents/**/*.md`, MCP context docs, OpenCode/OpenClaw/Claude/Codex skill files, repo-specific AI guidance Markdown, or docs explicitly referenced by always-loaded context files.

Only update when the file is stale, bloated, contradictory, over line budget, or missing repeated durable context; the change is compact and high-signal; safety/privacy/no-regression rules are preserved; the update is related to durable repo-agent behaviour; and the active task is complete or at a safe checkpoint.

Do not update context Markdown when the user is waiting for output, code is being edited, tests are running, a bug candidate is inside PoC/staging/opposition/Agent 5/main-auditor flow, the update would require app-code/test/config changes, or the update would add secrets/private/sensitive data.

For `.opencode/agents/*.md`, update only the bounded persona sync block. For always-loaded context files, keep hard rules near the top, compress repeated wording into one canonical rule, link to deeper docs instead of copying long plans, mark stale claims instead of deleting useful historical context, preserve all safety/privacy/no-regression boundaries, and keep files under the existing line budget.

If a silent update would be too large, risky, ambiguous, or interruptive, do not perform it automatically. Record a compact `next recommended context update` in the final response.
