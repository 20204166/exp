# OpenCode Session — 2026-07-08

## Skills reloaded
- **BugGuard** — full Mode A/B workflow, opposition templates, Agent 5 five-phase, mode_a_patch_review, completion/no-short-circuit rule. Mode B changes no app code or normal repo tests, but may create/run candidate-scoped PoC/counter-test evidence artifacts under `docs/bug_hunts/poc/BUG-YYYYMMDD-NNN/`.
- **audit-lr-drift** — drift audit specialist, P0–P3 severity, detector completeness, MCP context
- **repo-context-curator** — context hygiene, persona sync, quiet mode, anti-hallucination enforcement, line-count budget, approval gate

## Completed
- BUG-027/032/033/030/031 fixed and pushed
- BUG-034: Not a bug (intentional design)
- BUG-037 (P4 observability): fixed `_email_body_malicious_indicators` logging gap
- Full repo-wide audit completed (all folders); BUG-20260705-028 was fixed as a P4 observability gap in `app/services/auto_submit_persistence_steps.py`
- `bugguard-main-openai` primary agent added (`openai/gpt-5.3-codex-spark`)
- Mode C `app/core/database/db.py` startup perf patch accepted and pushed: cache only `_load_required_model_modules()` side effects; keep `Base.metadata` reads live and preserve failure timing.

## Key Decisions
- BugGuard model split follows `.opencode/agents/*.md` repo truth
- `bugguard-main-openai` has same task permissions as other BugGuard primaries
- Permission rule: Never edit `.opencode/agents/*.md` — user must do that themselves

## Critical Context
- **BUG-027 fix:** `auto_submit_evidence_store.py:91-97` — `db.rollback()` + `get_storage_backend().delete(path)` on commit failure
- **BUG-032 fix:** `auto_submit_field_resolver.py:160-169` — `_LOGGER.warning` before silent `return []`
- **BUG-033 fix:** `auto_submit_dynamic_apply.py:139-189` — `_LOGGER.warning` before silent `return ()`/`continue`
- **BUG-030 fix:** `auto_submit_native_plan.py:133` — `.strip()` in mismatch branch
- **BUG-031 fix:** `auto_submit_resume_flow.py:308-310` — replace merge with direct assignment
- **BUG-037 fix:** `app/jobs/email_ingest_task.py:127` — `logger.warning("email_body_malware_scan_error", exc_info=True)`
- **BUG-028 outcome:** `auto_submit_persistence_steps.py:57-78` still uses best-effort fault isolation, but now logs sanitized CSA persistence failures so the caller-observability gap is fixed; the shared-transaction claim remains disproven
- **Gold standard pattern:** `attachments.py:570-593` — `db.rollback()` + `get_storage_backend().delete()` for write-before-commit cleanup
- **Permission model:** `task` tool allowed for patterns `bugguard-opposer-*` and `bugguard-agent5`; general task calls denied
- **Primary agents:** `bugguard-main` (DeepSeek free), `bugguard-main-paid` (DeepSeek paid), `bugguard-main-openai` (GPT 5.3 Codex Spark)

## Relevant Files
- `docs/bug_hunts/bugs_found/bugs_found_3.md`: BUG-027/030/031/032/033/034/037 entries
- `docs/bug_hunts/bugs_found/bugs_found_4.md`: BUG-028/029/036 entries and current active volume
- `docs/bug_hunts/index.md`: master bug-hunt index and current status section
- `.opencode/persona.md`: Canonical persona source
- `.opencode/agents/bugguard-opposer-1.md` through `-4.md`: Registered subagents
- `.opencode/agents/bugguard-agent5.md`: Agent 5 subagent
- `.opencode/skills/repo-context-curator/SKILL.md`: Repo context hygiene skill — invoke proactively when context files drift stale

---

For the full CLAUDE.md reference (MCP, lr commands, planning, architecture, CI, production stack), read `CLAUDE.md` in the repo root.

---

# OpenCode Session — 2026-07-11

## Completed
- BUG-20260710-044: Fixed `security_probe.py` cookie_flags() — flagged missing Secure/SameSite on session cookies. Pushed in b93be0bf.
- BUG-20260710-043: Already fixed in d95f5dc8 (queuedIndex mechanism). Ledger updated to Fixed.
- BUG-20260710-042: Already fixed in 26131e1d (Live badge gated on `has_provider_backed_monitoring`). Ledger updated to Fixed.
- SEC-20260711-001: Mode D security audit of `security.py`, `csrf.py`, `jinja_setup.py`, `config.py` — no vulnerabilities. Pushed in 1afbba30.
- opencode.json: MCP `--repo-root` changed from `"."` to `"/root/railrefund"`.
- repo-context-curator: OPCODE.md stale line reference fixed (CLAUDE.md 908→305 lines). Session log updated.
- docs/planned_implementations: implemented plan docs compacted to short synopsis stubs; README index kept as the discoverability pointer.
- Workspace nav jitter fix landed and was pushed: collapsed-state centering classes removed from `_partials/nav.html`, dead `data-collapsed` overrides removed from `_kit-base.css`, and the compiled CSS bundle was rebuilt and committed because repo truth currently tracks `app/static/css/railrefund.css`.

---

# OpenCode Session — 2026-07-15

## Completed
- Compliance skill evolved into specialised legal/compliance reviewer workflow under `.claude/skills/Compliance/`.
- Compliance OpenCode subagents added under `.opencode/agents/`: `compliance-reviewer-1` through `compliance-reviewer-5` and `compliance-evidence-auditor`.
- Compliance primary agents added to `opencode.json`: `compliance-main`, `compliance-main-paid`, `compliance-main-openai`.

## Key Decisions
- BugGuard opposer and Agent 5 files were intentionally not touched.
- Compliance main agents mirror BugGuard main task-permission structure but allow only `compliance-reviewer-*` and `compliance-evidence-auditor` task targets.
- Compliance Evidence Auditor performs evidence QA only and does no new legal research.

---

# OpenCode Session — 2026-07-16

## Completed
- Service-test cleanup continued through `app/tests/services/` with low-risk helper extractions and contract-edge simplifications.
- `lr 7` caught `app/tests/services/test_claim_pipeline.py` at 813 lines after local helper growth; the shared trip/decision factories moved to a sibling helper module to keep the file under the 800-line gate.
- `test_claimpack_pdf_contract_edges.py` was reduced with a single parametrized missing-departure check; `test_reconcile.py` gained a tiny incoming-trip factory to remove repeated setup.

## Key Lesson
- When a service-test refactor pushes a file toward the 800-line limit, split shared factories into a companion helper module instead of leaving the file oversized.

---

# OpenCode Session — 2026-08-01

## Completed
- MCP `lr_run_readonly` now auto-backgrounds every allowlisted check (`lr <check> -b`) and returns immediately with PID/log-path/`--view`/`-b stop` info; added the missing `lr static --check` allowlist entry and a `backgrounded` flag on `CommandResult`. Pushed in 034159e3. `lr --version`, `lr docker status`, `lr dev status` stay foreground (sub-CLI/version queries). No `local-readiness` wheel rebuild needed — restart the MCP server to pick it up.
- repo-context-curator: CLAUDE.md / `.agents/AGENTS.md` / BugGuard SKILL.md updated to document the auto-backgrounded MCP check behavior.

## Key Lesson
- For MCP stdio servers (`python -m tools.railrefund_mcp.server`), code changes take effect on MCP restart only; `lr` wheel rebuild is only needed for `scripts/local_readiness/` edits.
