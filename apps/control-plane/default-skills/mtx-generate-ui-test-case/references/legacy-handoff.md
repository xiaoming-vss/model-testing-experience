# Internal handoff and planning

This contract is internal. The platform still receives the existing YAML list
or existing blocked/clarification string; no extra field enters a YAML case.

## Bundle

Use a supplied JSON bundle, or assemble one from the given blocks without
changing their meaning:

- `scenario`: selected stage-two scenario, including original precondition
  refs/dataPlan, actionBindings, observationBindings and fixed variables.
- `surface`: stage-one inventory with unchanged `runtimeEvidence` registry.
- `caseFrameworks`: original frames for all sourceFunctionCaseIds, including
  coreExpectationIds and sourceQuote/sourceStepNos for every expectation.
- `functionalCases`: original functional cases; source text remains authoritative.
  Keep exclusions/bookkeeping available for review.
- `context`: targetBaseUrl, scope, supplied testData/login, and authentication.
  authentication.mode is `suite_setup` only when shared login is explicitly
  declared, or `inline` with the input bindings below.
- `sourceRoot`: actual source root when available. Read routes, components and
  locale implementations as needed; keep them unchanged.
- Optional `capabilities.keywords`: caller-supplied subset of platform keywords.
  Keyword availability is not proof of a new assertion operator.

Inline authentication specifies `loginPageId`, `fields` (controlId/valueRef for
each supplied credential), `submitControlId`, and stable confirmed
`postLoginControlId`. ValueRefs are JSON pointers in the bundle. Emit open,
inputs, submission and post-login polling before business actions.
For suite_setup, declare loginPageId and preparedPreconditions references when
the shared login case supplies original ui_preparable authentication entries.
Only controls belonging to that login page may be delegated this way; shared
login does not satisfy unrelated object counts, states or role relationships.

## Completion

An optional `repair.json` contains `evidenceNotes` and any of `surface`,
`scenario`, `caseFrameworks`, `observationSchedule`. These are proposed effective
values, not replacements for original files. Keep source case text, core IDs,
scenario intent/observations, variables, precondition plans and raw runtime
evidence unchanged. Retain existing confirmed locators and element identity.
A newly confirmed locator must cite an existing raw runtime entry whose exact
type/value and count 1 agree. New source-only locators remain unconfirmed;
request runtime evidence rather than fabricate a count.

Restore bindings/readiness only after the repaired handoff proves the complete
core. Required-observation/core gaps remain blockers; supplementary expectations
stay in the frame. Review field semantics and object association against raw
records/source. The helper cannot prove natural-language equivalence.

Keep `valueRefs` as surface JSON pointers when binding supplied scalar values.
For a target with `sampleValueRef`, the helper also checks that immutable raw
record value. A reference is provenance for a value, not proof that the record
satisfies additional business prerequisites.

`observationSchedule` maps each one-based observation index (JSON string key) to
`afterActionIndex`, optional `beforeActionIndex`, and `sourceStepNos` equal to
its original expectation excerpts' source steps. Zero afterActionIndex is valid
for a true initial-state observation. Derive timing from the original flow,
not convenient YAML placement. Complete an omitted schedule through repair,
retain source-step evidence and review it before lowering.

## Internal plan

A plan has `name` and `steps`, or `cases` containing such objects for independent
complete flows. The compiler owns platform fields and fixed assertion values.

Operation example:

```json
{"actionIndex":1,"keyword":"open","pageId":"orders"}
```

Other operations use `targetId`; `input` also requires a supplied `valueRef`
(such as `/context/testData/name`). `press`, `wait_text`, `assert_visible` use
operationValue. Optional stepName is display text only. Targets belong to that
action's controlIds/pageIds/selectedOptions. Select the parent and its proven
option; parent ownership is checked.

Checkpoint example:

```json
{"observationIndex":1,"afterActionIndex":1}
```

The compiler expands **all** its checks with original targets/operators and
resolved fixed values. Add actionIndex only for an `observe` action implemented
by these assertions. Include beforeActionIndex when required by the reviewed
schedule, preserving refresh-before/after observations.

Setup rows use `purpose: login|precondition|navigation_wait` instead of an
actionIndex. They still need proven pageId/targetId and supplied input values.
Precondition setup includes functionCaseId/preconditionId and implements the
declared ui_preparable controls. navigation_wait uses polling assert_visible;
it does not create a new business expectation.

## Internal trace

The compiler saves a separate `ui_case_trace/1.0` object with scenarioId,
executionPrecheckRequired and one row per physical step. Each row records
caseOrderNo, stepOrderNo, kind, and original action or observation/check refs.
No trace metadata enters YAML. Direct YAML authors may supply the same sidecar
and run the validator; it must cover every physical step.

The validator checks fixed YAML fields, target/value/operator fidelity, required
checks, action/option coverage, complete core in each case, prerequisites and
reviewed checkpoint order. Structure checks do not prove fixture existence or
natural-language equivalence. Finish with semantic review.
