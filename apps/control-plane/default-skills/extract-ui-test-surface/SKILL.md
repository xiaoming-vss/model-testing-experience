---
name: extract-ui-test-surface
description: Extract pages, controls, observable fields, scoped locator evidence and missing evidence from frontend source for functional-case-driven UI testing. Use before mapping functional cases to UI scenarios; this stage records UI facts rather than test expectations.
---

# Extract UI Test Surface

Read selected functional cases to determine the inspection scope. Read frontend source to establish what the interface contains. Preserve the identity and conditions of every piece of evidence so the next stage can use it without joining unrelated objects or snapshots.

## Stage boundary

Capture elements and controls, including read-only assertion targets and source-derived locator candidates. When the selected flow creates records and later reuses them, include the result identity fields and input/value/attribute observation targets needed for extraction, with their page/container lifetime and source-backed row identity. A sample ID is evidence of a field, not a fixture value for the next run. Missing runtime confirmation is an inventory fact, not a reason to omit an element or stop extraction. Do not decide test inclusion, executor capability or scenario readiness. Stage two designs cases without locator binding; stage three uses this inventory and source to complete YAML.

## Inputs and output

Inputs are `sourceRoot`, selected formal cases or their scope, optional runtime DOM evidence, and optional task context. Runtime evidence describes its capture time, not the current environment.

Return one JSON object with `schemaVersion: "ui_test_surface/1.0"` and the existing `app`, `pages`, `containers`, `controls`, `feedback`, `interactions`, `unknowns` arrays. Read [references/contract.md](references/contract.md) for their fields and the additional inspection and provenance fields. Preserve this contract for downstream consumers. This stage does not generate scenarios or executable YAML.

When the caller supplies `outputPath`, write that exact JSON artifact there and return only `{"artifactPath":"the supplied absolute path","status":"written"}`. The caller validates the file contents. Otherwise return the artifact JSON directly. Use the caller's original input files for validation; fabricated substitute cases or runtime evidence do not validate the artifact.

## Inspect the complete selected scope

1. Follow routes and entry points from the cases' preconditions, actions **and expected results**. Include verification destinations and shared drawers, menus, tables and forms. Include login and a stable post-login element when authentication exists.
2. Read each relevant page and the child components implementing the selected flows. Follow list-to-detail navigation to its destination component, even across modules. Resolve the active locale.
3. Record each relevant page in `inspectionCoverage`: route, component files actually read, related case IDs, and inspection status. Finish accessible pages before handing off. Unknowns describe unavailable source or unresolved routing, not a substitute for reading a known local component.
4. Extract exact rendered labels, inputs, choices, read-only values, table columns/rows, feedback and conditional actions. Distinguish a declared option value from an addressable rendered option. Record eligibility conditions: state, permissions, active tab and dialog.
5. Follow interactions to their target page/container. Keep object identity for row actions. Finish when every selected flow has inspected source or a specific external/unavailable-source explanation.

Close the scope against UI needs in the selected cases: include paging, jump-to-page, option selection and verification destinations when mentioned. Give each needed control either an inventory entry or an explicit locator/evidence unknown. A table's pageSize alone does not describe its paging controls. Cases supply scope only: comparing formal expected outcomes with implementation belongs to stage two. Keep known source facts (columns, labels, eligibility) separate from unresolved locator facts. `evidenceIssues` compares source/runtime evidence, not formal test expectations.

## Preserve evidence rather than summarizing its meaning

Every locator candidate identifies its proof:

- `evidenceType: "source"`: a source reference and a reason for uniqueness **in its stated scope**. A library component tag alone does not prove DOM shape.
- `evidenceType: "runtime"`: `runtimeEvidenceRef`, the exact JSON pointer to the supplied locator entry, and its exact locator type/value. Keep `context.object` and the original evidence wording. Use null when object identity was not supplied; missing identity does not authorize joining observations.

`count: 1` proves uniqueness in that capture's page, container, record and state. It does not associate a menu from one record with another record, preserve first-row identity after filtering, or make a historical ID reusable. Link a menu to a row only when the evidence identifies the row or source proves the generic relation with its eligibility condition. Preserve the supplied raw evidence in `runtimeEvidence`; the validator can attach it unchanged.

Keep source behavior and runtime observations separate when they differ. Record the discrepancy and both references in `evidenceIssues`. Missing snapshot/object correlation is an evidence gap, not a product conflict. When the supplied evidence contains inconsistent summaries, preserve the specific observations and flag the inconsistency rather than silently choosing a story.

For each select control, record `options`: declared values/labels, and `controlId` only when an individual rendered option has proven locating evidence. An empty or API-loaded option list stays explicit. Confirming a selector or an options container does not confirm its individual options. Preserve an explicitly identified captured record in context.object instead of hiding its identity in a note.

## Locator decisions

Prefer test IDs, accessible names, associated labels/placeholders, stable attributes, then semantic scoped XPath. Exact text comes from rendered source or the resolved locale. A role name must be unique under the runner's substring-name matching. Scope repeated controls to a specific dialog, form, or business row.

For source-derived candidates, avoid generated library classes, positional CSS chains and guessed rendered internals. Leave uniqueness unknown when DOM shape or scope cannot be proven.

For supplied runtime candidates, copy the locator unchanged, including a library class when that is the actual supplied evidence. Label these `stability: "runtime_only"`; label stable semantic candidates `"stable"`. Uniqueness and stability are separate properties: a candidate can be confirmed in its capture while still needing execution-time rechecking. A manufactured semantic replacement cannot be called runtime proof.

For tables, describe row keys, columns and concrete row scope. A sampled cell is not an aggregate or a universal-row assertion. An input's value is not its DOM textContent; record the needed read mechanism instead of assuming executor support.

Separate a field's label from the target element's text. Put field captions in label/semanticName. For dynamic value cells and select displays, visibleText stays empty unless an exact captured value is provided; then mark sampleOnly and cite a scalar sampleValueRef in the original runtime evidence. For example, a locator for a numeric value does not have its label as visibleText. Icon-only buttons likewise keep tooltip/accessible names separate from DOM text.

For compound cell text, record textAssembly with its child parts, actual literal separator (empty string when source concatenates child text without one), and sourceRef. A display observation can contain layout whitespace that is absent from DOM textContent. Retain source expressions as expressions, not made-up captured values.

## Handoff check

When a filesystem is available, validate the artifact with the bundled helper:

```bash
python3 scripts/validate_surface.py surface.json --source-root SOURCE_ROOT --cases cases.json --runtime-evidence runtime.json --finalize
```

`--finalize` attaches supplied raw evidence and normalizes metadata into its proper fields: descriptive row keys into rowKey, non-message captures into observedStates, and long interaction prose into description. It preserves those facts, IDs and references and does not promote candidates or change readiness. Omit runtime options when none was supplied. The script checks references/provenance, not live browser behavior.

Verify that local verification destinations have been read, references resolve, runtime locators retain exact provenance, and unresolved facts remain explicit. Keep credentials and tokens out of the output.
