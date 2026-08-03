# Validation Commands

Read this file before the final report. These are safe documentation/repository checks only. Do not invent repository-specific commands; discover available commands from repo truth and use only those that exist.

## Skill-document-only changes

This skill creates only Markdown files under `.claude/skills/Compliance/`. Per repo guidance (AGENTS.md / repo-context-curator), when only Markdown or context files changed, do not run `lr 13`, `pytest`, or full app tests. Do not run writer/apply commands. Do not run performance benchmarks. Do not run long-running validation unless repo evidence or the user requires it.

## Direct doc checks (run these)

```bash
git diff --check -- .claude/skills/Compliance
git diff --stat -- .claude/skills/Compliance
git status --short -- .claude/skills/Compliance
wc -l .claude/skills/Compliance/*.md
```

`git diff --check` catches whitespace errors and merge-conflict markers. `git diff --stat`/`git status --short` confirm only intended files changed. `wc -l` confirms the SKILL.md stays compact and support files are within budget.

## Secret-shape search (run on created files)

Run a secret-shape grep over the created files to confirm no secrets, tokens, env values, API keys, cookies, or credentials were written. Do not print matches; report only whether any were found.

## Optional repo LR checks (only if `lr` is available and relevant)

If the `lr` launcher is available and the change touched code, these may apply. For skill-document-only changes they are generally not required, but may be used as a belt-and-braces check when available:

```bash
./lr 7 -- .claude/skills/Compliance     # 800-line file-size gate (every file change), if path-scoped invocation is supported
./lr secrets                           # secret scan, if available
./lr impact                            # changed-path audit, if available
```

If `lr` is unavailable, say so honestly and use the direct doc checks above as the equivalent. A missing or unavailable tool is not a pass; record it honestly. Never claim a check passed unless its output proves it passed. A missing, partial, still-running, timed-out, or failed log is not a pass.

## Commands not run and why

- `lr static` / `ruff` / `mypy` / `pyright` — only Python code changed would require these; no Python was changed.
- `lr 13` / `pytest` — no application code or tests changed.
- Performance benchmarks — not applicable to skill-document changes.
- `writer`/`apply` — prohibited in audit mode.

## Reporting

Report each run command, its outcome (pass/fail/unavailable), and the line counts of the created files. If a command was unavailable, state that honestly rather than implying it ran.
