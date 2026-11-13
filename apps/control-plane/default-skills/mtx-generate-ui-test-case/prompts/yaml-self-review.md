# Generation/repair audit

Use one temporary audit file for the exact reviewed design and serialized candidate. This is generation evidence, not a new caller artifact. Read-only advisory review does not run this workflow.

Set task_design_path, task_candidate_path and task_audit_path to the actual files in the same shell invocation that uses them. From the skill directory:

```bash
python3 scripts/coverage_workbench.py init --design "$task_design_path" --candidate "$task_candidate_path" --audit "$task_audit_path"
python3 scripts/coverage_workbench.py packet --design "$task_design_path" --candidate "$task_candidate_path" --audit "$task_audit_path" --case-id SUPPLIED_CASE_ID
```

Read each retained case packet. Fill only the reasoning required by [evidence-workbench.md](../references/evidence-workbench.md): basic static targets use one claim and real field references; compound, dynamic, collection, observation and fillable-gap targets use detailed clauses and counterexamples. Keep the original source and full accepted scope.

Bind and inspect current fields after reasoning about each case:

```bash
python3 scripts/coverage_workbench.py bind --design "$task_design_path" --candidate "$task_candidate_path" --audit "$task_audit_path" --case-id SUPPLIED_CASE_ID
```

After all cases, run check to inspect verdict counts, then export using the generation prompt. Check reports evidence completeness even when a precise unresolved/design dependency remains; successful export requires none. Resolve candidate defects; send true design dependencies through the failure branch, not through fabricated coverage or missingFields.

```bash
python3 scripts/coverage_workbench.py check --design "$task_design_path" --candidate "$task_candidate_path" --audit "$task_audit_path"
```

After edits run refresh, re-audit the reset cases, then bind again. A changed design needs a new audit. Export derives the legacy account and performs role/coverage checks automatically; no second account or manual source hash is required. Passing scripts establishes structure and evidence freshness, not semantic truth or live UI correctness.
