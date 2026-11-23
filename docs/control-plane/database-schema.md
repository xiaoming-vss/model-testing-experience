# 数据库结构描述

控制面数据库保存项目、迭代、需求、正式测试资产、AI 候选及审核记录、测试执行结果、个人授权、文件元数据、Bug 处理历史、账号登录限流记录和独立集成执行账本。

MySQL 8.4 没有库级 `COMMENT` 属性，库的用途在本文说明；表和字段的业务含义使用原生 `COMMENT` 保存。注释由 `src/testing_agent/models/` 内的 SQLAlchemy `__table_args__["comment"]` 和 `mapped_column(comment=...)` 定义，可被数据库管理工具及 `information_schema` 读取。

在数据库连接中查询：

```sql
SELECT TABLE_NAME, TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;

SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

## 预发布阶段单一基线

`Base.metadata` 是唯一结构来源，`alembic/versions/20261103_0001_v1_baseline.py` 是当前唯一迁移，创建全部业务表和 `alembic_version`。第一版正式发布前，表、字段、约束、索引、默认值和注释变更直接修改该 baseline 并同步模型，不新增 update 迁移；迁移链始终保持单一 revision。v1 只支持空库初始化：`alembic upgrade head` 建立完整结构，downgrade 仅用于空库测试往返，按依赖逆序删除全部表。

第一版正式发布时冻结 baseline；发布之后的结构变更才改为新增迁移，不能改写已发布的基线。新增表或字段时，在模型定义旁填写业务含义，并随结构变更一起落库；说明应包含必要的单位、状态值、标识归属、快照用途和历史兼容约定，个人凭据的说明必须与实际存储方式一致。`description` 等业务列保存业务内容，其列注释解释该列本身的用途。

`tests/test_initial_schema_migration.py` 验证预发布阶段只有唯一 baseline，以及空库升级、降级与再次升级；`tests/test_schema_comments.py` 验证模型注释完整性及真实 MySQL 注释与模型一致；`tests/test_mysql_initialization.py` 在明确指定的空、可丢弃测试库（库名必须以 `_test` 结尾）验证 MySQL 初始化和结构与模型一致。SQLite 不支持持久化表和字段注释，结构断言只覆盖表和字段。

本地开发库 `testing-agent-control-plane-b` 是唯一保留数据的例外：确认结构与当前 baseline 零差异且行数不变后，使用一次性 `alembic stamp --purge 20261103_0001` 写入版本号，不执行 DDL。旧 revision 已从代码库移除，原版本号无法直接 `alembic upgrade head`；也可以重建空库后重新初始化。详见[部署说明](../deployment.md#本地已有库的一次性-stamp)。

## LDAP 身份与认证切换

- `users.auth_source`：`local` / `ldap`，本地账号为 `local`；`external_id` 为可空的规范 UUID 文本，本地账号使用 NULL。两列组合唯一，阻止同一目录身份关联多个账号。`status` 包含 `pending_ldap`，普通业务鉴权仅允许 `active`。
- `login_rate_limits.auth_method`：`local` / `ldap`；唯一键为认证方式、用户名与 IP，防止 LDAP 同名失败锁住管理员本地入口。
- `auth_runtime` 是主键为 1 的单例。`mode`、`fingerprint`、`generation` 记录已完成的认证配置切换；`changed_at` 为切换时间；`reconcile_owner`、`reconcile_until` 协调对账租约。配置摘要不公开给浏览器，不替代配置源。

账号状态转换与会话撤销由显式切换事务执行，不由迁移或每次启动重复执行。写事务按运行状态行、用户行的顺序加锁，目录网络调用不持有用户写锁。恢复、回退及部署步骤见 [LDAP 统一认证](ldap-authentication.md)。

## UI 环境变量

- `api_environments.kind`：`api` / `ui` / `perf`，默认 `api`；唯一约束为 `(project_id, kind, name)`，不同类环境可以同名。性能运行要求所选环境 `kind="perf"`。
- `api_environment_vars.var_key`：MySQL 下使用 `utf8mb4_bin`，变量引用区分大小写；唯一索引为 `(environment_id, var_key)`。
- `ui_test_case_runs`、`ui_test_suite_runs`：包含 `environment_id`、`environment_name`（名称快照）、`used_variables_json`、`variable_writes_json` 与加密的 `private_payload`。

表名保留 `api_` 前缀，因为改名会牵动 API 自动化的全部代码。运行协议与隐私规则见 [UI 环境变量与后置提取](ui-environment-variables.md)。

## API/UI 测试集归属与运行快照

- `api_collections`、`ui_test_suites`：项目级测试资产。`project_id` 非空并决定权限、生命周期和名称唯一性，唯一约束为 `(project_id, name)`；`requirement_id` 可空，只表示来源需求或可选关联，外键 `ON DELETE SET NULL`。接收过正式生成导入的测试集以非空 `effective_import_id` 标记，不允许清空或更换需求；手工测试集可以自由关联和解除。需求删除时测试集自动转为项目级，项目删除前必须先删除测试集。
- `api_collection_runs`、`api_case_runs`、`ui_test_suite_runs`、`ui_test_case_runs`：运行创建时冻结 `project_id`、可空 `requirement_id`、`requirement_name`、可空 `sprint_id`、`sprint_name` 和 `trigger_type`。权限校验、历史展示和按迭代筛选使用冻结值，不从测试集当前关联推导；未关联需求的项目级运行可以不记录需求和迭代。索引覆盖 `(project_id, sprint_id, created_at)`，供项目级运行记录筛选。

结构决策与备选方案见 [ADR 0027](adr/0027-project-owned-api-ui-test-suites.md)。

## 性能测试

性能资产和执行账本与功能执行分开：

- `perf_suites`：项目级性能测试集，保存名称和描述。`(project_id, name)` 唯一。
- `perf_cases`：测试集内的性能用例，保存 YAML 正文、版本、测试集内顺序 `order_no` 和当前数据文件元数据 `data_files_json`。`(project_id, name)` 唯一；`suite_id` 可空以兼容尚未归入测试集的历史数据，归入测试集后按 `(suite_id, order_no)` 排序；更新正文时版本递增，运行冻结 `case_version` 与 `case_yaml`。
- `perf_suite_runs`：一次性能测试集运行的父记录。冻结测试集名称、环境、监控接入快照和 `total/completed/failed/skipped` 计数；状态与 `perf_runs` 一致，本期父运行 `outcome` 固定为 `inconclusive`，不合并子运行结果做验收判定。
- `perf_suite_run_items`：父运行中的有序用例条目，保存冻结用例名称、`order_no`、条目状态和 `child_run_id`。条目状态为 `pending/queued/running/completed/failed/stopped/canceled/skipped`。
- `perf_runs`：单条用例的子运行。冻结用例、环境、监控接入和数据文件；`monitoring_snapshot_json` 保存发起时的接入名称和 Remote Write 地址，不含凭据，接入后续修改或删除不影响历史运行；`spec_json` 是脱敏公开规格，`private_payload` 是加密的完整 RunSpec（含环境秘密和 Remote Write 写凭据），`summary_json`/`result_json`/`log_tail` 保存 Worker 回传事实。状态为 `queued/running/stopping/completed/failed/stopped/canceled`，`outcome` 为 `passed/threshold_failed/inconclusive/execution_error/stopped`。索引覆盖用例最近运行、项目最近运行和按状态回收。
- `monitoring_connections`：项目级 Prometheus Remote Write 接入，保存写入地址、认证类型、加密的写入凭据和启用状态。`(project_id, name)` 唯一；响应只暴露认证类型和“是否已配置凭据”。本期不保存查询地址、查询凭据或外部看板配置。
- `stored_files` 新增代码级用途 `perf_case_data`，对象目录 `perf-case-data`，只允许 CSV/JSON，单文件上限 50 MiB。文件正文只存在 S3；`perf_runs.data_files_json` 与 `perf_cases.data_files_json` 只保存 `fileId/filename/size/sha256`。
- `worker_tasks.domain` 扩展 `perf`；子运行使用 `task_type="perf_run"` 和 60 秒租约。通用状态列仍为 `pending/claimed/running/stopping/success/failed/canceled`。

测试集运行时，控制面在同一事务中预创建所有用例的子 `perf_runs`、父 `perf_suite_runs` 和有序条目，但只给第一条子运行写入 `worker_tasks`。子运行完成后在同一/后续事务中推进下一条，失败继续，用户停止则跳过剩余条目。父运行推进有租约扫描兜底，避免完成事件丢失导致长期挂起。停止只允许触发人操作；停止单条子运行会级联停止父测试集。Worker 结果映射、停止优先和终态幂等见 [ADR 0002](../perf-worker/adr/0002-control-plane-poll-mode.md)。项目删除前必须没有性能测试集和监控接入；删除测试集会级联删除用例、子运行、父运行和任务，并把当前及历史数据文件标记为 `deleting` 交给统一存储清理。

## 正式用例失效标记

- `function_test_cases`、`api_cases`、`ui_test_cases`、`perf_cases` 统一增加 `invalidated_at DATETIME NULL` 和同名索引：空值表示有效，非空表示已失效并保存首次失效时间；恢复有效只清空该列，重复失效不刷新首次时间。
- 该列是资产生命周期标记，不是 API/UI 的 `enabled` 执行开关，也不是软删除。失效用例仍属于原测试集或 Collection，并继续占用原有名称/标题唯一约束；`enabled` 原值和语义不变。
- 失效用例退出新的执行与 AI 分析，但不会被历史运行、运行快照、测试单执行条目、执行结果、历史统计或已冻结 AI 快照引用；删除资产仍按硬删除处理。结构决策见 [ADR 0026](adr/0026-case-invalidation-marker.md)。

## 接口库与软件仓库

- `software_repositories`：项目级软件仓库，保存名称、说明、仓库级 `base_path`、手工接口分组列表 `interface_groups_json` 和 `version`。Git 仓库以 `repository_project_id`、`repository_group_id`（所选群组来源快照）、`repository_instance_key`（匹配操作者同实例个人授权）、`repository_path`、`repository_name`、`repository_instance_url` 快照保存，创建与换绑均必选；`(project_id, name)` 唯一，删除前必须没有接口和需求关联。
- `api_interfaces`：接口定义，保存方法、规范化相对路径、`path_key`（路径 SHA-256）、请求头与 Path/Query 参数 JSON、请求体、单个默认成功响应、接口级 `security_json` 与文档级 `security_schemes_json`、标签、说明、版本和来源快照。接口身份由 `(software_repository_id, method, path_key)` 唯一约束确定，避免 utf8mb4 长路径索引限制；软件仓库外键为 `RESTRICT`。
- `api_interface_requirements`：接口与需求的关联表，接口外键和需求外键均 `CASCADE`，`(interface_id, requirement_id)` 唯一；迭代通过需求归属推导，不在关联表冗余保存。
- `requirement_software_repositories`：需求与软件仓库的多对多关联，保存需求级工作分支 `branch`、基线分支 `baseline_branch` 和关联人；`(requirement_id, software_repository_id)` 唯一，需求外键 `CASCADE`、软件仓库外键 `RESTRICT`。

接口删除为业务硬删除，使用统一的 `ResourceDeletion`；导入提交在单一事务内锁定软件仓库与接口行、校验来源摘要和逐项版本，并保留仅库中存在的接口。接口分组没有独立表：展示集合由 `software_repositories.interface_groups_json` 中手工创建的分组名与 `api_interfaces.tags_json` 的首个非空标签合并而成；手工分组允许为空，重命名、移除和移动同时维护分组列表与批量标签。软件仓库直接绑定 GitLab 仓库，群组仅作为个人连接下的选择范围与来源快照。结构决策见 [ADR 0013](adr/0013-software-repository-and-interface-library-api-generation.md)、[ADR 0015](adr/0015-software-repository-direct-gitlab-binding.md) 与 [ADR 0016](adr/0016-interface-library-tag-groups.md)。

## AI 执行、阶段尝试与历史

统一 AI 执行模型使用以下表：

- `ai_generate_tasks`：任务定义、归属、创建者和来源配置。
- `ai_executions`：一次用户或系统发起的执行身份、发起者和创建时间；独立多阶段执行另存聚合状态、当前阶段、检查点、初始快照和起止时间。
- `ai_generation_stages`：任务的稳定阶段，保存当前尝试和活动尝试；输入来源由候选内容的快照保存，不保存业务版本计数。
- `ai_generation_attempts`：阶段内的生成、修订或人工编辑尝试，保存冻结输入、输出、错误和可选执行关联；人工编辑可以没有 Worker 队列。
- `ai_generate_imports` 和 `ai_generate_import_requests`：正式资产导入的自包含来源回执及幂等请求，不依赖生成任务或尝试继续存在。

预发布单基线包含 `requirement_generation_chains`、`ai_generation_candidates`、`ai_generation_stage_contents` 和 `ai_generation_review_receipts`，用于多候选和唯一当前内容。候选以 `(stage_id, origin_attempt_id)` 防止同一尝试重复入池，当前内容以阶段及 `(chain_id, stage)` 保证唯一，并保留空槽令牌；`source_candidate_id` 是阶段本地采用指针，采用和导入只校验该内容自身的冻结来源闭包，不要求上游阶段当前指针一致。材料、功能、API、UI 和画像候选的公开读取、派发、采用及清空入口已接入。

`ai_generate_import_requests` 和 `ai_generate_imports` 是新导入方案的请求幂等记录及自包含目标回执。回执保存导入正文、所选上游产物、来源身份和摘要，不依赖来源候选、尝试或旧版本的外键；每个请求和正式目标的组合最多一条回执。来源审计快照不复制运行凭据、签名地址或原始提示词，但完整上游产物和导入正文仍属于项目业务数据，必须按项目权限保护。独立任务导入及其历史读取使用新回执。用户已确认不迁移旧生成历史，正式功能、API 和 UI 测试用例必须保留；本轮不连接或修改业务数据库。详情见[阶段记录](records/2026-11-20-generation-candidate-foundation.md)。

阶段尝试不保存 `progress_json` 或 `remediation`；阶段不保存可推导的执行状态和审核副本。公开 AI 接口的 `runId` 是执行 ID，AI Worker 队列和回传的标识是 `attemptId`。执行身份与阶段模型的完整决策见 [ADR 0010](adr/0010-unified-ai-execution.md)，历史删除规则见[生成链文档](generation-chain.md#历史与删除)。
