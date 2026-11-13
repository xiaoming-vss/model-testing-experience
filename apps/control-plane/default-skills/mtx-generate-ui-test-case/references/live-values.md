# Assert initial and current field values

For an input/textarea value target, inspect the current DOM `value` property. A `placeholder` attribute can remain present when the control contains text; `@value`, `not(@value)`, `text()` and `normalize-space(.)` need not reflect an edited input or textarea. Neither source defaults nor those predicates prove initial emptiness. These checks remain valid for a target specifically about the placeholder or attribute itself.

The executor supports capturing the control through `saveTo: [{name: actualValue, source: value}]` on a supported observation, then comparing `{{actualValue|xpath}}` to `''` (or an independent expected scalar) in a predicate on a visible, source-backed element. Capture before any clearing/filling when the target is the initial value; clearing the control would erase the defect. Use separate observations for separately required name and description values.

A captured scalar describes its capture time. To check that a field is still empty after another action, capture its value again at that later point and compare the fresh observation. Reusing the initial empty scalar cannot reject a field populated later by the UI. Keep an intentional baseline separately when the target is before/after equality; compare it with a fresh later observation, not with itself.

Apply the same check to the proposed repair: a nonempty live value with an unchanged placeholder and absent HTML value attribute must fail an empty-value assertion. Do not recommend `not(@value)` as an emptiness fix or claim that live-value reading is unsupported when `saveTo.source=value` is available. Preserve a genuine missing locator as a locator gap without replacing the required value comparison.

## Complete a value target

Generation, repair and review use the same completion criterion: each retained value expectation has both a live-value observation at its required time and an effective comparison against the independent expected value. `saveTo` alone records a value; it accepts both empty and nonempty controls and does not assert emptiness. A target that only asks to record a value does not require an extra comparison.

For example, this pair tests an initially empty control. The example ID is a fixture placeholder, not a suggested production locator; substitute the actual source-backed control and a distinct capture name:

```yaml
- orderNo: 1
  stepName: Read the initial field value
  keyword: assert_visible
  locatorType: xpath
  locatorValue: //input[@id='example-field']
  operationValue: '5000'
  saveTo:
    - name: fieldInitial
      source: value
  continueOnFailure: false
  enabled: true
- orderNo: 2
  stepName: Assert the initial field value is empty
  keyword: assert_visible
  locatorType: xpath
  locatorValue: //input[@id='example-field'][{{fieldInitial|xpath}}='']
  operationValue: '5000'
  continueOnFailure: false
  enabled: true
```

Place both before the first clearing/filling action. For a required later value, insert a fresh capture/comparison pair at that later observation point. For a required independent nonempty expected value, compare against that supplied scalar rather than a value copied from the same observed control. Preserve separately required placeholder, required-marker and visibility expectations; they test different properties.

Check three counterexamples against the serialized candidate: an initially prefilled control, an initially empty control that becomes populated after the intervening action, and a changed placeholder while the live value stays empty. Only the targets actually about each property should fail. Verify both separately required controls when a target names name and description; one empty field does not establish the other.
