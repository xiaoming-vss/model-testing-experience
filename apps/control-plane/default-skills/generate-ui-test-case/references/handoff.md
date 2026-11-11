# Editable YAML handoff

Use the original platform case and step fields. Steps support saveTo extraction and optional missingFields; no separate data-management or design-conflict schema is generated.

Inputs: stage-two ui_test_scenarios/2.0 design, original cases, stage-one surface, sourceRoot and context (targetBaseUrl, login/authentication, testData). A design has no locator bindings and is not execution-ready; stage three completes implementation details without changing the oracle.

## Module scope and delivery

Each call receives one complete module of original functional cases and reviewed stage-two designs. Stage-one elements and sourceRoot remain available for implementation details. Return exactly the retained designs in `batch.expectedCaseNames` order with unchanged names; only `coverage: excluded` cases are omitted. Return a YAML list directly, including a one-case list or `[]` for a wholly excluded module. Case orderNo starts at 1 within each module; step numbering restarts for each case. The Worker checks each module, requests bounded repair for deterministic format or contract errors, merges successful lists and checks the complete selection. AI semantic findings accompany the draft for human review; they do not trigger automatic regeneration or make generation fail. Preserve the original case content and the accepted design when repairing.

## missingFields

Only steps gain an optional `missingFields` array. Absent or [] means no declared unresolved content. Each entry has exactly:

- `fields`: distinct names among keyword, locatorType, locatorValue, operationValue, comparator. Listed fields must be present with null values. Use [] only for a real unresolved preparation condition that has no executable field. A missing value already identified in another entry does not need a duplicate preparation reminder. Unsupported assertions are not preparation conditions.
- `operation`: the intended action/assertion, in user language.
- `target`: the intended element, business object or prerequisite.
- `value`: known business input/expected value (string, number, boolean or null when unknown). This is user guidance, not an executable field. A click on a format option can have missingFields.value = LeRobot even though click needs no operationValue.
- `reason`: exactly what is missing and what the user needs to provide or prepare.

Example:

```yaml
- name: 选择转换格式后确认
  enabled: true
  stepsJson:
    - orderNo: 1
      stepName: 选择 LeRobot 格式
      keyword: click
      locatorType: null
      locatorValue: null
      missingFields:
        - fields: [locatorType, locatorValue]
          operation: 选择转换格式
          target: 转换格式下拉框中的 LeRobot 选项
          value: LeRobot
          reason: 源码声明了选项值，但尚未获得可定位的渲染节点；请补充定位类型和定位表达式
      continueOnFailure: false
      enabled: true
    - orderNo: 2
      stepName: 核对选中格式
      keyword: assert_text
      locatorType: null
      locatorValue: null
      operationValue: LeRobot
      comparator: eq
      missingFields:
        - fields: [locatorType, locatorValue]
          operation: 断言选中格式
          target: 转换格式当前选中项的文本节点
          value: LeRobot
          reason: 请提供选中项文本节点的定位，不能用 input 的 textContent 读取输入值
      continueOnFailure: false
      enabled: true
  orderNo: 1
```

Fill fields and remove the corresponding entry together. Merely clearing missingFields leaves nulls invalid. Filling a value while leaving its missing entry is also inconsistent. User-supplied locators are accepted by completeness validation without requiring another AI evidence review. Known unsupported operations are excluded in stage two, not fabricated as executor keywords. If a design mistakenly includes one, return it for design correction; never label it executable.

A draft may be saved and edited as YAML. Formal platform import rejects unresolved entries with the case/step location. The run boundary also rejects them, including disabled steps, so disabling a missing assertion cannot turn a partial case into a passing test. Completed files preserve the original platform format; empty missingFields is accepted and stripped during import.

No user-maintained completion checklist or trace is required; the temporary generation coverage account stays internal. Optional experiment diagnostics are not user inputs. Source-backed relationships, accepted fixture assumptions and unresolved prerequisites must be meaningful; never output one generic missing locator for an entire compound business step instead of expanding known operations.

## Self-contained editing

Write concrete prerequisite descriptions in missingFields, including required record counts/states/identity. Do not refer users to another file to discover what must be prepared. A supplied shared-login declaration is accepted context, not automatically a missing input. Keep historical record rechecks explicit where needed. Use the checked exporter described in SKILL.md for the complete YAML response. Its anchors and merge mappings compress repeated serialization; parsing restores the original case and step fields. To revise one case, parse the full document, edit that case object, refresh its evidence and export again; changing a shared anchor directly would change its other references.

## Distinguish the cause of missing content

When a target row ID is unknown but the row/checkbox structure is known, keep locatorType, set the incomplete locatorValue to null, and describe the required ID plus the source-backed locator rule in one missingFields entry. Do not label this as an unknown checkbox or add another fields: [] entry asking for the same record. Unknown assertion values and true independent DOM locators remain accurately marked at their actual steps. When an environment binding or prior saveTo producer exists, use its variable reference instead of a null field; see environment-variables.md.

A missing field identifies the expression to complete, not the category of information that is missing. A null `locatorValue` can legitimately await independent expected IDs that will become XPath literals or source-backed variable references in its predicate; it need not already contain placeholders. Keep an assertion's known timeout intact. Judge fillability by whether replacing the declared field can implement the intended comparison using the existing observations and supported operations.

For a later collection assertion, values successfully captured before navigation remain available as scalars even when their original rows leave the DOM. Its predicate may combine those scalars with currently visible cells. State exactly which prior values and current nodes participate, the independent expected collection, multiplicity and total checks. An earlier broken capture locator is a separate producer defect; filling the later field does not repair it, but the producer defect does not prove that the later expression is inexpressible. A vague completion recipe needs a concrete clarification of the missing condition, not a claim of unsupported capability when a faithful expression exists. Missing observations, unvisited pages and absent producers remain real gaps.

## Fillability check before adding each marker

For each gap, establish provenance, availability time and consuming field:

- A pre-existing fixture ID, environment URL or intended input can be provided before execution. Follow environment-variables.md for source-backed named inputs whose values are pending; use a null field for a genuinely unresolved mapping. Preserve the known locator strategy, intended action and business value.
- An ID created by an earlier action in this same test, or a baseline observed during this test, is a runtime dependency. First use source-backed saveTo extraction and a later variable reference (see environment-variables.md), or inspect navigation, retained row context or relational selectors that can preserve the original comparison. If the platform cannot express the required comparison, identify the reviewed-design conflict during internal review; it cannot be repaired by asking the user to supply tomorrow's value today. A historical record's pre-existing ID remains a valid fixture gap.
- `assert_visible.operationValue`, `assert_hidden.operationValue` and `sleep.operationValue` are wait durations in milliseconds. Set a concrete wait duration; business counts, names and expected text never belong in their missingFields. Express each business assertion in its own supported step. Setting a known timeout to null only to satisfy null-field validation is not a repair.
- A marker is fillable only if filling the listed fields makes that specific step perform the described operation/assertion. An empty-table selector does not compare a complete baseline list; visibility does not compare two dynamically produced values. Do not remove the marker and leave the intended assertion unimplemented.
- A missing row ID is not a missing checkbox. Scope the locator to the intended table, identity column and unique record. Use version names only with evidence of uniqueness or a composite identity; an OR over arbitrary cells is not sufficient identity evidence.
- If source shows the required control or state is not implemented, preserve a supported assertion of the expected state so execution can reveal the product defect. A known render condition that hides an expected header is not executor incapability. Report a candidate issue only when its expression is wrong, its missing field cannot express the intended assertion, or an included target truly needs unsupported executor behavior; keep the original business expectation unchanged.

Verify reported semantic issues using semantic-review.md before repairing supported findings against the unchanged inputs. Recheck the whole affected case so a local repair does not lose an assertion, change object identity or introduce a duplicate preparation marker. Internal review reports are attached to the generation run for human review and are never added to YAML. Their findings authorize no candidate edits until the user requests revision.

## Source-backed predicate assertions

Assess the meaning of the whole executable step, including selector predicates. With verified DOM structure, an `assert_visible` XPath may select a table only when `count(tbody/tr)=N`, a checkbox only when `@aria-checked='true'`, or a status cell only when its text is A **or** B. These preserve count/state/OR semantics; mere visibility without that predicate does not. Two sequential assertions require both to pass (AND), so they cannot replace an OR expectation. Verify the actual attributes, table scope, paging and virtualization before using these strategies. Never invent a predicate's source evidence.

For a source/requirement discrepancy, keep the original oracle. Report a concrete design/implementation question when no faithful executable expression is available. Matching current source defaults by changing the requirement is not a repair. Review repair suggestions as strictly as candidates: do not remove a clause, narrow an OR, change the compared identity or replace equality by non-emptiness.

## Avoid over-rejecting valid test gaps

The time a test reads a value is not necessarily when that value is created. Existing record IDs or a stable pre-existing list can be supplied as fixtures even if the original preparation text did not enumerate every ID; a bookkeeping read alone does not make them unavailable before execution. Distinguish these from values created or changed by this test and baselines that must be observed at that moment.

A faithful assertion can fail against a defective implementation and still be a valid generated test. Keep its business expectation. Missing source evidence alone does not prove that a backend message or runtime-rendered control cannot exist: mark a genuinely unknown locator, describe the missing DOM evidence and let the user confirm it. Do not invent a known node from an unused translation key. Reject mismatched or unfillable markers and weakened assertions, not tests merely because current implementation violates their expected result.


## Complete a collection assertion without sampling

For an included “all / only / one-to-one” target, keep the whole collection as the comparison object during generation and repair. A supplied minimum record count is not the size of the full collection. Unknown fixture cardinality does not justify generating checks for only the first one, two or three records. Total count plus a sample still permits replacement of every unexamined record.

When the complete expected IDs are available, implement each expected ID's required multiplicity and the total over the required page scope. When only those fixture values are missing, retain the complete-list requirement in the actual assertion's missingFields and describe an exact predicate over the required scope. Full-list multiplicity checks apply to a container exposing the full list, not separately to each partial page. A finite, fully traversed set of pages may instead establish equality through complete-list membership, uniqueness within and across pages, and matching total cardinality. Membership alone is insufficient. Establish a supported way to expose the full scope before choosing that predicate. A marker cannot create pagination steps, iteration or set operations that the executor lacks. If no faithful supported expression exists, identify the precise included-design dependency requiring confirmation; preserve the oracle instead of returning a smaller sample as a completed repair.

A known expected state remains known even if the current product does not satisfy it. For example, when the accepted expectation is an empty filter, preserve an empty-state assertion; the product's nonempty default is not a reason to turn the expected value into null or ask the user to choose a different expectation.


## Preserve validated YAML during delivery

Generate and repair a structured in-memory object, then serialize it with a YAML library. After both validators pass, return the same serialized candidate; manual changes after validation invalidate the check. For prose containing XPath, a literal block avoids YAML interpreting a colon-space inside the prose as a new mapping:

```yaml
reason: |-
  Provide the record ID. Scope the row inside the drawer whose style contains 'width: 900px', then select its version-name cell.
```

A valid script or file is not enough if the final response is manually reconstructed and loses required quotes. Validate the text that will actually be delivered, including all cases and the last step.

When a parser reports an unsafe scalar, repair the serialization class across the entire module, not just the reported line. Inspect all missingFields.reason values and other prose containing colon-space; the next parser error may be the same defect later in the file. Re-run both checks on the full serialized result after the last change.
