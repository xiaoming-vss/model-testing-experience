# Repository instructions

This monorepo contains five independently runnable projects under apps/: studio, control-plane, ai-worker, api-ui-worker and connector-zentao. Preserve each project's dependency files, lockfile, Dockerfile and startup entry point. Read the target project's AGENTS.md, then use [CONTEXT-MAP.md](CONTEXT-MAP.md) to find its context and relevant ADRs before business-code changes. All substantive documentation lives under docs/<project>/; app READMEs are navigation and startup entry points.

Deployment source of truth: config/platform.example.toml plus local ignored config/platform.toml. Generate runtime configuration through scripts/manage.py. Do not commit secrets, generated configuration, databases, worker runtime state or dependency directories.

For orchestration changes run `python3 -m unittest discover -s tests -v` and `python3 scripts/manage.py compose config --quiet` after initializing local configuration. Run relevant child-project checks for changes within a project.

Shared development conventions: [domain docs](docs/agents/domain.md), [issue tracker](docs/agents/issue-tracker.md), [triage labels](docs/agents/triage-labels.md). New issue files live under the repository-root .scratch/ directory.
