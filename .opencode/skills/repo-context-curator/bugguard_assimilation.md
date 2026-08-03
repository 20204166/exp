# BugGuard Assimilation

This file explains how repo-context-curator absorbs durable BugGuard lessons without bloating persistent context.

## Scope

Use this when BugGuard Mode A or Mode B work has produced new durable workflow lessons, or when bug-hunt output changes need to inform shared repo-agent context.

## Sources to inspect

- `docs/bug_hunts/bugs_found/*.md`
- `docs/bug_hunts/index.md`
- `docs/bug_hunts/patch_reviews/*.md`
- `docs/bug_hunts/opposition/*.md`
- `.opencode/skills/BugGuard/SKILL.md`
- BugGuard support files if they changed

## What may be promoted into `.opencode/persona.md`

Promote only durable workflow lessons, such as:

- evidence-first debugging habits that repeatedly prevent false positives
- repo-truth checks that keep agents from trusting plans or summaries over current files
- no-regression habits that protect public contracts and hidden-test-sensitive behaviour
- durable safety or privacy boundaries that kept reappearing across BugGuard work
- review habits that are broadly useful for future repo work

Keep the persona concise. Promote the lesson, not the whole episode.

## What must stay in bug ledgers and review files

Keep these in their original bug-hunt or patch-review files:

- specific BUG IDs
- candidate-specific reproduction steps
- counter-test details
- reviewer disagreements
- evidence transcripts
- patch-by-patch reasoning
- raw logs or large output excerpts
- full debate history

Do not copy full ledgers, patch reviews, or opposition transcripts into persistent context.

## Promotion rule

Promote only durable workflow lessons, not individual bug details.

If a BugGuard failure happened because persona guidance was ignored, place the enforceable rule in BugGuard or the active skill workflow first, then reflect only the durable remainder in persona/context.

## Safe assimilation pattern

1. Read the relevant bug-hunt files.
2. Identify the durable lesson.
3. Confirm it is not a one-off bug detail.
4. Add a short persona signal or working-style rule only if it will help future repo work.
5. Leave the detailed evidence in the bug-hunt or patch-review file.

## Never store here

- secrets
- raw logs
- OCR text
- provider payloads
- private URLs
- user uploads
- database rows
- sensitive personal data
- full opposition reasoning or full bug ledgers
