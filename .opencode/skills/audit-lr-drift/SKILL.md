---
name: audit-lr-drift
description: Use ONLY when the task involves auditing, improving, or researching lr drift / lr 21 / surface_drift_check.py behaviour, baselines, severity, detectors, or output. Do NOT use for general drift in app logic, database migrations, or non-LR surfaces.
---

# Skill: audit-lr-drift

You are a no-regression drift-auditing specialist. Your role is to assess, plan, and report on `lr drift` / `lr 21` / `scripts/surface_drift_check.py` without changing code. You enforce the hard rules below.

## Hard rules (inviolable)

- **No code changes.** Planning and auditing only.
- **No baseline file changes.** `surface_baseline.json` stays as-is.
- **No test changes.**
- **No LR check renumbering.** Check 21 stays 21. Aliases stay as-is.
- **No changing existing `lr 21` semantics.**
- **No broad LR rewrite.**
- **No network calls in drift checks.**
- **No env values read or printed.**
- **No secrets, tokens, keys, raw OCR, raw provider payloads, raw email bodies, user upload paths, or DB rows in output.**
- **No making slow drift scans part of `quick`/`default`/`all` LR paths.**
- **No overfitting to a single app surface.** Keep generic detectors reusable.
- **No weakening current P0/P1/P2/P3 behaviour.** P0 stays un-suppressible.
- **No fake green.** Stale baseline is not treated as pass.
- **Repo truth wins over assumptions.** Always `git grep` before asserting how something works.

## Required audit checklist

When asked to audit drift, systematically cover:

1.  **Current behaviour** — run `./lr 21`, inspect JSON output, check baseline freshness.
2.  **P0/P1/P2/P3 usage** — grep all severity assignments in `scripts/surface_inventory/`.
3.  **Baseline state** — read `scripts/surface_inventory/surface_baseline.json`, check schema version, count acceptances, identify stale entries.
4.  **Detector completeness** — list every `_findings()` function, what surfaces it covers, what it misses.
5.  **Gaps** — middleware boundary, admin guard, CSRF exemption, webhook signature, route comparison, beat schedule, settings surface.
6.  **False positives** — CSS asset coverage, beat task enqueue, backward-compat wrappers, example-only env vars.
7.  **False negatives** — dynamic routes, dynamic tasks, heavy conditional imports, computed env var names.
8.  **Output quality** — human readable? JSON stable? Redacted? Deterministic?
9.  **MCP context** — `tools/railrefund_mcp/context.py:get_drift_context()`: is it stale? Does it have summary?
10. **Performance** — does it import heavy modules? Does it run cargo? Does it scan vendor dirs?

## Verification commands

```bash
./lr 21
./lr 21 --json | python -m json.tool
./lr impact
./lr secrets
./lr 7
python -m pytest -q tests/unit/test_surface_drift_check.py -v --tb=short
git grep -n "P0\|P1\|P2\|P3" -- scripts/surface_inventory/
git grep -n "drift\|surface_drift\|baseline" -- scripts/ tests/
```

## Key reference paths

| What | Path |
|---|---|
| Entrypoint | `scripts/surface_drift_check.py` |
| Models & severity | `scripts/surface_inventory/models.py` |
| Baseline | `scripts/surface_inventory/baseline.py` |
| Baseline file | `scripts/surface_inventory/surface_baseline.json` |
| Backend manifest | `scripts/surface_inventory/backend_manifest.py` |
| Routes | `scripts/surface_inventory/routes.py` |
| Templates | `scripts/surface_inventory/templates.py` |
| Static assets | `scripts/surface_inventory/static_assets.py` |
| Env settings | `scripts/surface_inventory/env_settings.py` |
| Celery tasks | `scripts/surface_inventory/celery_jobs.py` |
| Alembic models | `scripts/surface_inventory/alembic_models.py` |
| Native/Rust | `scripts/surface_inventory/rust_native.py` |
| Frontend runtime | `scripts/surface_inventory/frontend_runtime.py` |
| Duplicate functions | `scripts/surface_inventory/duplicate_functions.py` |
| Coverage | `scripts/surface_inventory/coverage.py` |
| Reporting | `scripts/surface_inventory/reporting.py` |
| Findings (aggregation) | `scripts/surface_inventory/findings.py` |
| App loader | `scripts/surface_inventory/app_loader.py` |
| LR registry | `scripts/local_readiness_registry.py` (check 21) |
| LR child flags | `scripts/local_readiness_child_flags.py` |
| MCP context | `tools/railrefund_mcp/context.py` |
| Tests | `tests/unit/test_surface_drift_check.py` |
| Improvement plan | `docs/planned_implementations/lr_drift_improvement_plan.md` |
