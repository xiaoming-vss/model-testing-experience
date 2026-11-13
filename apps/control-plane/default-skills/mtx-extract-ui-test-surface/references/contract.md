# UI surface contract

The base schema remains `ui_test_surface/1.0`; [output.schema.json](output.schema.json) defines the checked structure. Additions preserve evidence without changing the existing arrays. Validation requires Python jsonschema.

| Field | Content |
| --- | --- |
| app | framework, entryRoute, loginRoute, authGuard, sourceRoot |
| pages[] | pageId, route, componentFile, title, sourceRef |
| containers[] | containerId, pageId, kind, semanticName, sourceRef, locatorCandidates; rowLocator when addressable |
| controls[] | controlId, pageId, containerId (or empty), semanticName, controlType, role, visibleText, i18nKey, sourceRef, uniqueness, locatorCandidates |
| feedback[] | feedbackId, pageId, kind, text, sourceRef; locatorCandidates/uniqueness when independently addressable |
| interactions[] | interactionId, pageId, controlId, effect, targetId, sourceRef; conditions/context when scoped |
| unknowns[] | topic, reason, sourceRef; affectedIds when known |
| inspectionCoverage[] | area, caseIds, pageIds, componentFiles, status, reason |
| evidenceIssues[] | topic, reason, refs; discrepancies or missing correlation, not inferred product defects |
| runtimeEvidence | supplied original JSON unchanged; omitted when none was supplied |
| observedStates[] | non-message capture states with stateId, pageId, sourceRef and notes; no invented feedback literal |

Inspection status is `inspected`, `unavailable`, or `non_ui`. Inspected entries
name actual files read and pages covered. Empty pages are valid when the selected scope is entirely non_ui, or unavailable with precise unknowns; an empty selection is also valid. No UI page may be invented merely to satisfy validation. Unavailable entries identify missing
input or unresolved routing and also appear in unknowns. Existing local pages
cannot be unavailable merely because extraction stopped early. Each selected
case ID appears in an entry; mixed UI/backend cases retain UI inspection.

Controls include interactive and read-only elements, distinguished by controlType.
Select controls also have `options`: each entry has label, value, controlId (null
when unproven), availability (`declared`, `addressable`, or `unknown`). Addressable
options reference an actual confirmed option control. Unknown option loading or
clickability is recorded separately from the select field's own uniqueness.
Mark captured sample values `sampleOnly: true`, retaining their context.
For dynamic cells/readOnlyText/select displays, a nonempty visibleText also has
sampleValueRef: a scalar JSON pointer into runtimeEvidence whose string value is
exactly that captured text. A caption belongs in label/semanticName instead.
Uniqueness is `confirmed` or `unknown`. Confirmed elements have a proven candidate;
source proposals have `confirmed: false`; this describes evidence, not whether a case is included in stage two. Stage three evaluates locator usability in context.

Each locator candidate contains:

```json
{
  "locatorType": "xpath",
  "locatorValue": "//dialog//button[normalize-space(.)='Save']",
  "reason": "exact scoped rendered label",
  "evidenceType": "source",
  "sourceRef": "src/edit.vue:80",
  "runtimeEvidenceRef": null,
  "confirmed": false,
  "stability": "stable",
  "context": {"object": null, "state": "edit dialog open", "scope": "edit-dialog"}
}
```

Runtime candidates use evidenceType `runtime` and a JSON pointer such as
`/locators/4`. The target has count 1 and the exact locator type/value. Its full
evidence wording remains in the raw registry. Context.object, when known, is a
literal identity such as `recordName=sample-a` supported by that locator entry.
Use null when the identity is absent; retain the narrower scope.

Conditions describe source predicates with source references. A template's
eligibility rule does not prove a captured record's state. Generated-class runtime
locators are allowed only as exact supplied candidates with runtime_only stability.

Interaction targets resolve to page, control, container or feedback IDs. Row
interactions retain object identity. Unresolved targets belong in unknowns.

Compatibility details: rowLocator is null/absent or has locatorType/locatorValue;
row-key expressions and descriptions belong in rowKey. Feedback text is a known
nonempty rendered message; captures such as empty/loading option lists belong in
observedStates. Interaction effect is a short tag/phrase (at most 60 characters);
put complete explanations in description/conditions. The finalizer moves existing
descriptive metadata without inventing selectors, messages or readiness. Long effect text is appended to an existing description without discarding it. A descriptive rowLocator conflicting with an existing rowKey is reported for explicit reconciliation; the artifact is not overwritten on failure.
