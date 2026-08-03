# Validation commands

Read this file during Mode A after-editing validation (A3/A4) when choosing which static and validation checks to run.

## Direct static checks (preferred)

For Python code changes, prefer these direct checks over `lr static`:

```bash
ruff format --check .
mypy app
pyright
```

## When to use `lr static`

Use `lr static`, `lr static --check`, `lr static --check --raw`, full `lr 13`, `lr 13:<mode>`, or other long-running validation only if:

- Repo evidence (CLAUDE.md, CI config, LR docs) specifically requires it for the changed surface
- The user explicitly asks for it
- A full repo-wide lint/type pass is needed to verify cross-file impact

`lr static` does not include `ruff format --check .` — run that separately.

## Long-running validation pattern

When a long-running validation command is needed, run it in the background and write output to `.tmp/validation/` instead of waiting on a live terminal tail.

### lr static

```bash
mkdir -p .tmp/validation
nohup ./lr static > .tmp/validation/lr-static.log 2>&1 &
echo $! > .tmp/validation/lr-static.pid
```

### Variants — use clear log and pid names

- `.tmp/validation/lr-static-check.log` — `./lr static --check`
- `.tmp/validation/lr-static-check-raw.log` — `./lr static --check --raw`
- `.tmp/validation/lr-13-unit.log` — `./lr 13:unit`
- `.tmp/validation/lr-13-full.log` — `./lr 13`

### Check progress

```bash
tail -n 80 .tmp/validation/lr-static.log
ps -p "$(cat .tmp/validation/lr-static.pid)" -o pid=,stat=,etime=,cmd=
```

### Poll until completion

Re-check the log after a reasonable interval (10 minutes for long checks) until the process exits or final output shows pass/fail/error/timeout.

**Never claim a background check passed unless the final log proves it passed.** A missing, partial, still-running, timed-out, or failed log is not a pass.

## Mode C note

For Mode C, run correctness checks before performance measurements. Treat noisy or failed measurements honestly. Do not run long-running benchmarks live; use `.tmp/validation/` logs when commands may exceed the shell timeout.
