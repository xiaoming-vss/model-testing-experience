---
name: code-review
description: "Review a branch, PR, committed range, or working tree against repository standards and the originating spec."
---

Review **Standards** and **Spec** independently; report actionable defects with evidence, not a summary of changes.

## Scope

1. Honor the user's scope. For a branch or commit range, resolve the supplied base and capture `git diff <base>...HEAD` and `git log <base>..HEAD --oneline`. For work in progress, include both `git diff --cached` and `git diff`, plus relevant untracked files from `git ls-files --others --exclude-standard`; inspect their contents, including additions and deletions. Keep staged and unstaged changes distinct when they differ. If both committed work and the working tree are requested, include both. Do not run code from untracked files.
2. If a committed comparison is requested without a base, infer it only when the repository or request makes it unambiguous; otherwise ask. A working-tree review needs no base. Validate refs and report an empty scope rather than declaring a review passed.
3. Find the spec from the user, referenced issues, or matching `docs/` and `.scratch/` materials using `docs/agents/issue-tracker.md`. If unavailable, review Standards and state that Spec could not be verified; do not block independent review.
4. Read the applicable root and project `AGENTS.md`, the context map, relevant project rules and ADRs. The [smell baseline](SMELLS.md) is a set of judgement calls, not hard violations; repository rules take precedence and tooling-enforced items need not be repeated.

## Review

When sub-agents are available and permitted, run Standards and Spec in parallel with the same exact scope, changed files and commit list. Give the Standards reviewer the standards paths and `SMELLS.md`; give the Spec reviewer the spec path. Otherwise review the two axes independently yourself.

- **Standards**: identify documented rule violations, citing the rule and affected code; label any smell as a judgement call and explain the concrete impact.
- **Spec**: identify missing, partial or incorrect requirements and consequential unrequested behavior; cite the relevant requirement and code. Skip this axis if the spec is unavailable.
- Verify each finding against the current scoped content. Report only actionable issues, with priority, file and line, trigger and impact. Do not claim tests ran unless they did.

Present the axes separately, followed by verification performed and limitations. If an axis has no findings, say so without implying the entire project is defect-free.
