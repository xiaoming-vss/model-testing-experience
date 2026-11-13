# Compare state changes for the same records

Read this for before/after state comparisons. Refresh can change row order. Capturing `tr[1]` before a refresh and comparing it to `tr[1]` afterward can reject a valid transition or hide another record's regression. Bind both observations to the same independently known record ID. A larger list of allowed state labels does not fix an identity mismatch.

For a finite, known identity set, `scripts/build_state_assertions.py` constructs existing `assert_visible`/`saveTo` steps and XPath predicates. Supply the reviewed transition relation exactly; do not replace a required label with the current product's label or add unsupported successors. Explicitly include unchanged states in the relation when staying in that state is allowed. `requireProgress: true` requires at least one changed state, in addition to every pair being allowed by that relation.

Example configuration (illustrative paths and bindings, not production locators or fixture values):

```json
{
  "anchorXPath": "//div[@id='detail']",
  "rowXPath": "//div[@id='detail']//tbody/tr",
  "identityColumn": 2,
  "stateColumn": 5,
  "scope": "all",
  "requireProgress": true,
  "records": [
    {"identity": {"variable": "preparedIdA"}, "beforeVariable": "stateBeforeA"},
    {"identity": {"variable": "preparedIdB"}, "beforeVariable": "stateBeforeB"}
  ],
  "transitions": {
    "待转换": ["待转换", "转换中", "转换成功", "转换失败"],
    "转换中": ["转换中", "转换成功", "转换失败"],
    "转换成功": ["转换成功"],
    "转换失败": ["转换失败"]
  }
}
```

Derive the row set, identity/state columns and visible comparison anchor from the supplied source and actual view. Use an identity `variable` only if its binding is supplied or produced earlier; alternatively use `{"literal":"actual independently known ID"}`. Do not invent IDs or executable bindings. If IDs are unknown, retain the real missingFields and describe the identity-bound completion rule instead of pretending that sample bindings are available.

`scope: all` additionally requires the supplied DOM row set to contain exactly the listed identities. `scope: selected` checks only the listed identities, allowing other rows. Choose from the reviewed target, not convenience. Neither mode discovers unknown IDs, traverses pages, proves a backend collection complete, or expands a sampled scope. Preserve any separately required total or pagination proof.

```bash
python3 scripts/build_state_assertions.py state-config.json --output state-plan.json
```

The output is an internal plan with `beforeSteps` and `afterSteps`, not an importable case. Place the former at the design's initial observation point and the latter after its actual update/refresh observation point. Preserve the original intervening business actions and renumber the final case. Insert the generated locator and saveTo fields unchanged into the structured candidate; change the configuration and rerun the builder when their inputs need adjustment. The builder already keeps its state comparisons inside the selected-row predicates to avoid repeated absolute paths, and the exporter handles serialization size. A shorter blacklist is not equivalent to the complete permitted transition relation. Each capture and comparison rejects missing/duplicate identities; runtime ID bindings must also be nonempty and distinct. Capture variables may not overwrite identity or scope bindings.

No polling or conditional loop is generated. A locator timeout does not refresh data, and a failing intermediate assertion cannot simulate retry-until-success. Keep genuine timing/control-flow dependencies visible. Refresh and re-audit affected cases after inserting the plan; coverage mapping is derived automatically, then use the normal checked exporter.

Challenge the result with a valid progression under reordered rows and a regression hidden by reordered rows. Both observations must still refer to the same IDs. The helper was exercised with the existing StepExecutor on isolated DOM for these cases, missing/duplicate/extra records, quoted IDs and variable-bound IDs; this is not evidence of live product execution.
