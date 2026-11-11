---
name: generate-ui-test-case
description: Complete reviewed UI test designs into the original platform YAML using frontend source and an element inventory. Fill known step fields and identify real data or locator gaps with step-level missingFields.
---

# Generate platform UI YAML

The accepted design defines the test oracle. Source defines how to address the UI; it does not authorize changing an expected empty filter to the product's default value, replacing full-list correspondence with a count/sample, or testing a different business object.

Read [platform-format.md](references/platform-format.md) for executable fields and [handoff.md](references/handoff.md) for stage inputs and fillable gaps. For environment values, runtime IDs, baselines or related CRUD cases, read [environment-variables.md](references/environment-variables.md).

For custom controls or computed table columns, follow the renderer-evidence and column-mapping procedure in [platform-format.md](references/platform-format.md) before emitting locators. When dependency source is absent, use the lockfile-verified `scripts/read_npm_source.py` reader described there before declaring a renderer gap.

For count changes, exact collections, uniqueness or fixed-page-count targets, read [predicate-strategies.md](references/predicate-strategies.md) before declaring an execution capability gap. Apply only source-backed strategies that preserve the complete accepted scope.

For included read/record/capture actions, use [environment-variables.md](references/environment-variables.md#recording-an-observed-value) to verify that execution records each requested actual value at the required time.

For initial or current input/textarea values, read [live-values.md](references/live-values.md) in generation, repair and review. Complete each value expectation with a timely live-value capture and a comparison; recording alone does not establish emptiness or equality.

For before/after record states, read [state-transitions.md](references/state-transitions.md). Use its finite identity-bound assertion builder when applicable; do not pair records by row position or substitute current product labels for the reviewed transition relation.

## Review mode

When the caller supplies `candidateYaml`, perform read-only auxiliary review and return only its JSON report. This mode takes precedence over generation, repair and export instructions. The report supplies evidence for human review; findings do not declare generation failure or authorize rewriting YAML.

Read [semantic-review.md](references/semantic-review.md). Bind every finding to the exact supplied candidate and its current case/step positions. Inspect each retained case against the accepted design, using the original cases and source to verify evidence. Reuse source-backed evidence already in the inputs; inspect additional source only to resolve a concrete suspected mismatch. Account for earlier `saveTo` producers and later variable consumers before reporting a runtime-value issue.

Return supported findings using the caller's existing fields and codes. For an upstream design conflict, identify what requires human design confirmation in `evidence` and `repair`; keep the original expectation. A valid assertion that exposes a product defect is not a candidate defect. Uncertainty or a preferred implementation is not enough to report a mismatch.

Review does not require creating coverage accounts, running the generation/export workflow, or obtaining a passing semantic audit. Keep candidate and inputs unchanged. A request to repair the review JSON only permits correcting report syntax and references, not editing the candidate. An empty issues array means no supported finding, not a guarantee of correctness. If the review cannot be completed, report failure to the caller rather than claiming an empty successful review; the caller retains the validated draft and marks review incomplete.

## Repair an existing candidate

When the user requests revision or the caller requests repair of a deterministic contract error, start from that exact candidate as structured data; do not regenerate the module from memory or rebuild every case. Read semantic-review.md, verify each finding against the unchanged design, and identify the affected cases and step fields. Parse the supplied YAML into a temporary object, patch only justified changes, then serialize the whole module. Preserve unrelated steps, known values, missingFields and saveTo dependencies. Repair a shared defect at all actual occurrences, but do not use that as a reason to rewrite unaffected cases. If the candidate was provided as text, save that exact text first; reuse a local temporary file only after verifying it is identical to the supplied candidate.

Reconstruct the internal coverage account against the patched candidate, updating affected step numbers. Compare before/after case objects: every changed case must have a concrete accepted-target defect or a necessary dependency repair. An adverse current product behavior alone is not a reason to rewrite a faithful expectation. Run both validators, then return the entire validated YAML unchanged. For malformed YAML, fix the serialization defect first while preserving business content; avoid wholesale re-authoring as a syntax repair.

## Shared semantic-audit workflow

Execute this workflow in generation and requested repair after a complete candidate has been serialized. Reading the instructions, printing case summaries or passing the reference-coverage checker does not execute this audit. Use a unique temporary directory for this invocation's candidate, account and audit; never reuse another invocation's files without verifying exact input equality.

Set `task_design_path` to the unchanged supplied design, `task_candidate_path` to the exact saved candidate and `task_audit_path` to a fresh audit file. Set shell variables in the same shell invocation that uses them. Run from the skill directory:

```bash
python3 scripts/coverage_workbench.py init --design "$task_design_path" --candidate "$task_candidate_path" --audit "$task_audit_path"
python3 scripts/coverage_workbench.py packet --design "$task_design_path" --candidate "$task_candidate_path" --audit "$task_audit_path" --case-id SUPPLIED_CASE_ID
```

For each case packet, read the complete target values and candidate fields, including the full locator and missingFields.reason. Split composite targets into clauses and fill the audit as described in [evidence-workbench.md](references/evidence-workbench.md). Record actual field references and concrete counterexamples for expectations and observe actions. Never generate evidence by copying stepName, labeling a target “implemented,” or applying one completion sentence to every target. A broad scan with truncated fields cannot close a long predicate or gap instruction.

After reasoning about this case, bind the exact current fields, inspect the bound packet, and then repeat for the next supplied case:

```bash
python3 scripts/coverage_workbench.py bind --design "$task_design_path" --candidate "$task_candidate_path" --audit "$task_audit_path" --case-id SUPPLIED_CASE_ID
```

After all retained cases:

```bash
python3 scripts/coverage_workbench.py check --design "$task_design_path" --candidate "$task_candidate_path" --audit "$task_audit_path"
sha256sum "$task_candidate_path"
```

Keep the current candidate SHA256, audit counts, check output and unresolved/design-dependency list as local evidence. No pending target or stale field snapshot may be silently treated as completed. A successful check proves completeness and provenance, not semantic correctness; resolve candidate defects and test repair advice against the same counterexamples. Genuine fillable gaps remain acceptable. In review, only supported concrete defects become issues; uncertainty alone is not rejection. In generation/repair, preserve an actual unimplementable dependency explicitly rather than weakening its target.

If generation or repair changes the candidate, run `refresh`, re-audit reset cases, bind and check again. Review must not change the candidate. Keep this evidence local: the final YAML/JSON contract has no audit fields or new caller prerequisites.

## Generation and repair workflow

1. **Initialize coverage before writing cases.** Use the supplied reviewedDesignPath as `task_design_path`, without reconstructing or editing it. Set `task_account_path` to a fresh temporary account file containing every included target:

   ```bash
   python3 scripts/check_design_coverage.py --init --design "$task_design_path" --account "$task_account_path"
   ```

   Use a fresh temporary path for this invocation. Read [coverage-account.md](references/coverage-account.md) for how to complete the empty slots. This working file is internal, not a user deliverable or import prerequisite.

2. **Implement one complete retained case at a time.** Read its original case, reviewed design and prerequisite scope together. Locate the relevant source and inventory evidence, then build its structured steps and fill its account entries before moving to the next case. Read targeted source ranges and reuse verified shared-component evidence; keep full YAML and accounts in local files instead of repeatedly dumping them into the conversation. Implement every included operation and expectation; keep explicit exclusions out. Preserve identity, timing, quantifiers and every clause of composite expectations. A minimum record count does not establish the full collection size. “All IDs correspond” is not satisfied by a count, first row or fixed sample. Preserve a supported expectation even when the current product will fail it.

3. **Represent actual information gaps.** Carry required setup into the self-contained draft; a precondition states what must be prepared, not what the environment has already supplied. Honor explicit shared-login/session context. When a fresh browser and protected route require authentication, retain the concrete setup gap or implement source-backed login with missing credentials, rather than assuming login survives automatically. Use known fields and source-backed pre-run bindings; follow environment-variables.md when mapping prepared data to named inputs. Capture runtime values with supported saveTo producers before their consumers. For unknown fixture data or locators, retain the intended assertion and known fields and declare step-level missingFields. Apply handoff.md's provenance, availability-time and consuming-field checks. A missing record ID is not a missing checkbox; combine the missing ID and known unique row/cell rule in one entry. A real unsupported included target remains a design dependency, not a fabricated executable assertion, manual oracle or timeout value.

4. **Check the account against the actual steps.** Run `python3 scripts/check_variable_flow.py "$task_candidate_path"` before the full audit; see environment-variables.md for source-backed pre-run bindings and genuine gaps. Each included target needs actual step orderNo references and evidence of the operation or oracle those steps implement. Multiple steps may jointly cover a target, and a single effective assertion may cover several targets; no duplicate checks are needed merely for accounting. Check same-count/different-ID counterexamples for full collections and actual page coverage. Keep known expectations intact when fixing a source conflict. Do not map an unrelated count assertion to an ID-list target just to fill a slot.

5. **Audit and export the final module.** Save the structured candidate as JSON or library-generated YAML, then execute the shared semantic-audit workflow above for every retained case. Set `task_export_path` to a separate final output file and run the provided exporter:

   ```bash
   python3 scripts/export_ui_case.py --candidate "$task_candidate_path" --design "$task_design_path" --account "$task_account_path" --audit "$task_audit_path" --output "$task_export_path"
   ```

   Pass `--external-variable NAME` for source-backed pre-run mappings, using the same provenance-backed declarations as the flow check; missing values alone are not rejected. The exporter rejects unresolved named references before replacing the output file.

   The exporter quotes literal strings and uses standard YAML anchors/aliases for repeated long strings and merge mappings for repeated scalar execution attributes, round-trips the exact data, and runs YAML, coverage-account and audit-freshness checks before replacing the output file. This prevents unquoted brackets/colon-space in gap descriptions from breaking YAML. Its receipt is local evidence, not the response. Resolve failures without modifying the accepted design. These checks do not prove semantic truth. Repair a shared error throughout the module, not only the first reported location. If a target cannot be implemented faithfully, keep the precise design dependency visible instead of inventing coverage or weakening the target.

6. **Deliver the exported serialization unchanged.** Read the complete exported file in chunks if necessary, then return that YAML list itself, beginning with `- name:`, without a fence, receipt, envelope or tool-control marker. Keep the exporter's quoted flow objects and anchors, aliases and merge mappings unchanged; return the complete document so every alias has its earlier anchor. Do not manually reconstruct scalars, merge steps, shorten gap instructions or compact the output after export. To change content, edit the input candidate, refresh/re-audit changed cases and export again. Preserve batch.expectedCaseNames exactly and in order; omit only cases with coverage excluded. Case fields remain name, enabled, orderNo and stepsJson; steps use the platform fields, supported saveTo and optional missingFields. Do not add account/trace fields, draftVersion, dataRequirements, dataBindings, designConflicts, sourceRefs, purpose or a new variable protocol. Number cases from 1 in the module and steps from 1 in each case. Only a wholly excluded selection yields `[]`.

On revision or repair, preserve unchanged business content and known values, update the account for changed step numbers, and return all retained cases. Historical currentArtifact metadata does not change the required output format. The Worker applies bounded repair only to deterministic format and contract errors, then checks the complete merge. Independent AI review adds advisory findings without rewriting or rejecting the draft. Human approval and import completeness remain separate gates. Validation without --allow-missing checks import readiness; it does not certify live DOM correctness or product behavior.
