# BugGuard Findings

## BUG-20260909-001 - Component edge-case audit

- Status: Partially validated; split by hypothesis after full B7
- Severity: P1/P2 findings, downgraded where evidence requires
- Created: 2026-09-09
- Scope: Legacy `window.py`/facade paths and extracted `maintenance/components/`, UI, persistence, network, action, installer, and thermal paths.
- Opposition: `docs/bug_hunts/opposition/BUG-20260909-001-opposition.md`
- PoC folder: `docs/bug_hunts/poc/BUG-20260909-001/`
- Mode A patch review: `docs/bug_hunts/patch_reviews/PATCH-20260909-012-review.md`
- Final decision: 6 validated bugs, 2 validated downgraded P2 bugs, 2 needs-more-evidence hypotheses

### Per-hypothesis decisions

- H1 Zeroconf peer-map callback/expiry race: Validated downgraded bug, P2.
- H2 Permission toggle drops unrelated permissions: Validated bug, P2.
- H3 Colour save failure loses the previous colour: Validated bug, P2.
- H4 Invalid UTF-8 store files block documented startup fallback: Validated bug, P1 pending product severity confirmation.
- H5 Manual node ports accept values outside 0..65535: Validated bug, P2.
- H6 Thermal thresholds render outside the visible graph: Validated bug, P2.
- H7 TypeError-text fallback may repeat partial work: Needs more evidence.
- H8 Destructive-action check/use races: Validated downgraded bug, P2.
- H9 PowerShell online reinstall omits same-version force reinstall: Validated bug, P2.
- H10 Broad keyboard/accessibility claim: Needs more evidence; narrow manual-host layout concern remains unproven.

Evidence and opposition are recorded in `docs/bug_hunts/opposition/BUG-20260909-001-opposition.md`.
