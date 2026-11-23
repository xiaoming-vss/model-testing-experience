# ADR format

Follow `docs/agents/domain.md` and the affected project's existing ADRs. Place decisions in `docs/<project>/adr/`; use that project's next available number. For cross-project changes identify the owning project and link affected contexts and ADRs.

Every ADR must contain the metadata checked by `scripts/check_docs.py`:

```md
# ADR NNNN: Decision title

- 状态：已接受
- 日期：YYYY-MM-DD
- 取代：—
- 被取代：—
- 关联：—

## 背景

Context and constraints.

## 决策

Decision and relevant alternatives.

## 后果

Consequences and compatibility or migration implications.
```

Use links in `取代` / `被取代` when applicable. For an existing ADR, preserve its history and follow the spec change checklist; do not silently rewrite a superseded decision. The repository's mandatory ADR triggers take precedence over the optional heuristic in `SKILL.md`.
