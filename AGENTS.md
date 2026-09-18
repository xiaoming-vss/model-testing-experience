# Repository instructions

This monorepo contains five independently runnable projects under apps/: studio, control-plane, ai-worker, api-ui-worker and connector-zentao. Preserve each project's dependency files, lockfile, Dockerfile and startup entry point. Read the target project's AGENTS.md, CONTEXT.md and relevant ADRs before business-code changes.

Deployment source of truth: config/platform.example.toml plus local ignored config/platform.toml. Generate runtime configuration through scripts/manage.py. Do not commit secrets, generated configuration, databases, worker runtime state or dependency directories.

For orchestration changes run `python3 -m unittest discover -s tests -v` and `python3 scripts/manage.py compose config --quiet` after initializing local configuration. Run relevant child-project checks for changes within a project.
