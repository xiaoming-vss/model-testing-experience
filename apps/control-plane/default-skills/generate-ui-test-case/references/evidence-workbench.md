# Case-local semantic audit

Use this after serializing a candidate, and independently in review mode. The old coverage account checks reference completeness; this audit makes the semantic reasoning inspectable against current fields. It is internal evidence, never a YAML field or a user prerequisite.

Initialize a fresh audit with the unchanged design and the exact current candidate:

```bash
python3 scripts/coverage_workbench.py init --design design.json --candidate cases.yaml --audit audit.json
python3 scripts/coverage_workbench.py packet --design design.json --candidate cases.yaml --audit audit.json --case-id SUPPLIED_CASE_ID
```

Process one case packet at a time. It contains that complete reviewed case, its current candidate and every included target. Leave source fields intact. For each target choose `supported`, `fillable_gap`, `design_dependency`, or `unresolved`. The last two need a precise `reason`; they do not need fabricated step references. A gap is acceptable only when filling the declared missingFields actually implements the target.

For supported/gap targets, split the original composite requirement into clauses and populate `clauses`. Each clause records `claim`, `object`, `valueSource`, `scope`, `timing`, and `refs`. Expectations and `observe` actions also need `counterexample` and `rejection`: describe a minimal state violating this clause and the actual candidate condition that rejects it. Challenge both directions: a conforming state must not fail due to an invented extra condition. A count condition cannot reject an identity substitution; page-local evidence cannot reject a change on an unobserved page. An observation is still a claim about a particular object and value channel. When the target explicitly requests actual values to be read or recorded, follow environment-variables.md’s “Recording an observed value”: cite the real result/extraction carrying every requested value, not only a boolean predicate or the step name. Use semantic-review.md for scope and capability decisions.

Use a concrete counterexample state: name the changed object/value and the required outcome. “Violates the target” plus a copied goal is not a state. In `rejection`, identify the actual candidate condition or extraction that distinguishes that state. A source default describes current product behavior; it does not prove the candidate observes that value or rejects a different live value.

A field reference is `{"orderNo": 3, "field": "locatorValue"}`. Cite real executable fields, including producer saveTo and downstream consumer fields where identity or time matters. Cite missingFields itself for a fillable gap. Step names and free-form claims do not count as field evidence. One assertion can cover multiple clauses; share references without inventing duplicate assertions. One supplied target may need several clauses. Decide the partition from this target's full value, sourceQuote and actions, not another case's similarly named target.

Example clause for a two-record count target (not an exact-ID target):

```json
{"claim":"Exactly two result rows","object":"result table body rows","valueSource":"design literal 2","scope":"complete prepared result","timing":"after the query response","refs":[{"orderNo":3,"field":"locatorValue"}],"counterexample":"Only one result row","rejection":"count(tbody/tr)=2 is false for that result"}
```

Bind the case after reasoning about its fields. The script copies exact field values and step hashes; do not type those snapshots yourself:

```bash
python3 scripts/coverage_workbench.py bind --design design.json --candidate cases.yaml --audit audit.json --case-id SUPPLIED_CASE_ID
```

Then inspect the bound case packet, resolve mismatches or mark them honestly, and move to the next case. Do not fill all targets in bulk with a common completion statement. In review mode, an unresolved target becomes an issue only after the evidence-before-rejection checks; uncertainty alone is not a defect. Test proposed repairs against the same clause and execution control flow.

After all retained cases:

```bash
python3 scripts/coverage_workbench.py check --design design.json --candidate cases.yaml --audit audit.json
```

This checks completeness, unchanged source, actual fields and snapshot freshness. It does **not** prove a claim or counterexample true, prove clause partition completeness, or certify DOM behavior. Read the verdict counts and unresolved targets. A completed audit with unresolved/design-dependency targets is not semantic success. Review reports the concrete supported findings in the existing issues contract. Generation resolves them or leaves the exact dependency visible rather than weakening the design.

After modifying candidate YAML, run `refresh` with the same arguments. It resets all judgments for changed cases and preserves unchanged cases. Re-audit reset cases, bind their current evidence, and check again. A changed design needs a new audit. Re-run normal YAML and coverage checks as well; none replaces semantic reasoning.
