# Repository instructions

This monorepo contains five independently runnable projects under apps/: studio, control-plane, ai-worker, api-ui-worker and integration-worker. Preserve each project's dependency files, lockfile, Dockerfile and startup entry point. Read the target project's AGENTS.md, then use [CONTEXT-MAP.md](CONTEXT-MAP.md) to find its context and relevant ADRs before business-code changes. All substantive documentation lives under docs/<project>/; app READMEs are navigation and startup entry points.

Deployment source of truth: config/platform.example.toml plus local ignored config/platform.toml. Generate runtime configuration through scripts/manage.py. Do not commit secrets, generated configuration, databases, worker runtime state or dependency directories.

For orchestration changes run `python3 -m unittest discover -s tests -v` and `python3 scripts/manage.py compose config --quiet` after initializing local configuration. Run relevant child-project checks for changes within a project.

Shared development conventions: [domain docs](docs/agents/domain.md), [issue tracker](docs/agents/issue-tracker.md), [triage labels](docs/agents/triage-labels.md). New issue files live under the repository-root .scratch/ directory.

Design prototypes are disposable working artifacts. Keep them out of app source directories; while options are still being compared keep them under the repository-root .scratch/ directory (ignored by git). Once an option is selected, delete the prototype files instead of archiving or committing them.

For backend development or review in control-plane, ai-worker, api-ui-worker or integration-worker, read and follow the [shared backend rules](docs/agents/backend-development.md) and the target project's linked development rules before editing code or protocols.
