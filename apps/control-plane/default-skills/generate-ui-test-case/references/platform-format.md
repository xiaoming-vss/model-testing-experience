For environment-backed tasks, read [environment-variables.md](environment-variables.md); it defines supported variable navigation and saveTo in addition to the literal-field examples below.

The optional step field `missingFields` extends this format for human completion; read [handoff.md](handoff.md). Missing entries allow null only for the named fields in draft validation. Formal import/execution requires all entries resolved. The executable keyword set below is unchanged.

## Required Task Context

Read these values from the task instruction before generating. Do not invent them.

- `targetBaseUrl`: the absolute origin of the environment under test, for example `http://10.9.103.80:30080`. Every literal `open` URL must use this origin; environment-backed tasks may use `{{baseUrl}}` for the selected environment.
- `login`: the login route, tenant, username, password, and a stable post-login URL or element. Alternatively the task may state that the suite is already authenticated or that a login case runs first.
- `testData`: names, descriptions, and other values supplied by the task. If a write needs a unique value and it is not asserted later, use `{{$timestamp}}` or `{{$uuid}}`.
- `scope`: the page and flow named in the instruction. Do not broaden the case to unrelated modules.

Rules:

1. Never use `localhost`, `127.0.0.1`, a Vite default port, or the example URL from this document unless the task explicitly names that environment.
2. If the source contains an explicit deployment URL, use it only when it matches the environment named by the task. Do not derive a public URL from dev-server configuration.
3. If neither targetBaseUrl nor a selected environment baseUrl binding is supplied, keep the open operationValue null and describe the required environment URL in missingFields.
4. If authentication is required but not supplied, include known login steps with missing fields, or attach an authentication prerequisite missingFields entry to the first dependent step.

## Output Contract

Return a YAML list directly, including for a single case; use `[]` only when all supplied designs are fully excluded. Start a nonempty result with `- name:`. Each item is a complete case with `name`, `enabled`, `stepsJson`, and `orderNo`. Preserve the reviewed design names in `batch.expectedCaseNames` order. Return YAML content, not a file receipt, prose or Markdown fence.

Return a YAML list when generating multiple cases:

```yaml
- name: Login succeeds
  enabled: true
  stepsJson:
    - orderNo: 1
      stepName: Open login page
      keyword: open
      operationValue: http://app.example.com/login
      continueOnFailure: false
      enabled: true
    - orderNo: 2
      stepName: Input username
      keyword: input
      locatorType: placeholder
      locatorValue: Username
      operationValue: test_user
      continueOnFailure: false
      enabled: true
    - orderNo: 3
      stepName: Click login button
      keyword: click
      locatorType: role
      locatorValue: button::登录
      continueOnFailure: false
      enabled: true
  orderNo: 1

- name: Username is required
  enabled: true
  stepsJson:
    - orderNo: 1
      stepName: Open login page
      keyword: open
      operationValue: http://app.example.com/login
      continueOnFailure: false
      enabled: true
    - orderNo: 2
      stepName: Input password
      keyword: input
      locatorType: placeholder
      locatorValue: Password
      operationValue: Pass123456
      continueOnFailure: false
      enabled: true
    - orderNo: 3
      stepName: Click login button
      keyword: click
      locatorType: role
      locatorValue: button::登录
      continueOnFailure: false
      enabled: true
    - orderNo: 4
      stepName: Assert username validation message
      keyword: wait_text
      locatorType: text
      locatorValue: Username is required
      operationValue: Username is required
      continueOnFailure: false
      enabled: true
  orderNo: 2
```

Do not wrap the YAML in markdown when the user asks for directly importable output. Preserve the user's language for `name` and `stepName`.

## Case Rules

- Use the reviewed design’s unchanged `name` for the case name.
- Use `enabled: true` unless the user explicitly asks to disable a case.
- Use `orderNo` at case level to preserve case order, starting from 1 within the current module; the Worker renumbers the merged result.
- For multiple cases, output a top-level YAML list. Each list item must be a complete case with its own `name`, `enabled`, `stepsJson`, and case-level `orderNo`.
- In multiple-case output, increment the case-level `orderNo` across cases, but restart each case's internal `stepsJson.orderNo` from 1.
- Use `stepsJson` for all executable steps.
- Keep known steps concrete; preserve unresolved content through missingFields. Do not add manual-test fields such as priority, precondition, expectedResult, moduleName, or description unless the user asks.

## Step Defaults

Each step must include these default fields unless the user explicitly asks otherwise:

```yaml
continueOnFailure: false
enabled: true
```

`continueOnFailure: true` controls whether execution proceeds after an error. The failed step still marks the case failed; later successful steps do not clear that result. Use it only when continued evidence collection after failure is intended. It is not a retry, optional assertion, ignored failure, or “any attempt succeeds” operator. For a stable terminal-state check after a bounded wait, use supported wait/refresh steps followed by the decisive assertion; intermediate unsuccessful assertions would still fail the case.

Each step must also include:

```yaml
orderNo: 1
stepName: Step name
keyword: open
```

Add `operationValue`, `locatorType`, `locatorValue`, and `comparator` only according to the keyword rules below.

## Valid Keywords

Only use these keywords:

- `open`
- `reload`
- `click`
- `dblclick`
- `input`
- `clear`
- `press`
- `wait_text`
- `assert_text`
- `assert_visible`
- `assert_hidden`
- `assert_url`
- `screenshot`
- `sleep`

Do not use `wait_visible` or `wait_hidden`; a negative business expectation is `assert_hidden`.

## Locator Rules

`locatorType` means the element location method. `locatorValue` means the element location value.

Allowed `locatorType` values:

- `css`
- `xpath`
- `text`
- `placeholder`
- `label`
- `test_id`
- `testid`
- `role`

Among locators whose actual rendered structure and uniqueness are established, prefer this order:

1. `test_id` or `testid`.
2. `role` with an accessible name, or a unique visible `text`.
3. `placeholder` or `label` when the framework associates it with the control.
4. Stable CSS attribute selectors such as `[name='...']` or `[aria-label='...']`.
5. Semantic XPath based on `@role`, `@aria-*`, visible text, or a label-to-control axis.

### Source-only locator restrictions

Trace a custom control from the page's props to its renderer before choosing a locator. Read the component implementation in the supplied source or the exact resolved dependency version (lockfile plus matching package source). Record the relevant render branch and emitted tag/attributes; a component named Select does not establish a native input, option role or selected attribute. Reuse verified component evidence within the invocation. A historical generated locator is a search hint, not renderer evidence.

If the application archive omits the dependency implementation, resolve its exact package/version and integrity from the supplied lockfile, then use the read-only package source reader before declaring a renderer gap:

```bash
python3 scripts/read_npm_source.py --package PACKAGE --version EXACT_VERSION --integrity LOCKFILE_SRI --output-dir "$task_renderer_dir"
```

This reads public npm metadata, verifies the archive against the supplied lockfile integrity and package identity, and saves `archive.tgz`, `source/package.json`, `members.json` and `provenance.json`. Inspect the member inventory for the component and shared renderer. Read selected members into a fresh directory by running the same command with `--archive "$task_renderer_dir/archive.tgz" --member PATH` (repeat `--member` for related files) and a new `--output-dir`; this second call uses the verified local archive. No dependency installation or package script execution is involved. Record the application props and relevant render branch alongside these source hashes. A version range or remembered library convention is insufficient. If the resolved version/integrity is absent, the source cannot be retrieved, or the component is locally overridden, retain that precise evidence gap instead of guessing DOM.

Use native semantics where the rendered element provides them. Otherwise use a source-established attribute or exact class token, scoped to the intended visible control and state. For a dependency class, verify its emitted spelling/prefix in that version and props, its intended node, and uniqueness; avoid generated hashes. An exact class token can be expressed as CSS `.token` or XPath `contains(concat(' ', normalize-space(@class), ' '), ' token ')`. The latter tests a whole token, unlike an unbounded substring. A recorded DOM can also establish the structure: require exactly one raw locator match, then verify it is visible/actionable. Hidden duplicate matches still violate strict mode unless the locator itself excludes them. If renderer evidence is unavailable, retain the precise locator gap; inventing a semantic role does not resolve it.

Restrictions:

- Unbounded class substring matches such as XPath `contains(@class, ...)`. Substring matching can hit several generated class names; for example, a component library may use `n-checkbox` plus `n-checkbox-box` and `n-checkbox-box__border`, so Playwright strict mode sees several elements and the step fails. The same problem exists in other design systems.
- Unverified component-library classes or generated hash classes. A library prefix alone is neither evidence of correctness nor a reason to reject a verified exact token.
- Positional CSS such as `:nth-child`, `:nth-of-type`, or deeply nested descendant chains.
- Generic text such as `确认`, `取消`, or `请输入` without proving it is unique on the current screen. If the same text appears more than once, scope it by a visible container or role.
- Exact equality on a form label's full text. Required fields often render a marker outside the label text, for example `<span>字段名</span><span>&nbsp;*</span>`, so `normalize-space(.)='字段名'` can match zero elements. Use a label-text span or `contains` instead: `//label[.//span[normalize-space(.)='字段名']]/following::input[1]` or `//label[contains(normalize-space(.),'字段名')]/following::input[1]`. Check the rendered label text before choosing.
- Paraphrased or translated labels. Copy the exact visible text. If the source uses an i18n key, resolve it against the active locale and use its actual value, not a synonym. For example, a key named `common.search` may resolve to one exact string in one locale and a different string in another; use the resolved value for the locale under test.
- `get_by_label` assumptions when the framework does not associate `<label for>` with the control. Check the rendered DOM; if the label is not associated, use a label-to-control XPath.

### Proving uniqueness

Before writing a locator, determine whether it matches exactly one element and whether that element is visible/actionable. If a rendered DOM or browser session is available, count all matches, including hidden nodes. If only source is available, use the renderer-evidence procedure above. Prove roles, attributes and class tokens from emitted DOM rather than the component name. If no unique semantic locator can be established, leave locatorType/locatorValue null and describe the intended target in missingFields.

Accessible-name matching for `role` is substring-based in the runner. A role locator for a short name also matches a longer control whose name contains it; for example, `button::保存` also matches `批量保存`. Before using a role name, check that it is not a substring of another visible control. When names collide, use an exact-text XPath such as `//button[normalize-space(.)='保存']` or a stable attribute that identifies only the intended control.

The standalone validator checks structure and does not certify renderer evidence or uniqueness. Its source-only locator heuristics run when evidence checking is enabled; a normal CLI pass is not proof that a selector is source-backed. Keep the semantic audit responsible for the facts above.

### Proving column semantics

A locator can be unique and still point at the wrong field. Derive the final visible column order for the active tab/filter: start with column definitions, apply computed filtering, insertion/reordering and selection/expand columns, then map each header/key to its rendered cell. Repeat for each distinct table or branch; declaration order alone is insufficient. Retain this map as local evidence for numeric td indices. Header keys establish column identity; they do not establish containment of data rows.

Before reusing a table locator helper, resolve the application props through the renderer's layout condition and write the resulting ancestor/child shape in local evidence. For example, a renderer may use `headerInBody = maxHeight === undefined && !flexHeight`: an active height/flex prop then produces a common wrapper containing separate header and body tables. In that branch, `table[.//th[HEADER]]/tbody/tr` cannot select a data row even though both the header key and cell key are correct. Scope the source-established common wrapper by its header, then descend through its body to the identified row. Use the single-table form only when that branch is actually established. Apply this separately to the page table and each drawer/detail table; their props can differ.

Check a populated, valid source-shaped example before expanding that helper across cases: the intended row/cell must match once and an adjacent unrelated table must remain outside its scope. Include hidden retained tables when the renderer preserves them. A selector that matches zero elements in the valid example is a locator defect, not evidence that the expected business value is absent. A synthetic DOM probe can test the selected shape without operating the product; it supports only the branch and scope represented by the fixture. If the source cannot establish the active layout, retain that specific locator gap.

Before reusing a summary-table or detail-table locator, verify which column it addresses:

- In a two-pair description row `th, td, th, td`, the left field is `td[1]` and the right field is `td[2]`. The row matches both headers, so `tr[th[...]]/td[1]` always returns the left value even when the observation names the right field.
- Write the header position into the predicate: `tr[th[1][normalize-space(.)='<left label>']]/td[1]` and `tr[th[2][normalize-space(.)='<right label>']]/td[2]`.
- Never reuse the same `td[1]` locator for different fields in one summary row.
- When runtime evidence provides a sample text for a locator, compare the sample with the expected field value before emitting the step. If they differ, inspect the source and object identity; use a supported locator or record the unresolved target in missingFields without rewriting the expected outcome.

### Design-system and table examples

The concrete labels below are illustrative only; the locator shapes apply to any component library. These patterns work when the page has one data table and one visible drawer:

```yaml
# First data row checkbox: scope by the row, then use the semantic role.
- keyword: click
  locatorType: xpath
  locatorValue: (//tbody/tr)[1]//div[@role='checkbox']

# Toolbar button whose name is a substring of another button ("保存" vs "批量保存").
# Role name matching is substring-based, so use exact visible text here.
- keyword: click
  locatorType: xpath
  locatorValue: //button[normalize-space(.)='保存']

# Drawer title by unique visible text.
- keyword: assert_text
  locatorType: text
  locatorValue: 示例面板
  operationValue: 示例面板
  comparator: contains

# Form field whose <label> is not associated with a for attribute.
# Required labels may append a marker such as " *" outside the label text;
# target the label-text span, or use contains(normalize-space(.),'字段名称').
- keyword: input
  locatorType: xpath
  locatorValue: //label[.//span[normalize-space(.)='字段名称']]/following::input[1]
  operationValue: 示例值

# Drawer footer button by role; scope by the visible drawer if the page has other confirm buttons.
- keyword: click
  locatorType: role
  locatorValue: button::确认
```

Do not copy a locator from these examples without checking the actual screen. In particular, `button::确认` is only safe while exactly one visible confirm button exists.

## Keyword Rules

### open

- Use to open a specified URL.
- Do not include `locatorType` or `locatorValue`.
- Require `operationValue` as the URL.
- The URL must use the task's `targetBaseUrl`. Never use the example host or a guessed dev port.

```yaml
keyword: open
operationValue: http://app.example.com/login
```

### reload

- Use to reload the current page.
- Do not include `locatorType` or `locatorValue`.
- Do not require `operationValue`; omit it unless the user explicitly supplies one.

```yaml
keyword: reload
```

### click

- Use to click an element.
- Require `locatorType` and `locatorValue`.
- Do not require `operationValue`; omit it unless the user explicitly supplies one.

```yaml
keyword: click
locatorType: role
locatorValue: button::登录
```

### dblclick

- Use to double-click an element.
- Require `locatorType` and `locatorValue`.
- Do not require `operationValue`; omit it unless the user explicitly supplies one.

```yaml
keyword: dblclick
locatorType: role
locatorValue: row::数据行
```

### input

- Use to clear an editable element and then input text.
- Require `locatorType` and `locatorValue`.
- Require `operationValue` as the input text.
- Treat `input` as clear-then-type; do not add a separate `clear` step before it unless the user asks.

```yaml
keyword: input
locatorType: placeholder
locatorValue: Username
operationValue: test_user
```

### clear

- Use to clear an editable element.
- Require `locatorType` and `locatorValue`.
- Do not include `operationValue`.
- Underlying behavior is equivalent to Playwright `Locator.fill("")`.
- Only use for editable `<input>` text types, `<textarea>`, and `[contenteditable]`.
- Do not use for normal `div`, `span`, buttons, dropdowns, readonly elements, non-editable elements, or unsupported input types.

```yaml
keyword: clear
locatorType: css
locatorValue: input[name='username']
```

### press

- Use to press a key or key combination on an element.
- Require `locatorType` and `locatorValue`.
- Require `operationValue` as the key or key combination, such as `Enter`, `Escape`, `Tab`, `Control+A`, `Meta+A`, or `Shift+Tab`.

```yaml
keyword: press
locatorType: css
locatorValue: input[name='username']
operationValue: Enter
```

### wait_text

- Use to wait until a located element contains or shows the expected text. This polls until the text appears, so use it for transient messages such as toasts.
- Require `locatorType` and `locatorValue`.
- Require `operationValue` as the text to wait for.

```yaml
keyword: wait_text
locatorType: text
locatorValue: 保存成功
operationValue: 保存成功
```

### assert_text

- Use to assert text on a located element. Prefer `wait_text` for messages that appear and disappear.
- Require `locatorType` and `locatorValue`.
- Require `operationValue` as the expected text.
- Require `comparator`.
- `comparator` must be `eq` or `contains`.

```yaml
keyword: assert_text
locatorType: text
locatorValue: 登录成功
operationValue: 登录成功
comparator: contains
```

### assert_visible

- Use to assert an element is visible within a timeout.
- Require `locatorType` and `locatorValue`.
- Require `operationValue` as the timeout in milliseconds.

```yaml
keyword: assert_visible
locatorType: role
locatorValue: button::登录
operationValue: "3000"
```

### assert_hidden

- Use when the caller declares `absent`, to wait for an element, message or validation prompt to be hidden or detached at the observation point.
- Require `locatorType` and `locatorValue` that identify the element that must not appear.
- Require `operationValue` as the timeout in milliseconds.
- Do not include `comparator`.
- The step passes as soon as the element is not visible or is detached. The timeout is the maximum wait for that state, not a continuous absence-monitoring interval: an initially absent element can pass immediately and appear later. Place the check after the source-backed action/result synchronization required by the design. This expresses a stage-two `absent` observation; do not replace the negative business target with a positive success toast. A requirement to never appear throughout an interval needs an actual monitoring strategy or an explicit capability limitation.

```yaml
keyword: assert_hidden
locatorType: text
locatorValue: 转换格式必填
operationValue: "3000"
```

### assert_url

- Use to assert the current page URL.
- This keyword checks immediately and does not wait. Use it after `open` (which waits for load), or after a preceding `wait_text`/`assert_visible` that polls for a post-login or post-navigation element.
- Do not include `locatorType` or `locatorValue`.
- Require `operationValue` as the expected URL or URL fragment.
- Require `comparator`.
- `comparator` must be `eq` or `contains`.

```yaml
keyword: assert_url
operationValue: /home
comparator: contains
```

### screenshot

- Use to take a screenshot.
- Do not include `locatorType` or `locatorValue`.
- Do not include `operationValue`.

```yaml
keyword: screenshot
```

### sleep

- Use to sleep for a fixed duration.
- Do not include `locatorType` or `locatorValue`.
- Require `operationValue` as the wait time in milliseconds.
- Prefer an assertion or `wait_text` over a fixed sleep. Use `sleep` only when the application has no stable observable state.

```yaml
keyword: sleep
operationValue: "1000"
```

## Authentication and Preconditions

- If the target route is behind a login guard, include the login flow at the start of the case unless the task explicitly says the suite is already authenticated or a login case runs first and shares the session.
- Use only the login route and credentials supplied by the task. Never invent a tenant, username, or password.
- After clicking login, first wait for a unique element that only exists after login. Use `wait_text` or `assert_visible` with a timeout; choose a page-specific card title, heading, or other text that appears exactly once, not a menu label or breadcrumb that may appear twice.
- Do not use the login username or tenant as the post-login visible text. The page often displays a separate display name, or no account text at all; use a page element that the source shows after login.
- Prefer a stable page element over the transient "登录成功" toast. A toast can disappear before the wait starts; use it only when the application has no stable post-login element.
- `assert_url` checks immediately and does not poll. Never place `assert_url` directly after a click that triggers navigation. Put a polling `wait_text` or `assert_visible` first, then optionally assert the URL.
- If the task provides credentials but no login route, use the source router to find the login route; do not guess a different host.
- A case that starts at a protected page without login steps must have a declared suite login or an authentication prerequisite in missingFields; preserve its reviewed design name.

## Assertion and Test Data Rules

- Assert that the target panel or drawer opened before filling it.
- For success feedback, use `wait_text` on the exact message. Do not rely only on `assert_text` for a toast that may disappear before the step executes.
- When the flow creates or updates a record and the list page is reachable, add a final check that the record is visible on its list page. A toast alone does not prove the business result.
- If a field value is not unique across the page (for example a description reused by several rows), do not assert it with a page-level `text` locator. Scope the assertion to the row or container identified by the unique key (name or ID).
- Use task-provided test data. For a value that must be unique but is not asserted later, use `{{$timestamp}}` or `{{$uuid}}`. For a value reused later, prefer the supplied named environment input, or capture a generated input once with saveTo and reuse that named value; built-in functions render independently per step.
- Do not delete, reset, or clean up data unless the task explicitly asks for it.

Example of a scoped assertion for a non-unique field:

```yaml
- keyword: assert_text
  locatorType: xpath
  locatorValue: //tr[contains(.,'示例名称')]//td[contains(normalize-space(.),'示例描述')]
  operationValue: 示例描述
  comparator: contains
  continueOnFailure: false
  enabled: true
```

### Stable values and record identity

Named environment variables and saveTo preserve identity across steps; follow [environment-variables.md](environment-variables.md). Built-in function expressions still render independently per step. Newest-first ordering alone does not prove a sampled first row belongs to this operation. Capture a positively identified creation result and reuse its ID; if no faithful observation is available, retain the intended relationship and explain the actual gap.
