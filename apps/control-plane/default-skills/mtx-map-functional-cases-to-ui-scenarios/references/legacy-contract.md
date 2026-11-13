# Scenario handoff contract

Keep schemaVersion `ui_test_scenarios/1.0`. IDs and source text are durable;
classification is a judgment supported by the bindings below.

## Source accounting

Each case with UI expectations has one frame:

```json
{
  "functionCaseId": "from-input",
  "caseGoal": "the formal case's primary acceptance question",
  "coreExpectationIds": ["E02", "E03"],
  "frameStatus": "blocked",
  "expectedResults": [
    {
      "expectationId": "E02",
      "sourceStepNos": [2],
      "sourceQuote": "an exact contiguous excerpt of the source expected text",
      "text": "an exact contiguous excerpt of the source expected text",
      "disposition": "gap",
      "gapCategory": "missing_data",
      "reason": "the required comparison object is unavailable",
      "scenarioIds": ["S001"]
    }
  ]
}
```

Use one source step per excerpt. Include connecting words in an adjacent excerpt
so the original expected text is accounted for without rewriting. Excerpts may
split a compound expected result; each clause, count and negation stays in an
excerpt. Parenthetical data and examples also remain accounted for. The helper
ignores punctuation/whitespace and a leading step number when checking coverage,
but not business quantities or comparison operators.

Excluded entries have functionCaseId, expectationId (unique within that case),
sourceStepNos, sourceQuote, text, and reason beginning `not_ui_observable:`.
Bookkeeping entries have the same source fields and a reason. All three
collections jointly account for every source expected result. An omitted claim
is a validation failure, not a normal gap. Merely assigning a source step ID
does not establish accounting.

Core IDs resolve to the case's expectations or exclusions. If the primary goal
is outside UI scope, reference its excluded expectation: setup cannot become a
ready core. An entirely non-UI case may omit a frame and uses excluded coverage.

## Scenario fields

Keep scenarioId, title, sourceFunctionCaseIds, requirementScenarioIds,
relatedRuleIds, requirementRefs, uiAssertability (`ui` or `partial`), fieldAliases,
businessGoal, preconditions, dataNeeds, requiredActions, requiredObservations,
expectedResult, pageHint, status, gapCategory and notes.

Add these explicit handoff fields:

- `goalCheck: {incorrectBehavior, detectedByExpectationIds, explanation}`. Describe
  a violation of this case's purpose; the bound observations must detect it.
- `preconditionRefs`: one `{functionCaseId, preconditionId}` for each original
  precondition of each source case. IDs are P01, P02, ... in original order.
- `dataPlan`: one entry for each precondition reference, with status
  `given_fixture`, `ui_preparable`, `bookkeeping`, or `needs_input`; reason;
  evidenceRefs and controlIds arrays. Given fixtures cite taskContext or an
  existing surface control/runtime evidence pointer. UI preparation uses
  confirmed controls and addresses the original condition, including quantities
  and states. History is a fixture, not current-state verification.
- `executionPrecheckRequired`: boolean; true for historical or variable fixtures.
- `actionBindings`: `{actionIndex, controlIds, pageIds, effect}`, one per business
  action, using one-based indices. Navigation can use pageIds; operations bind
  controls. An ID existing in the surface is insufficient if its uniqueness or
  eligibility is unconfirmed.
  Add `operation`: navigate, activate, input, select, observe, wait, or sequence.
  Selecting a value also includes `selectedOptions`: entries with controlId
  (the select), optionControlId, and value. optionControlId references a confirmed
  option in that select's `options` list; a field/container ID cannot stand in for
  an option. Keeping a select empty is an inspection/precondition, not selection.
- Non-ready scenarios retain business intent and source expectation references,
  with `actionBindings: []` and empty observation `checks`. Tentative mappings
  are not executable plans; use the surface again after resolving the blocker.
  The finalizer may qualify an existing raw runtime pointer with
  `/runtimeEvidence` only when it resolves to the same supplied registry entry.
  It never changes the fixture classification or adds evidence.
- `observationBindings`: `{observationIndex, functionCaseId, expectationIds,
  checks, context}`, one per observation. Indices are
  one-based. requiredObservations uses the exact expectation text (or multiple
  quoted excerpts joined by a newline), not a rewritten assertion. Scope the
  target to the intended object. Each `checks` entry is `{targetId, operator,
  expectedText, valueRefs}` and describes one actual assertion. Operators are
  visible, text_eq, text_contains, url_eq and url_contains unless supplied
  capabilities add more. URL checks target page IDs; others target confirmed
  elements. A multi-field observation needs individual checks with each field's
  actual expected value, not the same business sentence compared to every field.
  expectedText is the rendered literal or a declared variable, not the source
  business claim. valueRefs cite scalar JSON pointers in the surface (including
  original runtimeEvidence) when the literal is a fixture value. Exact target
  visibleText/text, quoted source literals and source numeric literals are also
  usable. Parameter values such as `{{recordId}}` must be declared in the optional
  scenario `variables` object with their source/preparation. Bindings are proof
  plans, not YAML steps.
- `conflictEvidence`: entries `{functionCaseId, expectationId, sourceRefs,
  targetIds, expectedQuote, observedFact, kind}` when conflict is claimed. Kind is
  source or runtime. Runtime comparisons use target candidates whose non-null
  context.object identities agree; keep the quoted source expected result.
  A missing identity/relationship cannot prove a runtime contradiction.

Ready observations bind executable expectations. A ready scenario includes all
coreExpectationIds for every source case it claims. Its dataPlan has no needed
input. Supporting UI expectations with gaps remain in the frame, outside ready
observations. To track several independent formal goals, use separate scenarios
with their actual source cases, rather than dropping a defining qualifier.

## Statuses and references

Scenario status: ready, missing_page, missing_data, not_ui_testable, conflict.
Gap category: missing_page, missing_data, not_ui_testable, unassertable_operator,
conflict, requirement_only, case_only; null for ready/executable.

`missing_page` is the legacy category for a missing UI binding: page, control,
observation node or confirmed locator. It does not assert that the product lacks
that page or field; the reason must identify the missing evidence precisely.
Use `missing_data` for unsupported fixtures/preconditions, and
`unassertable_operator` for a known target whose required assertion is unsupported.

Coverage has exactly one record per selected case: functionCaseId, frameStatus,
status, primaryGapCategory, scenarioIds, reason. Frame status is complete,
partial, blocked or excluded. Coverage status is ready, partial, missing_page,
missing_data, not_ui_testable or conflict. A blocked frame cannot have a ready
core; a partial frame must have a valid ready scenario covering its full core.

requirementGaps entries use requirementScenarioId, relatedRuleIds,
status `not_covered`, reason. Requirement, rule and evidence IDs must exist in
the supplied pack. Additional fields are allowed without replacing these.
