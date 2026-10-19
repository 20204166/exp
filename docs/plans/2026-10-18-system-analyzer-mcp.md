# System Analyzer MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a separate, Git-ignored MCP server copy adapted for read-only System Analyzer inspection, without modifying the Expra Connect MCP source.

**Architecture:** Copy the source package under `tools/system_analyzer_mcp/`, then replace its Connect-specific surface with a small MCP server calling `algo.Analyzer`. Keep MCP dependencies/config isolated from the app; ignore the copied package and local launcher config as requested.

**Tech Stack:** Python, MCP Python SDK, existing `algo.Analyzer`/`maintenance.models`, unittest, ruff, pyright, mypy.

---

## File map

- Create `tools/system_analyzer_mcp/`: a separate Analyzer adaptation using the source package's Python MCP packaging and server patterns, with Analyzer-specific tests, metadata, and README. Do not carry over Connect-only implementation. The source `/home/btn17/Downloads/expra-connect/tools/expra_connect_mcp/` is input only and must not be edited.
- Modify `.gitignore`: ignore `tools/system_analyzer_mcp/` and local MCP config/venv paths.
- Create `.mcp.json.example`: portable local launcher pattern; do not put absolute paths or secrets in it.
- Create `.mcp.json` only if it contains the local checkout's launcher path and remains ignored.
- Reuse `algo.Analyzer` and `maintenance.models`; do not change scanner or app code.

## Task 1: Copy package and establish ignored local setup

- [x] Create the separate adapted package using the source's MCP server/packaging patterns; omit generated artifacts and Connect-only code.
- [x] Name package metadata, Python module, executable entry point, README, and server identity for System Analyzer MCP; include no Connect-specific runtime settings.
- [x] Add ignore entries for `tools/system_analyzer_mcp/` and `.mcp.json`. Confirm entries are narrowly scoped; this checkout has no Git metadata, so `git check-ignore` is unavailable.
- [x] Add `.mcp.json.example` with a checkout-relative launcher and document the local virtualenv/install setup. Add an ignored, machine-local `.mcp.json` for this checkout.
- [x] Confirm the original source MCP tree is unchanged using `git status --short -- tools/expra_connect_mcp` and `git diff --check -- tools/expra_connect_mcp` in `/home/btn17/Downloads/expra-connect` (both clean).

## Task 2: Replace Connect tools with Analyzer tools (TDD)

- [x] Write focused protocol tests for exactly the four read-only Analyzer tools.
- [x] Observe the initial tests fail because the new MCP module was missing, then implement to the passing state.
- [x] Implement Analyzer-backed handlers and reuse the snapshot serializer.
- [x] Validate component keys and optional storage roots; expose no command or mutation operation.
- [x] Mark tools read-only; return structured results, cap list output, and contain scanner failures at the MCP boundary.
- [x] Test result shapes, invalid input, result limits, read-only registration, and stdio launch.
- [x] Run focused MCP tests: 7 tests passed.

## Task 3: Finish package docs and verification

- [x] Document setup, local config, stdio launch, available tools, read-only guarantees, and source-package separation.
- [x] Install into `tools/system_analyzer_mcp/.venv` and validate stdio initialization without opening Tk.
- [x] Run `ruff check .` and `ruff format --check .`; repo-wide checks report existing issues outside the MCP package (9 Ruff findings and 28 files needing formatting). MCP-specific Ruff checks pass.
- [x] Run repo-wide `pyright` and `mypy --ignore-missing-imports`; they report existing findings outside the MCP package (6 Pyright errors and 15 mypy errors). MCP-specific checks pass with 0 Pyright errors and no mypy issues.
- [x] Run `scripts/run_tests.sh`: 1,981 tests passed.
- [x] Review ignore patterns directly and check source-repo status; the current checkout lacks Git metadata, so ignored/untracked status cannot be verified here. The Expra Connect MCP source path has no Git changes.

## Self-review

- Spec coverage: separate untouched source / copied package is covered by Tasks 1 and 3; read-only Analyzer tools and validation are covered by Task 2; ignored local setup is covered by Tasks 1 and 3; focused and repository-wide verification is covered by Task 3.
- Deviation: rather than copying Connect-specific source modules and deleting them, the new local package uses the applicable MCP server/packaging patterns in a separate minimal Analyzer package. This avoids leaving irrelevant Connect code or tools in the ignored copy.
- This checkout has no Git metadata available in the current environment. Git-ignore behavior can be checked with `git check-ignore` only when the repository metadata is available; do not claim commit/status validation if Git remains unavailable.
