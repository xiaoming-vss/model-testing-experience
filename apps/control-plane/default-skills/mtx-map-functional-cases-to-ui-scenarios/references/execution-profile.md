# Versioned execution capability context

[execution-profile.json](execution-profile.json) is the bundled `mtx-ui-baseline/1.0` description. Its version identifies this skill's assumed executor contract, not a claim that the current deployment was inspected. Scenario design and YAML generation must use the same profile. The distribution sync tool keeps their bundled copies identical.

- `capabilities.operations/assertions` defines semantic labels allowed in the existing design output.
- `features` explicitly states XPath predicates, scalar capture, variable substitution, conditional flow, runtime iteration and cross-case preflight support. `captureSources` specifies the available text/value/attribute/url channels.
- These are task inputs/internal evidence. Do not add profile fields to scenario or YAML output. Preserve a separately supplied caller capability list; if it conflicts with an explicit execution profile, report the conflict instead of silently replacing either.
- On the established platform with no override, use the bundled profile. If the caller identifies a different executor/version or explicitly disables a feature, use its matching profile; unsupported or unknown feature semantics require confirmation, not guesses based on a similarly named primitive.
- Equivalent implementations may use only enabled features. `visible` alone does not establish support for scalar capture or arbitrary collection traversal. A finite XPath proof still needs the accepted scope and source-backed DOM. Enabling a feature flag does not add a new YAML keyword or implement a missing operator.

Pass `--execution-profile /path/to/profile.json` to the scenario validator and YAML exporter when an override was supplied. Export checks explicit capture, template and XPath-predicate feature use; semantic reasoning still checks timing, finite scope, dependencies and equivalents. Do not claim those are mechanically proven.
