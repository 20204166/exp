# Validation Commands

Use these checks for Markdown/context-only edits and for related repository truth checks.

## Markdown/context-only edits

- `git status --short`
- `git diff --check`
- `git diff --stat`
- `git diff -- .opencode/persona.md .opencode/agents .claude/agents .agents CLAUDE.md AGENTS.md .claude .codex .cursor docs/ai-context docs/planned_implementations docs/planned_implementation`
- line counts for context files with `find ... | xargs -0 wc -l`
- secret-shape grep across edited context files

Example secret-shape grep:

```bash
git grep -n "SECRET_KEY\|API_KEY\|TOKEN\|PASSWORD\|PRIVATE KEY\|BEGIN .*KEY" CLAUDE.md AGENTS.md .opencode .claude .agents .codex .cursor docs/ai-context docs/planned_implementations docs/planned_implementation
```

## `lr` checks

If `lr` is available, use the repo-documented equivalents such as `./lr 7`, `./lr impact`, and `./lr secrets`.

If `lr` is unavailable, say so honestly and provide equivalent safe checks.

## Tests

If only Markdown or context files changed, do not run `lr 13`, `pytest`, or full app tests.

## Python changes

If Python code was changed, prefer direct static checks such as `ruff format --check .`, `mypy app`, and `pyright`.

Do not run long-running validation by default unless repo evidence or the user requires it.

## Long-running validation

When a long-running validation command is needed, run it in the background and write output to `.tmp/validation/` instead of waiting on a live terminal tail.

Example:

```bash
mkdir -p .tmp/validation
nohup ./lr static > .tmp/validation/lr-static.log 2>&1 &
echo $! > .tmp/validation/lr-static.pid
```

Use the same pattern for variants with clear log and pid names, such as `lr-static-check.log`, `lr-static-check-raw.log`, `lr-13-unit.log`, or `lr-13-full.log`.

Check progress by reading the log file and process status, not by claiming success from partial output.

Never claim a background check passed unless the final log proves it passed. A missing, partial, still-running, timed-out, or failed log is not a pass.

## Honest timeout reporting

If a command times out or fails, report the timeout or failure plainly, include the command and log path if relevant, and do not infer success from incomplete output.
