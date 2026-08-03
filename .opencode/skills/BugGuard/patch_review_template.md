# PATCH-YYYYMMDD-NNN — Mode A patch review

## Artifact ownership

The Mode A patch-review artifact is the source of truth for adversarial review.

- The main auditor owns the scaffold, patch summary, evidence index, and final synthesis.
- Each selected reviewer owns only its own reviewer section and must write that section directly into the artifact.
- Agent 5, when required, owns only the Agent 5 evidence audit section and must write it directly into the artifact.
- The main auditor must not fill reviewer-owned sections.
- Reviewer and Agent 5 sections must not be backfilled by the main auditor.
- General AI output is not a substitute for writing the required section into the review/opposition artifact.
- If a selected reviewer or Agent 5 cannot write its required section into the artifact, the review is incomplete and must be reported as incomplete instead of treating the reviewer as complete.
- For Mode A patch review, any selected reviewer/checker sections in the patch-review artifact must exist before the main auditor final synthesis treats review as complete.

## Artifact write enforcement

Reviewer-owned sections must be authored directly by the assigned reviewer in the artifact.

The main auditor must not write, paste, transcribe, summarize, or backfill reviewer-owned sections or Agent 5 sections.

General AI output, terminal output, chat output, or copied reviewer text does not satisfy the artifact requirement.

If the selected reviewer cannot write directly to its required artifact section, the review is incomplete. The main auditor must report an orchestration/tooling gap instead of treating the reviewer as complete.

The main auditor may reference incomplete external reviewer output only as non-authoritative context, not as a completed reviewer section.

Final synthesis may begin only after all required reviewer-owned artifact sections exist.

For Mode A, selected validator/reviewer sections must be written directly into the patch-review artifact by the assigned reviewer. The main auditor must not capture or paste validator output into these sections.

## Mode and risk

BugGuard mode: Mode A — code-edit validation
Risk level: low / medium / high / contradictory
Validator threshold: none / selective / full A4
Reason:

## Patch summary

## Original bug / task evidence

## Diff summary

## Tests and checks run

## Static/type/format checks

## Selected validators

## Validator findings

### Opposing Agent 1 — Patch/Reproduction Skeptic
not used

### Opposing Agent 2 — Repo-Truth Skeptic
not used

### Opposing Agent 3 — Architecture/Security Skeptic
not used

### Opposing Agent 4 — External-Research Skeptic
not used

## Agent 5 evidence audit
not used

## Main auditor rebuttal

## Final patch decision
safe / unsafe / needs more evidence

## Remaining risk
