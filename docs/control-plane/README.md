# 控制面（control-plane）

平台的浏览器后端与业务状态管理服务。组织测试资产、AI 生成任务、人工审核与导入、执行调度、权限、外部集成凭据与报告，并向浏览器提供 `/v1/*`、向 Worker 提供 `/internal/*`。

这是 Go 控制面的 Python 重写版本，保留原 `/v1` 与 `/internal/*` 契约。领域术语见 [CONTEXT](CONTEXT.md)。

[通用后端规则](../agents/backend-development.md)适用于四个后端项目；[控制面开发规则](development-rules.md)补充本项目的 Web、权限、数据库和事务验证入口。新增开发和相关修改同时按两份规则执行。

独立集成 Worker 拆分已开始，方案见[拆分计划](integration-worker-split-plan.md)，代码交付与未完成接入见[实施记录](integration-worker-implementation.md)。控制面异步协议、独立 Worker 和 Studio 任务交互已接入并完成隔离专项验证；恢复账本、切换及真实外部验收仍在推进。默认开关关闭，未启用项目继续使用原入口。

[需求维度测试设计接口](requirement-design.md)

## 运行时与依赖

- Python 3.12（`.python-version`），包管理使用 uv（`uv.lock`）
- FastAPI + uvicorn、SQLAlchemy 2 async + Alembic、MySQL（`asyncmy`）、Pydantic v2
- 认证与授权：PyJWT、bcrypt、PyCasbin；报告输出使用 reportlab
- 开发依赖在 `[project.optional-dependencies] dev`，需要 `--extra dev` 才会装入

## 源码结构

`apps/control-plane/src/testing_agent/`：

| 路径 | 作用 |
| --- | --- |
| `main.py` | 启动入口，调用 uvicorn 加载 `app.py` 的工厂函数 |
| `app.py` | 应用装配、异常处理、OpenAPI 契约改写 |
| `routers/` | 27 个路由模块，全部由 `app.py` 挂载 |
| `handlers/` | 薄 HTTP 处理层，被 router 调用 |
| `services/`、`services/ai_execution/` | 业务服务与 AI 任务编排 |
| `repositories/` | 数据访问 |
| `models/`、`schemas/` | ORM 模型与请求/响应模型 |
| `core/` | `config.py`、`security.py`、`enums.py`、`errors.py`、`sid.py` |
| `db/`、`domain/` | 会话与基础层、领域值对象 |

调用层次为 router → handler → service → repository → model。注意 `api/` 目录下只有依赖注入与鉴权校验（`deps.py`），业务路由不在此处。

生成任务保留 `services/ai_generate_task.py` 作为调用入口，内部实现按职责划分：

| 模块 | 职责 |
| --- | --- |
| `ai_task_contracts.py`、`ai_task_output.py` | 阶段常量、产物解析、快照与响应序列化 |
| `ai_source_archive.py` | 源码归档校验、替换与失败清理 |
| `ai_stage_workflow.py` | 阶段保存、审核、修订、重试和图谱派发 |
| `ai_report.py` | 测试报告任务、运行与 PDF 导出 |
| `api_generate_import.py` | API 候选冲突预览、确认覆盖及事务 |
| `api_import_payload.py`、`api_import_entities.py` | 文件/候选导入共用的校验、转换和实体构造；不提交事务 |
| `ai_task_access.py` | 各工作流依赖的最小授权接口，不依赖入口服务实现 |

功能与 UI 正式资产导入继续由 `function_generate_import.py`、`ui_generate_import.py` 处理。审核只改变审核状态，正式资产由独立导入入口创建；不再保留旧的审核即导入路径。通用需求访问链集中在 `project_access.require_requirement_access`，每次调用仍显式传递操作人及权限动作。

## 数据库读取与历史列表

表与字段的业务说明使用 MySQL 原生 `COMMENT`，在 SQLAlchemy 模型中随结构定义维护。迁移 `20261007_0034` 补齐既有表和字段注释；库的用途、查询方法及后续维护约定见[数据库结构描述](database-schema.md)。

迭代列表 `GET /v1/projects/{project_id}/sprints` 同批返回每个迭代的 `zentaoBinding` 摘要（未绑定为 `null`）。需求列表使用 `GET /v1/projects/{project_id}/requirements`，支持可选 `sprintId` 筛选及 `page` / `pageSize` 分页（默认 1 / 20，最大每页 100 条），按创建时间和数据库 ID 倒序返回 `items` 与筛选后的 `total`。每项包含 `sprintName`、文档元数据和 `zentaoBinding`，不查询或返回 `documentContent`。两类列表都在项目读取授权后批量查询本地禅道绑定，不访问外部服务；单条需求详情与绑定管理接口保留原有契约。`test_project_list_queries.py` 验证分页、权限隔离、大字段排除和固定的绑定批量查询数。

AI 任务与资源绑定的普通读取不使用 `FOR UPDATE`；修改时通过明确的 `get_*_for_update` 查询锁定父资源和运行，避免与删除或导入并发。代码风险运行在准备 GitLab 快照时不持有这些写锁，落库前重新检查父资源、任务归属和执行权限。Worker 领取及写回、覆盖导入和删除仍保留原有锁保护。

六类 AI 运行历史 HTTP 接口返回分页摘要：`page` 从 1 开始，`pageSize` 默认 20、最大 100，按创建时间和数据库 ID 倒序。响应包含 `items`、匹配条件的 `total`、`statusCounts` 和任务范围内的 `latestRun`。摘要保留阶段、审核、导入、错误和时间信息，使用 `availableArtifacts` / `hasResult` 表示产物是否存在，不返回 `snapshotJson`、`configJson`、`resultYaml` 或解析后的报告。完整内容仍从单次运行详情接口读取。功能用例运行支持 `pipelineFilter`，先在数据库筛选，再分页；`latestRun` 不受筛选或页码影响。

`repositories/ai_run_history.py` 只查询本页及最新运行的轻量记录，不把大字段加载到 ORM；`repositories/latest.py` 通过窗口函数按创建时间、ID 筛选每个资源最近一次运行。代码风险快照批量读取功能/API/UI 用例、API 断言及最近执行摘要，每日统计只读取最新状态与计数，不传输执行日志、请求快照或全部历史。

迁移 `20261004_0025` 增加 AI 任务列表、AI 运行历史、共享绑定、Bug 列表以及 API/UI 最近运行的七个联合索引，保留既有唯一约束与外键索引。空库初始化及升级、回退由 `test_initial_schema_migration.py` 验证；`test_database_read_paths.py` 覆盖权限、分页、大字段排除、相同创建时间的 ID 排序，以及 1 / 100 条用例下固定的批量查询数。

## 配置

启动时按 `--config/-c` 参数、`APP_CONF` 环境变量、`config/local.toml` 的顺序确定配置文件路径。本地独立启动由 `scripts/manage.py` 生成 `config/local.toml` 并注入 `APP_CONF`；容器内为 `/app/config/local.toml`。

顶层配置段：

```toml
env = "local"                     # local 时开启 uvicorn reload
[http]                            # host、port
[security.jwt]                    # key、expire_hours
[security.integration]            # key，用于集成凭据加解密
[security.worker]                 # key，Worker 调用内部接口的令牌
[data.db.user]                    # driver、dsn
[storage]                         # uploads_dir
[integrations.zentao_service]     # base_url
[code_overview]                   # cache_ttl_seconds
```

## 命令

在 `apps/control-plane/` 下执行：

```sh
uv sync --locked --extra dev                      # 安装依赖（含开发依赖）
uv run mtx-control-plane                          # 启动
uv run --locked --extra dev python scripts/check.py  # 静态检查和完整测试
uv run --locked --extra dev python scripts/check.py --static-only  # 仅静态检查
uv run --extra dev alembic upgrade head           # 数据库迁移
```

也可在仓库根目录用 `python3 scripts/manage.py run control-plane` 和 `python3 scripts/manage.py migrate`，由统一配置生成 `config/local.toml`。

`sql/` 存放一次性的数据订正脚本，需人工对着目标库执行，默认干跑、执行前自动备份受影响行。已有的脚本见下表。

| 脚本 | 用途 |
| --- | --- |
| `backfill_function_case_ids.sql` | 给历史功能用例候选结果补 `case_id`（审核页编号与导入沿用的编号） |

## 对外接口

默认监听 9000（Dockerfile `EXPOSE 9000`）。注意代码内兜底常量是 8000，与示例配置和镜像不一致。

- `GET /v1/health`：健康检查
- `/v1/*` 业务接口：24 个路由模块挂在 `/v1` 前缀下，覆盖登录注册、项目与成员、迭代、需求、功能/API/UI 测试资产与运行、各类 AI 任务、禅道与 GitLab 与 LLM 集成、共享服务、资源绑定与项目技能
- `/internal/ai-worker/*`、`/internal/ui-worker/*`、`/internal/api-worker/*`：3 个 Worker 面路由模块
- `GET /swagger/index.html` 返回 `{"url": "/docs"}`，兼容原 Go 契约

## 鉴权

- 浏览器请求使用 `Authorization: Bearer <JWT>`，HS256，载荷键为 `userId` 和令牌版本 `ver`；账号状态、改密、禁用、登录锁定、超级管理员与删除规则详见 [认证、账号与系统管理员](authentication.md)。
- 认证、会话、项目策略和执行授权的职责、权限矩阵与回归入口见 [认证与权限模块](auth-permission-modules.md)。
- 2026-10-20 的全项目检查见 [结构与质量排查记录](control-plane-audit-2026-10-20.md)；后续批次与验收标准见 [模块整改方案](control-plane-remediation-plan.md)。
- Worker 请求使用 `X-Worker-Token` 头，值等于 `security.worker.key`

## 外部调用

- 禅道：通过项目保存的 MCP 端点访问，实际实例由 MCP 提供；只使用操作人本人的 Token
- GitLab：直连 `/api/v4/*`，使用操作人的个人访问令牌
- LLM：按任务向 AI Worker 下发 `/internal/ai-worker/tasks/{id}/llm-credentials`

## 迭代每日统计

功能/API/UI 执行指标和缺陷指标均从平台本地记录统计，不依赖禅道个人授权。手动更新仍受项目写入权限控制；历史快照中缺陷未采集的空值保留原有显示语义。

Control Plane 启动时注册每日统计任务，每分钟检查一次，在北京时间（Asia/Shanghai）23:55 后采集当天快照，只处理开始时间已到、结束时间未到的迭代。未开始和已完成的迭代不自动更新，仍可手动刷新。多个服务实例通过迭代行锁串行化写入，以当天快照更新时间避免重复采集；当天 23:55 前的手动快照会在定时时点重新统计。

单个迭代失败不影响其他迭代，当天午夜前下一轮重试。服务在 23:55～24:00 启动时会补跑当天任务；错过整段时间不以当前数据补造历史快照。部署后需重启 Control Plane 才会加载任务。回归覆盖 `test_sprint_metrics_scheduler.py` 和 `test_sprint_daily_metrics_service.py`。

## 测试

在 `apps/control-plane/` 执行 `uv run --locked --extra dev python scripts/check.py`，
依次检查 Ruff、格式、全源码类型和完整测试。可通过 `--tests tests/<file>.py`
选择关联回归，或 `--static-only` 仅执行静态检查。共享测试准备代码逐步集中到
`tests/support/`，新增共享夹具不放在 `test_*.py` 中供其他模块导入。
当前整改的实际测试数量、失败修复和真实 MySQL 结果见[实施记录](remediation-implementation.md)，
模拟测试不替代真实 MySQL、S3 或外部目录验收。

- [内置 MCP 配置](builtin-mcp.md)
- [Bug 生命周期对齐禅道](adr/0005-bug-zentao-lifecycle.md)：三个主状态、独立确认及解决方案、旧数据迁移。
- [Bug 手动推送到禅道](bug-zentao-push.md)
- [禅道 Bug 同步到平台：需求草案](bug-zentao-reverse-sync-requirements.md)：已关联 Bug 的反向更新与禅道新建 Bug 导入。

- [统一 S3 文件存储与迁移](file-storage.md)

- [Skill 文件夹与默认技能维护](../control-plane/skills.md)

- [用例推送到禅道 MCP](zentao-mcp-case-push.md)：推送规则、部分失败和连接器退出。

## 文件存储验收与恢复

- [联合备份、恢复与部署门槛](storage-operations.md)
- [2026-10-03 S3 P1 验收记录](s3-p1-acceptance-2026-10-03.md)

- [ZenTao-MCP 手动部署](zentao-mcp-deployment.md)：已发布镜像、配置示例、直接 Compose 启动、多项目端口和网络排查。

需求分析的阶段审核及拒绝后的只读规则见 [需求分析审核规则](requirement-analysis-review.md)。

需求在线图文编辑与正文文件契约见[需求富文本正文](requirement-rich-text.md)。

- [LDAP 统一认证配置、切换与目录验收](ldap-authentication.md)。

- [LDAP 实施与验证记录](ldap-implementation-verification.md)。
