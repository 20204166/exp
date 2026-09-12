# BugGuard Findings

## BUG-20260912-001 - Thermals page stuck at waiting for samples

- Status: Validated downgraded bug
- Severity: P2 user-facing cross-platform thermal state defect
- Created: 2026-09-12
- Scope: Thermal acquisition-to-render state for local and remote node summaries.
- Opposition: full B7 completed; temporary opposition artifact removed after synthesis.
- PoC folder: `docs/bug_hunts/poc/BUG-20260912-001/`
- Mode A patch review: `docs/bug_hunts/patch_reviews/PATCH-20260912-001-review.md`
- Initial evidence: `tests/thermal_capability_gap_red.py` fails after 1000 empty supported summaries because the state remains `NO_DATA`.
- Candidate decision: Full B7 confirmed a deterministic state/presentation defect;
  severity downgraded from P1 to P2. Phase 3 fix-forward is approved.

## BUG-20260910-001 - Full application release and extraction wiring audit

- Status: Validated downgraded bug for H2; H1 not a bug on current evidence
- Severity: P3 for H2
- Created: 2026-09-10
- Scope: Installed-versus-source runtime selection, wheel/install verification, extracted window/UI composition, and node projection state.
- Opposition: `docs/bug_hunts/opposition/BUG-20260910-001-opposition.md`
- PoC folder: `docs/bug_hunts/poc/BUG-20260910-001/`
- Candidate hypotheses:
  - H1: the interpreter/launcher used after installation can load an older installed distribution than the source/wheel just built.
  - H2: the extracted UI/node projection can display a duplicate local-looking node because identity/context state is not reconciled at the composition boundary.
- Initial evidence: the active repository `.venv` reports installed metadata `1.3.7.1` while importing source modules reports `maintenance.__version__ == 1.4.0.2`; the screenshot shows two “This System” rows in All Systems, with one trusted/unknown row.
- Final decision: H1 not a bug on current evidence; H2 validated downgraded P3 conditional UI/state bug, fixed by stable-ID display disambiguation. Online PowerShell verification hardening also added.

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
