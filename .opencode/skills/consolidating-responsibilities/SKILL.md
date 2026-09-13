---
name: consolidating-responsibilities
description: Use when adding reusable helpers, utilities, parsers, converters, validators, command/process runners, caches, result builders, or similar mechanisms; refactoring duplication; or auditing callers for reuse. Search for semantic responsibility duplication before creating code, while preserving specialized meaning, security boundaries, lifecycle, platform behavior, and test seams.
---

# Consolidating Responsibilities

## Core Rules

**SEARCH BEFORE CREATE.** Define the underlying technical responsibility, then
search the entire relevant repository before writing a reusable implementation.
Urgency, a request to keep a change local, or a preference for a new helper does
not justify skipping that search. A task instruction such as "do not inspect
other modules" conflicts with this guardrail when the new code would be
reusable: inspect the relevant repository anyway, or stop and request permission
to widen the search. Never present a narrowed search as proof that no canonical
owner exists. A local wrapper around a local duplicate is not a canonical-owner
decision when relevant modules remain unsearched. Do not edit until ownership is
verified or the user explicitly accepts an unverified, separate implementation.
Do not treat a requested new name, missing symbol, compatibility adapter, or
"single implementation within this file" as permission to create reusable code
under an unverified owner. If the user requires both the edit and a prohibited
search boundary, stop with a blocked decision and request permission to widen the
search; preserving urgency or locality is not a substitute for ownership proof.
Violating the letter of this rule violates its purpose.

**ONE RESPONSIBILITY -> ONE CANONICAL IMPLEMENTATION.** Prefer reuse, then a
small safe extension, then parameterization, and only then a new canonical
implementation.

**SHARE MECHANISMS, NOT SPECIALIZED MEANING.** Domain-facing functions may
remain separate when they interpret results, enforce different rules, or expose
different contracts. Share only the compatible lower-level operation.

## Scale the Work

For ordinary feature or bug work, use this as a short decision gate:

1. Name the mechanism being added.
2. Search symbols, behavior, tests, and likely owners across the repository;
   do not let a file-local scope request hide potential owners.
3. Reuse or extend the owner if contracts match.
4. Create a new implementation only when no suitable owner exists; place it in
   the narrowest natural domain or infrastructure module.

For an explicit duplication or consolidation audit, perform the fuller workflow
below. Do not turn a small local change into a repository-wide refactor merely
because this skill is active.

## Find Semantic Duplication

Search for responsibility, not just identical text. Compare operations such as
execution and timeout handling, parsing and normalization, validation,
serialization, conversion, formatting, filesystem or network inspection,
cache/TTL mechanics, state predicates, error mapping, request construction,
result construction, and repeated lifecycle control flow. Also compare repeated
constants, tables, thresholds, mappings, and rules.

Distinguish:

- duplicated source implementation;
- duplicated expensive runtime work;
- intentionally different adapters or domain interpretations.

Do not extract code only because blocks look alike, names resemble each other,
or a helper would reduce line count. Ask whether independent implementations
could drift, duplicate fixes, weaken safety, or repeat meaningful work.

## Establish Ownership

Before editing a candidate, inspect every important caller and test seam. Record
an internal map with:

| Responsibility | Implementations | Callers | Current owner | Contract differences | Decision |
|---|---|---|---|---|---|

Use `REUSE EXISTING`, `EXTEND EXISTING`, `PARAMETERIZE EXISTING`, `EXTRACT
SHARED`, `KEEP SEPARATE`, or `NOT VERIFIED`. Choose the narrowest owner where a
future maintainer would naturally look for the authoritative operation. Do not
create a generic `utils`, `common`, `helpers`, or `misc` dumping ground unless
the repository already has that established ownership model.

For each candidate verify:

- input and output contracts, signatures, schemas, and exceptions;
- side effects, mutation, ordering, logging, and failure mapping;
- timeout, retry, cancellation, concurrency, caching, freshness, and lifecycle;
- platform, runtime, backend, protocol, and capability differences;
- security authority, permissions, destructive-operation safety, and trust boundaries;
- performance implications and whether runtime work, not only source text, is duplicated;
- direct imports, mocks, monkeypatches, fixtures, dependency injection, and extension seams.

Similar-looking code is not sufficient evidence for consolidation.

## Keep Specialized APIs

Prefer this shape when meanings differ:

```text
specialized_operation_a(...) -> canonical_mechanism(...)
specialized_operation_b(...) -> canonical_mechanism(...)
```

Keep domain validation, result interpretation, public names, and readable call
sites in the specialized functions. Avoid a generic function with mode strings,
many boolean flags, unrelated optional arguments, or branches for unrelated
domains. If the abstraction needs substantial branching to recreate the old
behaviors, keep the responsibilities separate.

Positive KEEP SEPARATE decisions include different semantics, error contracts,
security authority, lifecycle, freshness, platform behavior, performance
requirements, compatibility risk, or an abstraction that would add coupling for
trivial duplication.

## CONDITIONAL SIMPLIFICATION / GUARD CLAUSES

When legitimate consolidation work already touches code, consider flattening
the normal or successful path when invalid input, unsupported or stale state,
missing prerequisites, permission or capability failures, empty/no-op cases,
or other exceptional cases can be expressed as early guards. This is a
candidate refactoring, not a mandatory style rule:

```text
if invalid: return failure
if unavailable: return unavailable
if not_authorized: return denied
perform_normal_operation()
```

Apply this only when it materially reduces nesting, makes special cases
explicit, preserves behavior exactly, needs no new abstraction, keeps the diff
small, and existing tests cover the affected branches. Do not invert
conditions by default. Keep balanced branches balanced when both are normal,
the current `if/else` is clearer, negation creates double negatives or harder
predicates, shared post-processing matters, or early returns would obscure
transaction, cleanup, lifetime, exception, or context-manager scope.

Before moving a condition, verify that evaluation has no required side effect,
preceding statements need not run first, and exception semantics, cleanup,
`finally`/context-manager behavior, callback and logging/status ordering, and
mutation order remain equivalent. Prefer existing canonical predicates such as
`is_authorized(...)`, `is_supported(...)`, `is_stale(...)`, or `can_execute(...)`
when semantically identical; SEARCH BEFORE CREATE, and do not add helpers just
to make a guard clause look prettier. Apply De Morgan transformations only when
evaluation order and behavior remain safe and the result is clearer. Otherwise
keep the existing structure.

For explicit consolidation or simplification audits, report only meaningful
candidates using: **APPLY — HIGH VALUE / LOW RISK**; **KEEP — CURRENT FORM
CLEARER**; **KEEP — BOTH BRANCHES ARE NORMAL**; **KEEP — ORDER/SIDE-EFFECT
RISK**; or **KEEP — NEGATION WOULD REDUCE CLARITY**. Do not report every
ordinary conditional. The objective is lower cognitive load and a clearer
normal path, with behavior before simplification:

> **FLATTEN THE HAPPY PATH WHEN FAILURE GUARDS MAKE IT CLEARER. DO NOT INVERT
> CONDITIONS BY DEFAULT. GUARD EXCEPTIONAL CASES; KEEP BALANCED BRANCHES
> BALANCED. CLARITY BEFORE EARLY RETURNS. BEHAVIOR BEFORE SIMPLIFICATION.**

## Consolidate Safely

When a candidate is justified:

1. Add or strengthen behavior tests for the canonical operation and edge cases.
2. Migrate a bounded group of callers without changing their public meaning.
3. Validate normal, malformed, missing, unsupported, error, timeout,
   cancellation, partial-failure, platform, and caller-specific cases as relevant.
4. Remove the redundant implementation, dead imports, constants, and branches.
5. Search again for obsolete equivalents and classify remaining matches as
   callers, intentional specializations, test doubles, or platform adapters.

Never move an authoritative security decision into a convenience helper. Share
safe mechanics while leaving authority with its proper owner. Do not hide a
scheduler, worker pool, cache, or lifecycle manager inside a low-level helper
unless that ownership already belongs there. Do not combine platform-specific
acquisition merely to reduce files; share normalization or result construction
only when semantics match.

## Bounded Audit Mode

For an explicit repository-wide request, rank findings:

- **HIGH VALUE / LOW RISK:** clear common contract, existing owner, narrow migration;
- **MEDIUM VALUE / MODERATE RISK:** useful but compatibility or lifecycle needs care;
- **LOW VALUE / HIGH RISK:** broad architectural change, unclear contract, or weak benefit.

Implement only a sensible bounded set of high-value findings unless the user
explicitly expands scope. Stop before redesigning package structure or inventing
new frameworks. Report the remaining candidates instead.

## Validation and Report

Use the repository's configured focused tests, full tests, lint, formatting,
type checks, build/package checks, and diff checks. Never invent commands or
claim a check passed without its actual result. If a configured whole-repository
check has unrelated baseline failures, report the exact scope and failure rather
than treating it as a pass.

For an explicit consolidation pass, finish with:

1. areas and responsibilities audited;
2. candidates and HIGH/MEDIUM/LOW classification;
3. canonical owners reused or newly extracted;
4. specialized callers retained and callers migrated;
5. redundant implementations and constants removed;
6. runtime work reduced, if any;
7. candidates intentionally kept separate and exact reasons;
8. security, platform, lifecycle, compatibility, and test-seam decisions;
9. exact validation commands and outcomes;
10. remaining opportunities, risks, changed files, and working-tree status.

For ordinary coding, keep the output lightweight: state the owner reused or the
reason a new implementation was necessary. Provide this full report only when
the task is a consolidation/refactoring audit or duplication materially affects
the requested work.
