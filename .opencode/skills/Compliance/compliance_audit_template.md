# Compliance Audit — COMP-YYYYMMDD-NNN

**Artifact path:** `docs/compliance/audits/COMP-YYYYMMDD-NNN.md`
**Skill:** Compliance (`.claude/skills/Compliance/SKILL.md`)
**Convention note:** If the repository has an existing compliance-audit convention that conflicts with this path, use the repo convention and note the deviation here.

---

## Header metadata

```text
Audit ID: COMP-YYYYMMDD-NNN
Created: YYYY-MM-DD
Last researched: YYYY-MM-DD
Audit date: YYYY-MM-DD
Organisation/activity:
Product/service:
Scope:
Jurisdiction:
Operational date:
Documents reviewed:
Implementation surfaces reviewed:
Out of scope:
Assumptions:
```

> No broad "all laws" audit. Scope is explicit. Regulators named below have had their remit and applicability proven in the applicability analysis.

## Legal-domain and regulator routing

```text
Primary legal domain:
Secondary legal domains:
Primary regulator:
Secondary regulator:
Possible regulator:
Regulator considered but not applicable:
Evidence for regulator remit:
Unresolved routing questions:
```

## Spark register

| Spark ID | Source | Spark text | Domain hint | Regulator hint | Score | Became |
|---|---|---|---|---|---|---|

Sparks do not carry compliance status. Only sparks scored 3–4 entered the staged audit as claims/questions.

## Document inventory

| path | title | owner | purpose | audience | jurisdiction claimed | effective date | review date | source citations | linked implementation | conflicts/duplicates | stale/missing metadata |
|---|---|---|---|---|---|---|---|---|---|---|---|

Conflicting documents detected: list them; do not silently choose one.

## Claim register

| Claim ID | Source document | Source location | Claim text (exact/paraphrase) | Implied legal proposition | Implied implementation commitment |
|---|---|---|---|---|---|

Extract atomic claims. Do not audit at paragraph-summary level. Each claim has a stable ID.

## Source register

Maintained per source using `source_record_template.md`. Summary table:

| Source ID | Title | Publisher/body | Source type | Authority tier | URL | Jurisdiction | Citation | Publication date | Effective date | Access date | Current/superseded/draft/archived | Exact words verified | Conflicting authority | Research limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

Full records are appended per-source below this table when used.

## Requirement register

| Requirement ID | Authority source | Requirement type | Subject | Trigger | Required action | Deadline/frequency | Exceptions | Evidence required | Uncertainty |
|---|---|---|---|---|---|---|---|---|---|

Requirement type: mandatory legal duty / conditional legal duty / regulator rule / statutory-code expectation / regulator guidance / recognised good practice / internal policy commitment. Do not conflate internal policy commitment with legal duty.

## Applicability analysis

| Requirement ID | Jurisdiction | Organisation legal role | Activity | Affected group | B2B/B2C | Threshold/exemption check | Applicability status | Evidence | Missing facts |
|---|---|---|---|---|---|---|---|---|---|

Applicability status: applies / likely applies / may apply / does not appear to apply / unresolved. If unresolved, do not continue as though the rule applies.

## Temporal analysis

| Requirement ID | Source date | Effective date | Commencement check | Amendments/outstanding changes | Transitional/savings/sunset | Version at document issue date | Current version | Version at planned operational date |
|---|---|---|---|---|---|---|---|---|

Do not assume enactment means commencement; publication means legal effect; consultation means current law; archived guidance means current guidance.

## Repository evidence mapping

| Requirement / Claim ID | Evidence surface | Repo path | Exact evidence | Capability vs deployment | Provider dependence | Evidence status |
|---|---|---|---|---|---|---|

Evidence status: read / inferred / missing. Do not infer implementation from document wording; read actual implementation. Capability ≠ deployment.

## Initial gap findings

| Finding ID | Requirement / Claim ID | Applicability | External legal/regulatory finding | Internal document finding | Implementation finding | Operational/deployment finding | Overall status | Evidence summary |
|---|---|---|---|---|---|---|---|---|

Use the bounded status vocabulary from `SKILL.md`. Do not call a gap a legal breach without sufficient evidence. The four finding types are separated, not merged. Each may carry its own status; the overall status is the bound of the four.

## Reviewer 1 — Authority & Currency Review

> Owned by Reviewer 1. Main auditor must not write, paste, transcribe, summarise, or backfill this section. If Reviewer 1 cannot write independently, mark `Review incomplete: <reason>`.

- Sources re-located:
- Authority classifications verified/corrected:
- Commencement checks:
- Amendment/repeal/outstanding-change checks:
- Guidance current/superseded/draft/archived checks:
- Case-law status checks:
- Authority conflicts:
- Findings overturned or confidence-capped:
- Outcome: complete / incomplete

## Reviewer 2 — Applicability Review

> Owned by Reviewer 2. Reads the initial audit and the verified authority record. Main auditor must not backfill this section. If Reviewer 2 cannot write independently, mark `Review incomplete: <reason>`.

- Legal framework challenged:
- Jurisdiction checks:
- Territorial scope checks:
- Organisation role checks:
- Affected group and B2B/B2C checks:
- Threshold/exemption checks:
- Regulated-activity checks:
- Applicability status changes:
- Missing facts:
- Findings overturned or confidence-capped:
- Outcome: complete / incomplete

## Reviewer 3 — Repository Compliance Review

> Owned by Reviewer 3. Reads the initial audit and the verified applicability record. Main auditor must not backfill this section. If Reviewer 3 cannot write independently, mark `Review incomplete: <reason>`.

- Documents re-read:
- Implementation surfaces checked:
- Tests checked and limitation stated:
- Feature flags/config keys checked without secret values:
- Policy-vs-code contradictions:
- Repository evidence gaps:
- Findings overturned or confidence-capped:
- Outcome: complete / incomplete

## Reviewer 4 — Operational Reality Review

> Owned by Reviewer 4. Reads the initial audit, verified applicability record, and repository evidence record. Main auditor must not backfill this section. If Reviewer 4 cannot write independently, mark `Review incomplete: <reason>`.

- Operational surfaces checked:
- Deployment/config evidence available:
- Provider/account configuration evidence:
- Admin/operator workflow evidence:
- Runtime/scheduled-job evidence:
- Operational evidence unavailable from repo:
- Deployment-dependent findings:
- Findings overturned or confidence-capped:
- Outcome: complete / incomplete

## Reviewer 5 — Enforcement & Consequence Review

> Owned by Reviewer 5. Reads the validated authority, applicability, repository, and operational records. Main auditor must not backfill this section. If Reviewer 5 cannot write independently, mark `Review incomplete: <reason>`.

- Harm analysis:
- Regulator/enforcement route considered:
- Civil/consumer/commercial consequence:
- Likelihood and severity:
- High-risk escalation triggers:
- Evidence dependencies from Reviewers 1-4:
- Consequence confidence caps:
- Outcome: complete / incomplete

## Reviewer 6 — Compliance Evidence Audit

> Owned by Reviewer 6. Reads completed Reviewer 1-5 sections and the main auditor's Stage 1-8 sections. Reviewer 6 performs no new legal research and does not replace missing specialist work. Main auditor must not backfill this section. If Reviewer 6 cannot write independently, mark `Review incomplete: <reason>`.

- Authority proof checked: yes / no / issues
- Applicability proof checked: yes / no / issues
- Repository evidence checked: yes / no / issues
- Operational evidence checked: yes / no / issues
- Consequence reasoning checked: yes / no / issues
- Contradictions found:
- Unsupported assumptions:
- Source weaknesses:
- Confidence inflation:
- Hallucination risks:
- Finalisation readiness: pass / pass with caps / incomplete / reject finalisation
- Outcome: complete / incomplete

## Conflict register

| Conflict ID | Source A | Source B | Contradiction type | Relevant date | Which source has precedence | Evidence | Unresolved question | Required escalation |
|---|---|---|---|---|---|---|---|---|

Contradiction types to search: document-vs-document; policy-vs-terms; privacy-notice-vs-logging; retention-schedule-vs-deletion-jobs; UI-vs-terms; marketing-vs-legal-terms; API-vs-policy; code-vs-configuration; tests-vs-production; current-vs-historical; regulator-guidance-vs-legislation; lower-vs-higher-authority; different-jurisdictional-sources; internal-commitment-vs-statutory-minimum.

Do not average conflicting official sources. Rank authority, check dates and scope, record the conflict, escalate unresolved interpretation. Do not silently choose one source.

## Unknowns

- Unverified sources:
- Unresolved applicability:
- Missing implementation evidence:
- Missing deployment configuration evidence:
- Missing specialist reviewer evidence:
- Evidence-auditor finalisation blockers:
- Database/search limitations for case law:

## Legal-review escalation

| Item | Trigger | Status | Recommended action |
|---|---|---|---|

Apply the high-risk escalation gate. The skill may identify and evidence; it must not make the final professional decision.

## Final synthesis

> Owner: main auditor. Reads all completed reviewer sections, performs rebuttal, records bounded conclusions.

### Final rebuttal

- Reviewer 1 responses and revisions:
- Reviewer 2 responses and revisions:
- Reviewer 3 responses and revisions:
- Reviewer 4 responses and revisions:
- Reviewer 5 responses and revisions:
- Reviewer 6 evidence-audit responses and confidence caps:
- Surviving findings and confidence:

### Matrix

| Finding/Requirement | Authority | Authority type | Jurisdiction | Effective date | Applicability evidence | Repository document | Implementation evidence | Operational evidence | Status | Confidence dimensions | Reviewer challenge | Follow-up |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

Confidence dimensions: Authority / Temporal / Jurisdiction / Applicability / Repository-document / Implementation / Operational-deployment / Enforcement-consequence / Evidence-audit / Overall (capped at weakest decisive). Record the dimension that caps overall confidence.

### Final statuses

Summary count per status (use the bounded vocabulary from `SKILL.md`):

| Status | Count |
|---|---|

## Recommended document changes

| Document | Finding | Proposed change | Owner | Approval required |
|---|---|---|---|---|

Recommendations only. Do not edit compliance/policy documents during this audit. Any edit is a separately approved task.

## Recommended implementation follow-up

| Surface | Finding | Proposed follow-up | Owner | Approval + regression + legal review required |
|---|---|---|---|---|

Recommendations only. Do not edit code/config/tests/migrations during this audit. Any edit is a separately approved task with its own regression and legal-review controls.

## Research limitations

- Sources searched:
- Databases searched (case law):
- Coverage limitations:
- Facts unavailable from the repo:
- Access date:
- Material not located (recorded as unverified):
- Per-domain re-check cadence applied and override reason:

## Compliance drift (if re-audit of a prior audit)

> Required only where this audit re-checks a prior audit. Use `compliance_drift.md` for the workflow.

| Drift ID | Previous research date | Current research date | Previous source/version | Current source/version | Change identified | Legal significance | Repo documents affected | Implementation surfaces affected | Re-audit required |
|---|---|---|---|---|---|---|---|---|---|

Do not claim absence of visible change proves no legal drift. Record `Drift cannot be excluded` where relevant.

## Scope integrity (per audit)

Every final conclusion in this audit is bounded to:

```text
Reviewed scope:
Unreviewed scope:
Documents reviewed:
Implementation surfaces reviewed:
Operational evidence reviewed:
Jurisdictions reviewed:
Dates covered:
Limitations:
```

A conclusion about the whole organisation is only permissible where the reviewed scope actually covers it and all reviewer sections are complete.

## Review-by date

**Next review due:** YYYY-MM-DD
**Trigger for earlier review:** change in law, commencement, guidance, or repo implementation within scope.

---

## Approval gate

```text
This audit produced evidence and findings within the reviewed scope only.
It did not establish that the repository or organisation is legally compliant.
It does not replace review by a qualified lawyer where legal interpretation, material exposure, enforcement risk, litigation risk, or unresolved ambiguity exists.
No application code, tests, configuration, migrations, dependencies, generated files, or production policies were changed by this audit.
Any recommended implementation or policy change is a separately approved task with its own regression and legal-review controls.
```
