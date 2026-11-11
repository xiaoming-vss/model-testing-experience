# Internal design coverage account

Use this while generating or repairing a module. In review mode, reconstruct the target-to-step account from the unchanged candidate to ensure every included target has been inspected; do not edit the candidate. Missing or falsely mapped targets require semantic assessment and a concrete finding, not a fabricated reference to make the checker pass. It makes omissions visible before delivery. The account is a temporary local working file: do not add it to the YAML, ask the user to maintain it, or change the platform import contract. Semantic review still judges the actual YAML independently.

1. Initialize the account using check_design_coverage.py --init with the unchanged reviewedDesignPath. It enumerates actions and expectations whose status is included for each retained case and starts with empty steps/evidence; it makes no coverage claim. Keep caseId and target IDs. Explicit excluded/bookkeeping expectations are outside this account, even when listed in coreExpectationIds.
2. Associate each target with actual candidate step orderNo values. For an expectation, identify the assertion's compared object, expected value, quantifier and page/time scope. A click or saveTo producer alone is not proof of an expected result. Multiple steps can jointly implement a target and one valid assertion can satisfy multiple targets; do not duplicate assertions just for accounting.
3. Write the account in the following format. Replace the example IDs and step numbers with the actual supplied IDs and candidate numbers.

```json
{"cases":[{"caseId":"supplied-case-id","targets":[
  {"id":"supplied-action-id","steps":[1],"evidence":"Clicks the query button in the active filter panel."},
  {"id":"supplied-expectation-id","steps":[2,3],"evidence":"Step 2 compares the fixture count; step 3 requires every fixture ID exactly once in the complete observed result."}
]}]}
```

4. Run `python3 scripts/check_design_coverage.py cases.yaml --design /path/to/reviewed-design.json --account /path/to/coverage.json`, as well as the normal YAML validator. Resolve every missing target and stale step reference after edits. Account evidence describes the actual selector/operationValue/missingFields semantics, not what the step name claims. Copying a step name or dumping its fields does not establish equivalence. For composite expectations, explain which exact expression implements each clause; for page-wide targets, identify every observed page and the evidence that this exhausts the accepted scope. If these cannot be established, record the unresolved dependency honestly rather than claiming the target is covered.
5. Challenge collection mappings with an equal-count result containing a different unchecked ID. If it still passes, the whole-list target is not covered. Challenge product-conflict findings by distinguishing a valid failing assertion from an unsupported executor operation. Use semantic-review.md for those decisions.

The checker verifies completeness, references and basic action/assertion roles. An included interactive operation needs an actual interaction among its mapped steps; a visibility assertion cannot substitute for clicking. Equivalent interaction methods still need semantic review, and an intentional negative action may continue to its later effective assertion. Passing it does not establish semantic coverage, valid runtime DOM, or product correctness. Never attach an unrelated count assertion to an ID-list target just to satisfy it. If an included target has no faithful supported implementation, retain the precise design conflict for the caller's review; do not invent coverage or silently drop the target.
