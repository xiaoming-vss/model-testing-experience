# UI YAML 语义复核


When read-only review is explicitly requested, or a legacy candidateYaml call has no explicit repair intent, return only the review JSON report. Explicit repair requests follow the generation/repair workflow using that candidate; the data field name does not override the requested task. The report supplies evidence for human review; findings do not declare generation failure or authorize rewriting YAML.

Read [semantic-review.md](../references/semantic-review.md). Bind every finding to the exact supplied candidate and its current case/step positions. Inspect each retained case against the accepted design, using the original cases and source to verify evidence. Reuse source-backed evidence already in the inputs; inspect additional source only to resolve a concrete suspected mismatch. Account for earlier `saveTo` producers and later variable consumers before reporting a runtime-value issue.

Return supported findings using the caller's existing fields and codes. For an upstream design conflict, identify what requires human design confirmation in `evidence` and `repair`; keep the original expectation. A valid assertion that exposes a product defect is not a candidate defect. Uncertainty or a preferred implementation is not enough to report a mismatch.

Review does not require creating coverage accounts, running the generation/export workflow, or obtaining a passing semantic audit. Keep candidate and inputs unchanged. A request to repair the review JSON only permits correcting report syntax and references, not editing the candidate. An empty issues array means no supported finding, not a guarantee of correctness. If the review cannot be completed, report failure to the caller rather than claiming an empty successful review; the caller retains the validated draft and marks review incomplete.

