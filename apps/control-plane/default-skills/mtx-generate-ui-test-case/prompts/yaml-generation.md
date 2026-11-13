# Generate platform UI YAML

The accepted design defines the test oracle. Source defines how to address the UI; it does not authorize changing an expected empty filter to the product's default value, replacing full-list correspondence with a count/sample, or testing a different business object.

Read [platform-format.md](../references/platform-format.md) for executable fields and [handoff.md](../references/handoff.md) for stage inputs and fillable gaps. For environment values, runtime IDs, baselines or related CRUD cases, read [environment-variables.md](../references/environment-variables.md).

For custom controls or computed table columns, follow the renderer-evidence and column-mapping procedure in [platform-format.md](../references/platform-format.md) before emitting locators. When dependency source is absent, use the lockfile-verified `scripts/read_npm_source.py` reader described there before declaring a renderer gap.

For count changes, exact collections, uniqueness or fixed-page-count targets, read [predicate-strategies.md](../references/predicate-strategies.md) before declaring an execution capability gap. Apply only source-backed strategies that preserve the complete accepted scope.

For included read/record/capture actions, use [environment-variables.md](../references/environment-variables.md#recording-an-observed-value) to verify that execution records each requested actual value at the required time.

For initial or current input/textarea values, read [live-values.md](../references/live-values.md) in generation, repair and review. Complete each value expectation with a timely live-value capture and a comparison; recording alone does not establish emptiness or equality.

For before/after record states, read [state-transitions.md](../references/state-transitions.md). Use its finite identity-bound assertion builder when applicable; do not pair records by row position or substitute current product labels for the reviewed transition relation.

## Repair an existing candidate

When the user requests revision or the caller requests repair of a deterministic contract error, start from that exact candidate as structured data; do not regenerate the module from memory or rebuild every case. Read semantic-review.md, verify each finding against the unchanged design, and identify the affected cases and step fields. Parse the supplied YAML into a temporary object, patch only justified changes, then serialize the whole module. Preserve unrelated steps, known values, missingFields and saveTo dependencies. Repair a shared defect at all actual occurrences, but do not use that as a reason to rewrite unaffected cases. If the candidate was provided as text, save that exact text first; reuse a local temporary file only after verifying it is identical to the supplied candidate.

Refresh the single audit against the patched candidate, updating affected target field references. Compare before/after case objects: every changed case must have a concrete accepted-target defect or a necessary dependency repair. An adverse current product behavior alone is not a reason to rewrite a faithful expectation. Re-audit changed cases and use the checked exporter, then return the entire validated YAML unchanged. For malformed YAML, fix the serialization defect first while preserving business content; avoid wholesale re-authoring as a syntax repair.

## Generation and repair workflow

1. Read the accepted design, original cases and [execution profile](../references/execution-profile.md). Implement one retained case at a time; preserve original names/order, every included target, identity, timing and full scope. Missing locators or initial values use accurate step-level missingFields; unsupported included targets follow the failure branch in SKILL.md. Do not alter the accepted design or silently reduce its scope.
2. Keep the candidate as structured data in a temporary file. Carry genuinely required setup into the draft, honor declared authentication/session context, and use earlier saveTo producers for runtime values. Ordinary source-backed initial bindings may be declared with `--external-variable`; no invented IDs or future values as pre-run fixtures.
3. Execute [the single-audit workflow](yaml-self-review.md) against the exact candidate. The audit is the authoritative target-to-field record. Scripts bind field snapshots and derive the compatibility coverage account; do not maintain a second model-written account. Reuse one effective assertion for multiple targets where justified.
4. Export after all included targets are supported or faithfully fillable:

   ```bash
   python3 scripts/export_ui_case.py --candidate "$task_candidate_path" --design "$task_design_path" --audit "$task_audit_path" --output "$task_export_path"
   ```

   Use separate output and input paths. Pass `--external-variable NAME` for evidenced initial bindings and `--execution-profile PATH` for a caller profile. The exporter checks candidate structure, variable flow, current evidence, derived action/assertion coverage and feature restrictions before replacing output. It refuses unresolved/design-dependency targets and preserves an earlier output on failure. The optional legacy `--account` adds a consistency check; it is no longer required.
5. Read and return the exported YAML unchanged, without fences or receipts. Default output is readable block YAML with quoted strings and independent mappings. `--compact` opts into the previous flow/anchor form only when requested; both forms round-trip the same data. To change content, edit the candidate, refresh/re-audit affected cases and export again. Do not rewrite after validation.

Cases retain name, enabled, orderNo and stepsJson; steps retain platform fields, saveTo and optional missingFields. Do not add audit/profile fields or new variable protocols. Number cases from 1 in this module and steps from 1 in each case. Omit only coverage=excluded cases; only a wholly excluded selection yields [].

A nonzero exporter result is not successful generation. Genuine design dependencies return the failure explanation specified in SKILL.md through the caller's failure channel; they are not format defects to repair by weakening assertions. Read-only review is advisory and runs no generation/export audit. Human approval, import completeness and actual execution are separate checks.
