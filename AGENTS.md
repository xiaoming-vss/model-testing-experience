# Repository instructions

> Status: active | Owner: repository maintainers | Last reviewed: 2026-11-21 | Review cadence: quarterly
>
> Change/deprecation: follow the [spec change checklist](docs/agents/domain.md#规范变更检查清单); record an ADR and notify consumers for cross-project contract changes.

This monorepo contains six independently runnable projects under apps/: studio, control-plane, ai-worker, api-ui-worker, integration-worker and perf-worker. Preserve each project's dependency files, lockfile, Dockerfile and startup entry point. Read the target project's AGENTS.md, then use [CONTEXT-MAP.md](CONTEXT-MAP.md) to find its context and relevant ADRs before business-code changes. All substantive documentation lives under docs/<project>/; app READMEs are navigation and startup entry points.

Deployment source of truth: config/platform.example.toml plus local ignored config/platform.toml. Generate runtime configuration through scripts/manage.py. Do not commit secrets, generated configuration, databases, worker runtime state or dependency directories.

For orchestration changes run the root and Compose checks in [docs/commands.md](docs/commands.md#根目录与部署编排) after initializing local configuration. Run the relevant child-project checks in [docs/commands.md](docs/commands.md) for changes within a project.

Control-plane database policy: before the first public release, keep exactly one editable Alembic baseline (`apps/control-plane/alembic/versions/20261103_0001_v1_baseline.py`) and edit it directly for schema changes; do not add update migrations. Freeze the baseline at first release, then add new revisions. See [database schema](docs/control-plane/database-schema.md) and [ADR 0014](docs/control-plane/adr/0014-pre-release-single-baseline.md).

Shared development conventions: [domain docs](docs/agents/domain.md), [issue tracker](docs/agents/issue-tracker.md), [triage labels](docs/agents/triage-labels.md). New issue files live under the repository-root .scratch/ directory. `.scratch/` is a local, gitignored working area; durable specs, acceptance evidence and historical design records belong under [docs/records](docs/records/README.md) or docs/<project>/records/, and must not be reachable only through `.scratch/`.

Change hygiene: when a change replaces behavior, remove the old code and logic in the same change — unused handlers, services, API clients, helpers, branches, tests, styles and live documentation. Do not leave dead code, compatibility shims or duplicate paths behind unless the user explicitly asks to keep them. Historical ADRs and records are evidence and are not deleted.

Design prototypes are disposable working artifacts. Keep them out of app source directories; while options are still being compared keep them under the repository-root .scratch/ directory (ignored by git). Once an option is selected, delete the prototype files instead of archiving or committing them.

For backend development or review in control-plane, ai-worker, api-ui-worker, integration-worker or perf-worker, read and follow the [shared backend rules](docs/agents/backend-development.md) and the target project's linked development rules before editing code or protocols.
