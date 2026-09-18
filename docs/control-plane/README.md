# mtx-control-plane

> 文档统一维护于此；以下项目命令在仓库根目录的 `apps/control-plane/` 中执行。整套平台的配置与部署见 [统一部署指南](../deployment.md)。

Model Testing Experience（MTX）的 Python 控制面。

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
uv run mtx-control-plane --config config/local.toml
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
backfill. See [ADR-0006](adr/0006-fresh-database-baseline.md).

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

## 文档目录

- [测试智能体控制平面](CONTEXT.md)
- [GitLab 连接使用个人访问令牌](adr/0001-use-personal-gitlab-connections.md)
- [项目共享 GitLab 绑定模型](adr/0002-project-shared-gitlab-bindings.md)
- [数据库结构加固](adr/0003-schema-hardening.md)
- [命名对齐与代码工程化收敛](adr/0004-naming-alignment-and-code-convergence.md)
- [迭代状态由计划时间实时推导](adr/0005-derive-sprint-status-from-schedule.md)
- [仅支持新建数据库初始化](adr/0006-fresh-database-baseline.md)
- [项目成员与个人授权边界](adr/0007-project-membership-authorization.md)
- [共享服务配置与个人授权分离](adr/0008-shared-services-personal-authorization.md)
- [业务资源逐级硬删除](adr/0009-child-first-hard-deletion.md)
- [功能测试用例批量删除](api/function-case-batch-delete.md)
- [项目协作与个人授权接口](api/project-membership.md)
- [项目共享服务与个人授权](api/shared-services.md)
- [代码绑定与风险分析 — 需求总览](specs/code-binding-and-risk-analysis-overview.md)
- [模块需求:mtx-control-plane(控制面)](specs/code-binding-and-risk-analysis.md)
- [新增 UI 测试用例生成任务并解耦候选结果审核与导入](specs/ui-case-generate-and-import-workflow.md)
- [04 工单补充：以当前源码包作为 UI 用例生成来源](specs/ui-case-source-archive-addendum.md)
- [AI 生成运行存储与验证](verification/ai-generation-storage.md)
- [API 运行归属与验证](verification/api-run-scope.md)
- [功能用例正文与验证](verification/function-case-content.md)
- [硬删除落地验证（2026-09-17）](verification/hard-deletion-rollout.md)
- [项目成员与个人授权验收](verification/project-membership.md)
- [UI 运行归属与验证](verification/ui-run-scope.md)
- [Worker 队列存储与验证](verification/worker-queue-storage.md)
