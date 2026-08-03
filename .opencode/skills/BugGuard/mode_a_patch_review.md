# Mode A patch-review lifecycle and rules

Read this file when a Mode A code-edit validation uses selective validators or full A4 and needs a patch-review file.

## Selected validator write/read rules

For every selected validator, the main auditor must:

1. Spawn the registered subagent (`bugguard-opposer-1` through `-4`) or, if unavailable, a separate independent subagent assigned that exact role under the portable fallback in `SKILL.md`.
2. Provide the patch-review file path.
3. Provide the patch diff.
4. Provide the original bug/task evidence.
5. Provide target files and their callers/callees.
6. Provide tests/checks output.
7. Require the validator to use exact repo evidence, test evidence, command output, or official docs.
8. Require the validator to write its own findings directly into its own section of the patch-review file.
9. Do not simulate missing validator or Agent 5 findings, and do not let the main auditor substitute its own review.
10. If a selected validator fails to return, report incomplete validation — do not fill in the section with guesses.

## Artifact ownership

The patch-review artifact is the source of truth for Mode A adversarial review.

- The main auditor owns the scaffold, patch summary, evidence index, and final synthesis.
- The main auditor may create the patch-review file, fill the header, and write the main auditor candidate summary.
- Each selected validator owns only its own validator section and must write that section directly into the artifact.
- Agent 5, when required, owns only the Agent 5 evidence audit section and must write it directly into the artifact.
- The main auditor must not fill reviewer-owned sections or Agent 5 sections.
- Reviewer and Agent 5 sections must not be backfilled by the main auditor.
- General AI output is not a substitute for writing the required section into the review/opposition artifact.
- If a selected validator or Agent 5 cannot write its required section into the artifact, the review is incomplete and must be reported as incomplete instead of treating the reviewer as complete.
- The final synthesis may summarize reviewer findings only after the required reviewer-owned sections exist in the artifact.

## Artifact write enforcement

Reviewer-owned sections must be authored directly by the assigned reviewer in the artifact.

The main auditor must not write, paste, transcribe, summarize, or backfill reviewer-owned sections or Agent 5 sections.

General AI output, terminal output, chat output, or copied reviewer text does not satisfy the artifact requirement.

If the selected reviewer cannot write directly to its required artifact section, the review is incomplete. The main auditor must report an orchestration/tooling gap instead of treating the reviewer as complete.

The main auditor may reference incomplete external reviewer output only as non-authoritative context, not as a completed reviewer section.

Final synthesis may begin only after all required reviewer-owned artifact sections exist.

For Mode A, selected validator/reviewer sections must be written directly into the patch-review artifact by the assigned reviewer. The main auditor must not capture or paste validator output into these sections.

## Agent 5 Mode A reading checklist

If Agent 5 is used in Mode A (full A4 only), it must read these before writing its audit:

1. The patch-review file
2. The patch summary
3. The diff summary or current git diff
4. The original bug/task evidence
5. All selected validator findings (must be complete before Agent 5 starts)
6. Tests/checks output
7. Relevant target files and nearby files
8. Relevant repo docs/plans only as context
9. Official framework/library docs if semantics matter
10. Prior bug ledgers/rejected hypotheses only if related

Agent 5 must not write its audit until those inputs are read or honestly reported unavailable.

Agent 5 writes its evidence audit into the patch-review file under `## Agent 5 evidence audit`.

Agent 5 must not:
- Patch code
- Update final bug status
- Run writer/apply commands
- Treat partial/missing validator findings as complete
- Claim a command passed if it did not run
- Use vague internet claims as proof
- Hide uncertainty

## Full A4 no-peeking sequence

For full A4 Mode A, mirror Mode B sequencing:

1. Main auditor creates the patch-review file with mode/risk/patch details filled in.
2. Main auditor spawns all four opposing agents first, providing each with the patch-review file, patch diff, target files, and test/check output.
3. Each opposing agent writes findings into the patch-review file.
4. Main auditor waits for all four to complete (all four sections filled).
5. Main auditor spawns Agent 5 with the completed patch-review file (all four findings present), patch diff, target files, test/check output, and the [Research Link Pack](./research_link_pack.md).
6. Agent 5 reads all inputs (checklist above), writes its audit into the patch-review file.
7. Only after Agent 5 completes, the main auditor reads all findings and writes the rebuttal.

For selective Mode A without Agent 5, the main auditor may read selected validator findings as they return, but final synthesis still waits until the required reviewer-owned sections exist in the artifact.

For selective Mode A with Agent 5, the main auditor must not make the final decision until Agent 5 has read the patch-review file and completed its audit.

## Patch-review lifecycle

### Creation

- Create `docs/bug_hunts/patch_reviews/PATCH-YYYYMMDD-NNN-review.md` only when at least one validator is selected.
- Do not create for low-risk Mode A with no validators.
- Use the template in [`patch_review_template.md`](./patch_review_template.md).
- Number sequentially: first review in a day is `PATCH-YYYYMMDD-001`, next is `-002`, etc.
- The PATCH ID is independent of BUG IDs — it tracks the review, not the bug.

### Deletion

Delete the temporary patch-review file after final report unless:
- The patch fixes a ledgered BUG (link from the BUG entry)
- The user asks to preserve audit evidence
- Validator/Agent 5 findings identify unresolved risk
- Repo policy says to archive evidence

### Preservation

If preserved:
- Link from the relevant BUG entry: `Mode A patch review: docs/bug_hunts/patch_reviews/PATCH-YYYYMMDD-NNN-review.md`
- Link from the final report if no BUG entry exists
- Do not add Mode A patch-review files to Mode B BUG ledgers unless the patch directly fixes an existing BUG entry and repo policy says to link them

### Deletion fallback

If deleted, copy the final decision summary into the final response. The record of adversarial review is in the main auditor's report, not in a permanent file.

## Linking to BUG entries

When a Mode A patch directly fixes a ledgered BUG:
- Add a link in the BUG entry: `Mode A patch review: docs/bug_hunts/patch_reviews/PATCH-YYYYMMDD-NNN-review.md`
- The patch-review file is patch-safety evidence, not a replacement for the BUG ledger entry
- The BUG entry's status still follows the BUG ledger lifecycle (Candidate → Validated → Fixed)

## Main auditor research pack

For Mode A patch validation where external semantics affect the patch or tests, use [`main_auditor_research_pack.md`](./main_auditor_research_pack.md) before creating new tests or choosing static/native/frontend checks.

If a code-edit task is primarily performance-related, transition to Mode C. If Mode C exposes a correctness bug introduced by the current patch, transition back to Mode A and repair correctness before measuring performance. If the suspected bug is pre-existing and outside scope, pause implementation and use Mode B only with approval.
