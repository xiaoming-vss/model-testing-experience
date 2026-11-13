# Source-backed predicates with existing execution features

Read for count changes, uniqueness, exact collections or fixed-page-count scenarios. These are implementation strategies, not production locators. The examples were exercised on synthetic DOM through the existing StepExecutor and Chromium, including duplicate/substitution counterexamples. Derive the actual table scope, ID column, total-text format and page controls from the task's source. Do not claim a live product was tested by these examples.

`assert_visible` can wait for an element selected by a true XPath predicate. Its operationValue remains a positive timeout in milliseconds. SaveRule source=text captures text as-is; it does not provide regex extraction, arithmetic or arrays. XPath 1.0 itself can perform numeric comparisons and arithmetic after escaped variables become string literals.

## Runtime count change

Save the source-backed footer text with saveTo, for example a variable baseline whose value is `共 11 条`. On the corresponding current footer, this predicate proves an increase of exactly one:

```xpath
//*[@id='total'][number(translate(normalize-space(.),'共 条','')) = number(translate({{baseline|xpath}},'共 条','')) + 1]
```

The example `id='total'` belongs only to the synthetic fixture. Confirm the real footer's exact text format before translating characters; do not apply this to formatted text with unhandled separators or to a detail view that has no total footer. A known static expected count remains a legitimate fixture alternative. Never put the business count in assert_visible.operationValue.

## Unique IDs within one fully observed table

For a fixture whose ID is in its first column, this rejects a row whose ID equals that of any preceding sibling:

```xpath
//table[@id='records'][count(tbody/tr)>0 and not(tbody/tr[td[1] = preceding-sibling::tr/td[1]])]
```

An exact expected collection still needs membership of every expected ID and exact total. For distinct expected IDs id1/id2/id3:

```xpath
//table[@id='records'][count(tbody/tr)=3 and count(tbody/tr[td[1]={{id1|xpath}}])=1 and count(tbody/tr[td[1]={{id2|xpath}}])=1 and count(tbody/tr[td[1]={{id3|xpath}}])=1]
```

The number three is solely this example's known collection size. For the task, use the actual complete fixture list, not a sample or minimum prerequisite count. Unknown IDs can be described in a complete-list locator gap only when filling that locator makes the whole intended assertion work. Equality against one row per expected ID and exact total rejects duplicate, omitted and substituted IDs. Ensure the whole expected scope is actually rendered; table predicates do not cover unseen pages or virtualized rows.

## Two-page distinct-count target without a set_merge operation

This strategy applies to an accepted claim about two explicitly observed pages whose first page has fixed size K. It expresses the distinct count of those observations and its comparison with the required total. It does not assume that every allowed fixture fits two pages: if the original remaining-count expectation conflicts with a larger fixture, preserve the expectation and surface that design conflict rather than inventing a bound. A target requiring arbitrary-page traversal is different and is not implemented by this strategy.

1. On the first page, assert exactly K rows and uniqueness of all K IDs. Use saveTo text rules on each of the K ID cells to retain first1 ... firstK and save the total footer as total. Multiple scalar saveTo rules are already supported.
2. Execute the source-backed navigation to page two.
3. Assert exactly total minus K rows, uniqueness within that page, and that none of its IDs equals any saved first-page ID. For K=10, the exact count expression is `count(tbody/tr)=number(translate({{total|xpath}},'共 条',''))-10`. Combine the within-page uniqueness predicate with `not(tbody/tr[td[1]={{first1|xpath}} or ... or td[1]={{first10|xpath}}])`; expand all ten equality terms, never leave ellipses in executable output.

Treat the three uniqueness obligations as one proof: first-page uniqueness, second-page uniqueness, and cross-page disjointness. Counts plus cross-page disjointness alone still accept first-page [A,A,C,...] or second-page [K,K]. Verify each predicate on the serialized steps; a step name claiming “no duplicates” is not evidence.

The first-page count plus second-page count equals the saved total; uniqueness within each page and disjointness across pages establishes the distinct union count. No unsupported array extraction or set_merge keyword is introduced. The actual supported predicates implement the retained count target, even if an explicit set_merge operation was excluded upstream. Preserve other independent exclusions rather than reintroducing them as separate test goals.

A different accepted page scope requires its own complete proof. Do not infer two pages merely from “at least 11 records”, force a smaller fixture to make this strategy fit, change a test of the default page size, or replace a full expected-ID equality target with distinct count alone. A true unhandled scope or design inconsistency remains a design question.

Keep observation timing: switching to a larger page size and then proving uniqueness of a new single-page query does not prove that the two previously observed pages were disjoint. A pagination bug can repeat a first-page record only on page two while the large-page query is correct. Capture the actual original page IDs before navigation and compare those observations when the target is about the original two pages.

## Two explicitly observed pages: compare the observations, not an invented array

When the source explicitly observes pages one and two, and the first page has a fixed K rows, the retained claim about those two observations can be implemented without a set_merge keyword or dynamic iteration:

1. Assert first-page count K and internal ID uniqueness, and capture its K IDs as separate supported scalars.
2. Navigate to the second page. Assert its required row count, internal uniqueness, and that none of its IDs equals any of the captured first-page IDs.
3. For “distinct union count equals total N,” the count conditions K and N-K plus the uniqueness/disjointness conditions prove precisely that claim. No array needs to be materialized. An excluded raw array-building/set_merge operation does not force exclusion of this independently expressible result.

This is an expression of a two-observation assertion, not an assumption that the dataset inherently fits two pages. If N exceeds the amount those pages can display, the original “second page contains N-K remaining rows” expectation fails. Preserve that expectation and expose its conflict with an unbounded prerequisite; do not invent an upper bound or call the predicate unsupported. If the source instead requires reading an arbitrary number of pages, this strategy does not satisfy it.

For equality against an independently known complete expected fixture ID set, additionally require every ID on both observed pages to belong to that set, and the summed count to equal its cardinality. Together with both internal uniqueness checks and cross-page disjointness, this proves exact equality and rejects substitutions, duplicates and missing records. These combined checks were exercised through the real StepExecutor on synthetic Chromium DOM. Unknown static expected IDs are a data gap when that complete fixture set can be supplied before execution; never derive the expected set from the result under test itself. If the baseline must first be extracted from an unknown number of pages, its construction remains a genuine unresolved traversal dependency.

Keep identity completeness distinct from cardinality. Without an independent expected-ID oracle, distinct count alone does not prove that the correct identities were returned. Explain the actual missing oracle or unsupported traversal, rather than claiming that every finite collection comparison requires a new executor operator.
