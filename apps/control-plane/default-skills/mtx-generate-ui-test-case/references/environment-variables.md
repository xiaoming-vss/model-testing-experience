# Environment variables and producer/consumer flows

The executor supports environment variables in `locatorValue` and `operationValue`, and post-step extraction in `saveTo`. Use these existing fields; no extra YAML protocol is needed. Variables are shared in the selected environment, and writes replace the existing value. Related flows using the same names run sequentially.

## Plan from the requested business flow

Identify initial inputs, values produced by steps, and their consumers before writing YAML. For a requested record lifecycle, establish the record first, capture its identity, query and modify that same record, verify the changes, then delete it after its last consumer. Preserve intervening queries and original acceptance conditions. Never add destructive cleanup to unrelated tests or silently merge, omit or reorder reviewed cases. If the supplied order has a consumer before its producer, report that scheduling prerequisite instead of changing case identity or inventing an ID.

Only initial inputs need user-provided environment values. A name supplied as `{{projectName}}` remains that reference throughout the flow. An ID produced by creation is extracted with `saveTo`, not requested as a pre-run fixture. Generated functions such as `{{$uuid}}` change on each step: capture the first generated value from the input using `source: value`, then reuse its named variable.

The current platform precheck tracks producers within each case, not across cases. A lifecycle in one original case can run from initial inputs alone. For several original cases, keep their identities: execute the producer case first, then submit its consumers after the environment has the outputs. A single suite submission with absent cross-case outputs is not currently supported; do not prefill fake IDs or claim otherwise. An independent consumer may instead use an explicitly supplied existing-record fixture.

## Exact syntax

- `{{name}}` references a named environment value. `{{baseUrl}}` is the selected environment base URL; use `{{baseUrl}}/projects` for navigation when an environment is supplied.
- XPath tokens require `{{name|xpath}}` without surrounding quotes, for example `//tr[td[normalize-space(.)={{projectId|xpath}}]]/td[2]`.
- CSS tokens are escaped according to their string/identifier position. Role shorthand such as `button::{{name}}` supports variables; role JSON does not.
- Only locatorValue and operationValue are templated. Names, keywords, locator types, comparators and saveTo names are literal.
- Names are case-sensitive, at most 120 characters, contain no whitespace or `{ } |`, do not start with `$` or `data.`, and cannot be `baseUrl`.
- An external input already specified as a variable is an environment prerequisite, not a null YAML field. Keep the reference; runtime precheck requests absent input values. Use missingFields for unknown mapping/locator/capability, not for a value whose variable binding is already known.

## Check availability before the semantic audit

Run `python3 scripts/check_variable_flow.py CANDIDATE` after building a case. Each case starts with `baseUrl` and declared source-backed pre-run bindings; successful `saveTo` producers become available only to later steps in that case. Disabled or failure-ignored producers do not guarantee a value. Cross-case outputs require the already-described execution/environment prerequisite.

A source-backed pre-run input is a valid external binding even when its concrete value is absent. Preserve supplied variable names. When the accepted prerequisites explicitly prepare a value (for example, record a release ID and its collection ID before this case), choose distinct meaningful names and map each to that prepared object and consuming field. The requirement need not spell those template names verbatim or separately authorize parameter naming. Pass each evidenced name with `--external-variable NAME` to both the checker and exporter; runtime precheck requests absent values. Keep the source, meaning, availability time and consumers as internal evidence, not a new user-maintained manifest. If the object's meaning or preparation time cannot be established, retain that actual gap instead of declaring a name merely because it occurs in the candidate.

A baseline explicitly recorded in the prerequisites can be an initial input for that case. A baseline required to be observed during the case, a value created by its actions, and a later fresh observation require timely producers. Preserve independent expected values rather than deriving them from the result being tested. Assess each case with its own preparation; infer cross-case invalidation only where the requested execution contract actually shares state without renewed preparation. For a declared shared flow, use distinct names for independent fixtures and runtime outputs and preserve required refresh/producer timing. The flag proves neither provenance nor freshness.

The check covers executable `locatorValue` and `operationValue` references. Text in `missingFields.reason` is not executed. A declared fillable producer can supply its named output after its field is completed; the checker does not certify that completion rule, capture identity, capture timing or business oracle. Ordinary human editing/import remains governed by the platform; this is an internal generation/export check, with no new YAML fields.

## Recording an observed value

When an included action explicitly asks to read, record or capture actual values, identify which execution result carries each requested value. An `assert_text` result records its observed text; `saveTo` records text, live input value, attribute or URL and also makes it available to later steps. Use the supported channel matching the target and timing. A boolean `assert_visible` on a status predicate records that the condition passed, not which status appeared. A row identity supplied in a locator is not a readback of the displayed ID. For a request to capture both status and progress, record both actual cells even if separate predicates already check their allowed values. A requested later observation needs a fresh read; an earlier capture is not evidence of the later display.

Reuse an existing step's actual-value output when it already records the same object, field and time; add `saveTo` only when a capture or downstream binding is still needed. For a target that only asks whether a condition holds, an effective predicate can suffice without an extra capture. Conversely, a capture alone does not establish an expected property: retain every separate comparison, OR relation and full-collection identity requirement. Do not replace an OR status check with one fixed expected text merely to obtain an actual-value output.

## Extraction

Attach `saveTo` to a successful step whose source is still present after that step. Prefer waiting for the uniquely identified creation result, then extracting its displayed ID. Multiple matches fail. Avoid extracting from a submit button that disappears after navigation or from the first unrelated list row.

Each saveTo rule has `name`, `source` (`text`, `value`, `attribute`, `url`), optional `locatorType` and `locatorValue`, `attribute` for attribute source, optional string `defaultValue` and boolean `trim` (text only).

For text/value/attribute, omit both locator fields to inherit the step's already-rendered locator. This supports extraction from a row located by an environment variable. If specifying an extraction locator, provide both fields as a static locator: explicit saveTo locators do not support variables. URL source reads the full page URL and forbids locator fields; it does not parse an ID from the URL. There is no regex/JS/JSON extraction capability.

```yaml
- orderNo: 7
  stepName: 等待新建项目的ID并保存
  keyword: assert_visible
  locatorType: xpath
  locatorValue: "//tr[td[normalize-space(.)={{projectName|xpath}}]]/td[@data-field='id']"
  operationValue: 5000
  continueOnFailure: false
  enabled: true
  saveTo:
    - name: projectId
      source: text
```

The selector is illustrative; derive the actual locator from supplied source. Capture inputs with source=value, text cells with source=text, attributes with source=attribute and an attribute name. Essential record identities should not use a defaultValue that hides missing evidence. Producer/extraction steps and dependent operations use continueOnFailure=false. In cross-case orchestration, stop the chain if the producer fails; an old environment value does not prove this creation succeeded.

## Assertions and review

For initial input/textarea emptiness, capture the live value with `saveTo.source=value` before any input or clear action, then compare the captured scalar to `''` on a visible source-backed element. A placeholder, absent `@value` attribute or empty text node does not establish the current value. Preserve each required initial-value check; do not clear the control to make it pass. See semantic-review.md, “Live input values,” for the corresponding counterexample and repair check.

Keep intended inputs/expected values separate from observed values. Compare a renamed record to `{{newProjectName}}`, not to a variable just captured from that same displayed name. When the accepted design also checks that an input displays exactly the submitted value, use a stable intended input binding and capture the live value into a different variable. Compare these two scalars with a supported predicate on a source-backed visible container (see predicate-strategies.md). A post-input saveTo supplies an observation; it does not by itself prove input equality. Re-evaluating a generated function cannot recover the original intended value, so use a pre-run unique input binding when that equality must be tested. Keep any separately required capture and downstream identity chain. Capture a pre-action baseline before the mutation, then compare the post-action observation to it when equality is the requirement. Capturing a scalar does not provide arithmetic, pagination traversal or collection comparison; only claim these when the executor and source provide a faithful implementation.

A value created during the test is supported when a source-backed earlier saveTo supplies it. Review the producer timing, unique object identity and consumer expression. A missing producer, impossible observation or changed business oracle is still an unresolved problem; retain the original target and explain the actual gap. No arbitrary script execution or invented set_variable keyword is available.
