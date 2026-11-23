---
name: domain-modeling
description: Sharpen project terminology and record domain decisions when editing a context glossary or ADR.
---

# Domain modeling

1. Read `CONTEXT-MAP.md` and `docs/agents/domain.md`; identify the affected context, existing glossary and relevant ADRs. For cross-project changes read producer and consumer contexts. Repository instructions determine paths, required ADRs and review procedures.
2. Compare proposed terms with the glossary and code. Surface conflicts, overloaded terms and mismatched behavior; use concrete scenarios to resolve them with the user when necessary.
3. Record each confirmed term in the relevant `docs/<project>/CONTEXT.md`, using [CONTEXT-FORMAT.md](CONTEXT-FORMAT.md). Keep definitions about the domain; put implementation contracts and operational details in project docs. Create a context only when needed and update the map.
4. Record decisions as required by the repository's [spec change checklist](../../../docs/agents/domain.md#规范变更检查清单), even if a generic ADR heuristic would not require one. For other choices, an ADR is useful when reversal is costly, the decision is surprising without context, and genuine alternatives were considered. Use [ADR-FORMAT.md](ADR-FORMAT.md).

Do not invent a decision, resolve an open question on the user's behalf, or silently override an existing ADR. State unresolved questions and the affected files.
