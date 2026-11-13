# Single case-local audit

This internal record is required only for generation and requested repair. Read-only review inspects the design and current candidate directly without generating audit artifacts. Commands and lifecycle are defined in [yaml-self-review.md](../prompts/yaml-self-review.md).

The workbench initializes every included action/expectation and copies its source. For each target choose supported, fillable_gap, design_dependency or unresolved. The last two require a precise reason and no invented step references; they can be recorded locally but block successful export. A fillable gap must be implementable by completing its actual missingFields.

## Basic static targets

Set reviewDepth=basic only for one ordinary interaction or simple static text/visibility/URL comparison with no compound scope, runtime identity, time relationship, collection reasoning or missing field. Use one clause with claim and refs; its wording must connect the design goal to the actual candidate field, not copy a step label.

```json
{"verdict":"supported","reviewDepth":"basic","clauses":[{"claim":"The query button is clicked through its source-backed test ID","refs":[{"orderNo":2,"field":"keyword"},{"orderNo":2,"field":"locatorValue"}]}]}
```

The checker rejects basic mode for obvious capture/template/compound-predicate/gap evidence. It cannot infer every business dependency; choose detailed mode whenever the target requires one. Preparation shared by several targets is referenced rather than repeated.

## Detailed targets

Omit reviewDepth or set it to detailed. Split composite goals into their real clauses. Each clause records claim, object, valueSource, scope, timing and refs. Expectations and observe actions additionally record a concrete counterexample and rejection condition. Preserve complete collection identity/multiplicity, observation time and producer/consumer identity; use the corresponding live-values, state-transitions or predicate-strategies reference when applicable.

```json
{"claim":"Exactly two result rows","object":"result tbody","valueSource":"design literal 2","scope":"complete prepared result","timing":"after query","refs":[{"orderNo":3,"field":"locatorValue"}],"counterexample":"Only one result row","rejection":"count(tbody/tr)=2 is false"}
```

Field references contain orderNo and field. Cite executable fields, producer saveTo and consumer fields where needed, or missingFields for a gap. The bind command fills exact values and hashes; do not type snapshots. One valid assertion may support multiple clauses; no duplicate test step is needed for accounting.

For actual-value observations cite the readback/extraction carrying the requested value, not just a boolean visibility predicate. For a collection claim challenge equal-count replacement and duplicates. For a transition retain record identity under row reordering. For initial/later input values challenge a changed live value at the required time. A conforming state must not fail because of an invented extra condition.

## Closure and export

check verifies source equality, field references and current hashes; it reports unresolvedTargets without calling them implemented. Export derives the compatibility account only when all targets are supported or fillable_gap, then checks actual interaction/assertion roles. It rejects design dependencies with DESIGN_CONFIRMATION_REQUIRED and unfinished candidate checks with GENERATION_INCOMPLETE. Do not weaken the design to clear either result.

An edit resets changed cases through refresh; unchanged cases keep their reasoning. These checks do not prove truth of a claim, completeness of semantic clause splitting, DOM behavior or product conformance. Review independently checks supported defects and never modifies the candidate merely to obtain a passing audit.
