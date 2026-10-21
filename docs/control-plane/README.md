# 控制面（control-plane）

平台的浏览器后端与业务状态管理服务。组织测试资产、AI 生成任务、人工审核与导入、执行调度、权限、外部集成凭据与报告，并向浏览器提供 `/v1/*`、向 Worker 提供 `/internal/*`。

这是 Go 控制面的 Python 重写版本，保留原 `/v1` 与 `/internal/*` 契约。领域术语见 [CONTEXT](CONTEXT.md)。

[通用后端规则](../agents/backend-development.md)适用于四个后端项目；[控制面开发规则](development-rules.md)补充本项目的 Web、权限、数据库和事务验证入口。新增开发和相关修改同时按两份规则执行。

集成远端写入由独立 integration-worker 执行，控制面保留授权、写入意图、账本与结果事务。
未启用的范围不能回退到旧同步写入口；未知写入不能自动重发。约束以
[ADR 0006](adr/0006-independent-integration-execution.md) 为准，交付与外部验收记录见
[实施记录](integration-worker-implementation.md)。

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
| `routers/` | 路由注册，由 `app.py` 挂载 |
| `handlers/` | 薄 HTTP 处理层，被 router 调用 |
| `services/` | 业务服务；AI 执行、Worker 分域处理、Bug 导入分别组织为子包 |
| `repositories/` | 数据访问 |
| `models/`、`schemas/` | ORM 模型与请求/响应模型 |
| `core/` | `config.py`、`security.py`、`enums.py`、`errors.py`、`sid.py` |
| `db/`、`domain/` | 会话与基础层、领域值对象 |

调用层次为 router → handler → service → repository → model。注意 `api/` 目录下只有依赖注入与鉴权校验（`deps.py`），业务路由不在此处。

AI 生成任务按能力装配，HTTP handler 直接获取所需的查询、管理或工作流对象。
旧的 `services/ai_generate_task.py` 与 `get_ai_generate_task_service` 已移除，不再维护总入口的
转发方法或常量/序列化函数重导出。下表中的模块默认位于 `services/`，装配入口位于 `api/deps.py`。

| 模块与公共能力 | 职责 |
| --- | --- |
| `ai_task_scope.py` / GenerationAccess | 当前成员动作、任务/运行归属、父资源先于子资源的锁顺序；不提交事务 |
| `ai_task_queries.py` / GenerationQueries | 任务列表/详情、运行详情与分页历史；代码风险详情保留 report，历史摘要不读取正文 |
| `ai_task_commands.py` / GenerationTaskCommands | 任务创建、修改、删除与运行删除；业务命令保留各自提交点 |
| `ai_run_launcher.py` / GenerationRunLauncher | 准备快照、重查权限、发起运行；使用显式 ExecutionWriter |
| `ai_stage_workflow.py` / GenerationStageWorkflow | 阶段保存、审核、修订、重试和图谱派发 |
| `ai_candidate_review.py` / GenerationCandidateReview | 整次候选运行的内容编辑与审核，不创建正式资产 |
| `ai_report.py` / TestReportWorkflow | 报告任务、运行及 PDF 导出 |
| `ai_source_archive.py` / SourceArchiveManager | 源码归档校验、替换和失败清理 |
| `api_generate_import.py` / ApiCandidateImporter | API 候选冲突预览、确认覆盖及正式资产事务 |
| `function_generate_import.py`、`ui_generate_import.py`、`requirement_generate_import.py` | 功能/UI 候选正式导入、需求增强文本采纳；各入口负责原有提交与回滚语义 |
| `ai_task_access.py` / GenerationImportContext | 仅向正式导入提供仓储、执行写入器、运行访问与需求权限能力；不承担任务管理 |
| `domain/ai_tasks.py`、`ai_task_output.py` | 纯任务规则与常量、产物解析及快照/响应序列化；调用方直接引用实际归属 |
| `ai_execution/writer.py` | 协调 run、stage、attempt、queue 的显式写入；flush，不提交调用者事务 |

工作流通过明确的构造参数获取依赖。`RequirementDesignService` 显式接收工作区查询仓储、
任务仓储、归档仓储、访问检查、任务管理和运行启动能力；装配时共享同一请求会话，
保持关闭旧授权快照、项目→迭代→需求加锁、重查当前权限和业务入口提交的顺序。
审核与正式导入继续独立，旧 attempt、本人模型授权和响应丢失后的幂等规则不变。

功能用例的本地操作与外部导出也有独立入口：

| 模块 | 职责与约束 |
| --- | --- |
| `function_test_case.py` / FunctionTestCaseService | 本地查询、创建、编辑、删除；不装配禅道客户端 |
| `function_case_import.py` / FunctionCaseImporter | 文件读取后的内容验证与本地导入；完整处理后一次提交，异常请求会话撤销未提交数据 |
| `function_case_export.py` / FunctionCaseExporter | 本人授权、目标核验、预览及结果汇总；结束只读事务后委托写入工作流 |
| `function_case_push_flow.py` / FunctionCasePushFlow | 冻结批次、当前权限与目标复查、意图提交、一次远端写入及回执事务；拥有提交责任 |
| `function_case_push_journal.py` / CasePushJournal | 稳定映射、一次许可和安全回执；不隐式提交或回滚调用者事务 |
| `zentao_case_gateway.py` | 请求内目录复用、明确编号的远端读写及内容核对；不按标题决定更新，不重试写入 |
| `function_case_access.py` / FunctionCaseAccess | 共用资源归属与项目动作检查；本地读写和导出仍使用各自要求的动作 |
| `domain/function_case_export.py` | 普通值对象到禅道载荷的纯转换；保留结构化多行步骤、旧文本、优先级与步骤/预期补齐 |
| `import_payload.py` | 功能/API/UI 等资产导入共用的文件读取与 YAML/JSON 信封解析，不依赖 API 集合业务模块 |

API 导入的专用校验与实体转换继续由 `api_import_payload.py` 和 `api_import_entities.py` 负责。
远端导出的部分成功保留逐项结果，本地事务失败不代表撤销了远端操作。

## 模块接口与事务责任

以下路径相对 `src/testing_agent/`。保留同一控制面部署和业务数据库，模块划分不增加远程调用。

| 职责与公共入口 | 隐藏的实现及调用约束 |
| --- | --- |
| `services/auth_session.py` 的 SessionService、本地/LDAP 登录模块 | 验证当前账号和会话；项目授权仍使用 `project_access` 与 `domain/project_policy.py`，资源归属不能由角色替代 |
| `services/ai_execution/writer.py` 的 ExecutionWriter | 显式接收 ExecutionIntent；查询投影在 `repositories/ai_execution.py`，普通 repository.commit 不推进执行状态 |
| `repositories/worker_task.py` 的 execution_context | 返回 `domain/worker_context.py` 的明确上下文；不向 WorkerTask ORM 临时附加业务字段 |
| `services/worker_task.py` 的 ai_worker_task | 查找任务并检查当前执行授权；文档、源码包及技能入口复用它，调用方仍检查所需租约/资源条件 |
| `services/worker_domains/` | AI、API、UI 各自维护快照和结果规则；公共协调层管理领取、租约与事件身份，集成写入使用独立协议 |
| `services/personal_credentials.py` 的 PersonalCredentialAccess | 先检查本人归属、供应方、范围和状态，再解密；供应方查询与绑定不依赖连接管理的私有方法 |
| `services/bug_import/` | 远端读取、准备、本地写入和文件处理分开；事务提交由导入编排负责，提交后的附件失败不回滚已创建 Bug |
| `file_verification.py` | 核验代次领取、事务外复制和当前权限/CAS 发布；持久保留未知对象回收依据 |
| `skill_storage.py` / SkillPublisher | 项目上传、默认同步、旧路径迁移共用批次发布；复制目标独占、清单原子切换 |
| `stored_file_cleanup.py` | 有界领取与清理租约，事务外删除，按代次及对象键记录结果；关联仍归原业务事务 |
| `services/resource_deletion.py` 的 ResourceDeletion | 删除前业务检查与生命周期协调；`repositories/deletion.py` 只负责锁定和关联清理；最终提交由调用者负责 |
| `services/integration_bug_state.py` 的 IntegrationBugState | 本地证据应用与状态投影；恢复记录通过显式能力传入，生命周期不反向依赖完整步骤执行器 |

新增业务命令必须明确提交者。可复用写入辅助方法不能隐式提交；远端成功不能由本地回滚撤销。
修改执行与删除时继续覆盖旧回传、未知写入、授权撤销及并发保护，不用统一重试掩盖各域差异。

`tests/test_architecture_layers.py` 检查层次依赖、源码静态导入无环、跨模块私有调用、
禁止 ORM 命令临时字段、查询模块写事务、重新引入 AI 总入口，以及测试准备不导入被收集的测试模块。
这些静态约束不能证明动态依赖和业务行为正确，仍需对应行为测试。

## HTTP 诊断

`core/http_diagnostics.py` 在入口校验单个规范 UUID 格式的 `X-Request-ID`，不合法或重复时
重新生成，并通过响应头、request.state 和 ContextVar 传递同一标识；请求结束后重置上下文。
日志使用 `testing_agent.http`，只记录方法、路由模板、HTTP 状态、已知业务错误码及耗时。
未知异常记录异常类型与模块/函数/行号，省略消息、源码、局部变量和请求内容。
异常链最多记录 8 项、每项最多 40 帧，避免错误输出无界增长。

未开始响应的未知异常返回既有 500 信封，不把原异常交给服务器重复打印。
已开始的流式响应无法替换为 500，记录安全异常后以脱敏的中止异常结束；
日志中的状态保留已发送状态，不能据此认为流式输出成功完成。
成功的 Worker 领取/心跳摘要使用 DEBUG，其余正常请求摘要使用 INFO，未知异常使用 ERROR。
官方 `mtx-control-plane` 启动入口关闭 Uvicorn 默认 access log，并配置该命名 logger；
自行直接启动 Uvicorn 时也应采用等价配置，以免另行记录原始路径和查询。

诊断契约由 `test_http_diagnostics.py` 验证，包括上下文并发隔离、隐私、错误信封、
流式失败以及启动日志配置。完整整改状态见[实施记录](remediation-implementation.md)。

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
选择关联回归，或 `--static-only` 仅执行静态检查。共享测试准备代码集中到
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

## 资产文件导入资源预算

功能/API/UI 文件导入共用 `services/import_budget.py`。预算来自
`config/platform.example.toml` 的 `[control_plane.asset_import]`，经
`scripts/manage.py` 生成控制面配置。默认内容上限 8 MiB、列表条数上限 10000、
单字段 262144 字符、深度 32、节点数 200000，每进程最多同时处理 2 个导入。
这不是整个集群的配额；扩容时需要把进程数计入总资源预算。

三个文件导入 HTTP 入口在 FastAPI 解析 multipart 前限制请求总量，额外允许
64 KiB 封装开销，上传读取最长 60 秒。超过内容或结构预算返回 413，并发饱和返回
429，上传超时返回 408。文件按实际读取字节核验，不依赖 Content-Length 或文件元数据。
非法编码、YAML/JSON 语法或 YAML 别名返回 400；别名需先展开成普通内容。
直接传入的导入对象也会检查结构、字段长度和内容预算。

解析在线程执行，取消请求不会提前释放仍在解析的并发名额。初次访问校验后结束只读
事务，解析完成后重新检查目标与访问权限，再执行原子写入。功能用例导入先验证整批
数据再加入 session，非对象条目和非法顺序值明确报错，不再静默略过或返回 500。
其他 AI 产物的内部同步解析入口没有在此变更中套用文件导入预算。
