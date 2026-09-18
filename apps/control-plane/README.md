# testing-agent-control-plane

Python control-plane rewrite for `testing-agent`.

## Scope

This project rewrites the Go backend control plane only. Worker executors stay outside this repository. The backend keeps the existing `/v1` and `/internal/*-worker` contracts so existing frontends and workers can keep talking to it.

## Stack

- Python 3.12
- uv
- FastAPI
- SQLAlchemy 2.x async ORM
- Alembic migrations
- Pydantic v2
- MySQL via asyncmy

## Local configuration

Create a local config from the example:

```powershell
Copy-Item config/local.example.toml config/local.toml
```

The example config points at:

```text
127.0.0.1:3306/testing-agent-python
user: root
password: password
```

## Commands

```powershell
uv sync --extra dev
uv run alembic upgrade head
uv run testing-agent-control-plane --config config/local.toml
uv run pytest
```

## Storage

Project skill files are stored under `storage/skills/`. The directory is kept in
the repository with `.gitkeep`; uploaded/generated skill archives should live
there at runtime.

## Database initialization

Deploy to an **empty MySQL database** using `uv run alembic upgrade head`.
The only initial revision is `20260915_0001`; it contains the complete current
baseline schema; later revisions add subsequent features. Fresh databases need no historical
backfill. See [ADR-0006](docs/adr/0006-fresh-database-baseline.md).

Only fresh database initialization is supported. Retired development databases
and historical connection conversion are not supported.

Database credentials come from the config selected by `APP_CONF` (default:
`config/local.toml`). Keep that file local. Future schema changes must add a
migration rather than modifying the frozen initial revision.

## Pre-push checks

```sh
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
git diff --check
```

For real MySQL initialization, rollback/re-initialization and uniqueness checks,
set `CONTROL_PLANE_TEST_DATABASE_URL` to an **empty disposable database** whose
name ends in `_test`, then run:

```sh
uv run pytest -q tests/test_mysql_initialization.py
```

These tests create and delete business tables in that database. The optional
MySQL queue concurrency test in `tests/test_worker_queue_storage.py` uses the
same explicit test URL and initializes its own disposable schema.

The MySQL test account also needs read access to `performance_schema` to verify
that concurrent group deletion actually waits for the binding transaction.
