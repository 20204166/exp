# Source Record Template

Read this file when creating an entry in the audit artifact's source register. One record per external source. Append completed records to the artifact's source register when used. Do not invent fields; if a field cannot be filled, record `unverified`, `unknown`, or the actual limitation — do not fabricate.

```text
Source ID: SRC-NNN
Title:
Publisher/body:
Source type:
  - primary legislation
  - secondary legislation or statutory instrument
  - retained, assimilated, or otherwise continuing EU-derived law
  - binding court or tribunal decision
  - statutory code of practice
  - regulator rule
  - regulator decision or enforcement notice
  - regulator guidance
  - official government guidance
  - official consultation or draft proposal
  - official standard
  - industry code
  - vendor documentation
  - secondary commentary
  - community material
  - unknown authority
Authority tier: 1 / 2 / 3 / 4 / 5 / 6
URL:
Jurisdiction:
Citation or reference (section/regulation/paragraph/schedule/article):
Relevant section/regulation/paragraph:
Publication date:
Effective date:
Access date:
Research date: YYYY-MM-DD
Version/status: current / superseded / draft / archived / repealed / amended / prospective / temporary
Current/superseded/draft/archived:
Temporal applicability:
Outstanding-change check:
Superseded-material check:
Commencement check (if legislation):
Quoted or closely paraphrased proposition:
Exact words verified: yes / no
Proposition type: exact verified quotation / close paraphrase / auditor interpretation
Auditor interpretation (if proposition type is auditor interpretation; record sources relied on):
Review-by date (where appropriate; see compliance_drift.md default cadence):
Applicability conditions:
Known amendments or outstanding changes:
Conflicting authority:
Research limitations:
```

## Rules

- Classify the source using exactly one value from the `Source type` list. Do not collapse categories into "official source".
- Keep quotations short and exact. Do not fabricate quotation marks around paraphrases — where the text is a paraphrase, mark `Exact words verified: no` and describe it as a close paraphrase.
- Record the access date and research date. Authority can change; a conclusion is only as current as its access date.
- For legislation, do not assume that enactment or Royal Assent means commencement. Fill the `Commencement check` from the commencement provision/order; if it cannot be verified, record `unverified`.
- For guidance, record whether it is current, superseded, draft, or archived, and the effective/revision/withdrawal dates. Where a current page refers to superseded guidance, use official archives and record that the material is archived.
- For case-law sources (use `binding court or tribunal decision`), additionally record:
  ```text
  Court:
  Neutral citation:
  Judgment date:
  Precedential relevance: binding / persuasive / distinguishable / overturned / appealed / other (specify)
  Appeal/overruling status where verified: affirmed / reversed / overruled / under appeal / not verified
  Relevance to the exact legal question:
  Factual distinctions (how the case's facts differ from the audited facts, where material):
  Database searched:
  Database coverage limitations:
  Qualified legal research needed: yes / no / unknown
  ```
  The absence of a judgment from one database does not prove no relevant case exists. Record `No result found` with limitations rather than treating it as proof of the negative. A case factually distinguishable on a material point is weaker authority for the exact question than its bare precedential label suggests — record the distinction.
- Where a source could not be located and verified, record `unknown authority`, `unverified`, and the steps taken. Do not assert the proposition from memory or from a search-result snippet.
- Record conflicting authority explicitly. Do not average conflicting official sources; rank authority, check dates and scope, and escalate unresolved interpretation.