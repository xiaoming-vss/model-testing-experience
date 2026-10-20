# 控制面整改实施记录

本记录跟踪 [B0–B5 整改方案](control-plane-remediation-plan.md) 的实际进度。
目标为完成全部批次，不能以 B0 检查恢复替代完整模块整改。

## 基线

- 起点：`5fa733a`，`dev` 分支工作区干净。
- 实施分支：`codex/control-plane-remediation`。
- 复核发现：审计后的提交已修复正文漂移旧预期及部分格式问题；实际只剩两个文件格式未通过。
- 类型检查仍为 6 个文件中的 7 处错误；OpenAPI 的六处未建模字典仍违反现有约束。
- `4dfd73e` 单独修复两个测试文件的格式，检查通过。

## B0 已完成

已实现并通过本批验证：

- 修复 ORM 查询类型、Mixin session 声明、Worker 域模型联合类型和技能文件输入模型。
- S3 addressing style 显式限制为 auto/path/virtual，非法配置在创建客户端前拒绝。
- 禅道导入快照、转换结果和当前字段组使用命名 TypedDict，保持缺省空对象和未映射 null。
  历史基线的 local/remote 明确允许可扩展 JSON，不丢弃既有扩展字段。
- 增加预览序列化兼容测试、S3 配置验证，以及远端正文覆盖事实持久化检查。
- ZIP 参数化测试使用固定 ID。
- 项目 API 与 AI 执行的共享夹具迁入 `tests/support/`；其余测试支持迁移继续纳入 B5。
- 新检查入口：在本项目执行 `uv run --locked --extra dev python scripts/check.py`。
  可用 `--static-only` 只做静态检查，或 `--tests tests/<file>.py` 在检查后执行指定测试。

专项检查：55 项通过、1 项未选择；覆盖 OpenAPI、预览序列化、源码包和正文图片流程。
随后完整收集到 1,484 项测试，六组完整回归为 1,420 通过、64 项环境跳过、0 失败。
另在独立临时 MySQL 8.4 中顺序运行全部 55 项真实数据库检查，最终 55 项全部通过。
因此本批 1,484 项中有 1,475 项通过证据，剩余 9 项为未启用的真实存储验收；
数据库复验、专项复验和 6 个 subtest 不重复计数。
专用空测试库仅监听本机回环地址，此处不保存数据库凭据，也不连接已有业务库。

真实 MySQL 首轮发现两项授权用例在插入 User 时缺少列。
原因是迁移保护测试从最新版本降级，在触发预期拒绝前已执行不可回滚的 DDL；
简单 rollback 或随后升级 head 都不能保证版本记录与表结构一致。
测试现先定位至待验证的 0039 版本，验证守卫后恢复 head，整组复验通过。
没有修改已有迁移文件或放宽业务授权规则。

本批提交：

- `4dfd73e`：独立格式调整。
- `4e849dc`：查询/配置类型与兼容测试。
- `9ceb5a7`：项目 API、AI 执行共享夹具迁移。
- `3bea3d7`：预览契约、稳定测试 ID 与覆盖事实断言。
- `4e3c069`：真实 MySQL 迁移保护测试隔离。

最终静态入口 `uv run --locked --extra dev python scripts/check.py --static-only`
通过 Ruff、格式检查和 348 个源码文件的类型检查。
数据库测试命令为 `python -m pytest` 加以下入口，使用同一锁定环境与专用测试库：
`test_mysql_initialization.py`、`test_integration_jobs_mysql.py`、`test_ldap_mysql.py`、
`test_requirement_design_mysql.py`、`test_sprint_metrics_scheduler_mysql.py`、
`test_worker_queue_storage.py::test_mysql_claim_skips_locked_task`、
`test_schema_comments.py::test_mysql_comment_upgrade_preserves_definitions_constraints_and_rows`。

## B1 提交入口梳理（迁移前）

当前以下入口依赖 repository 的隐式 persist，迁移时需要逐个验证：

| 流程 | 当前提交与状态传递 | 迁移要求 |
| --- | --- | --- |
| 新建运行 | `AiGenerateTaskService.run`，同时写 run 和 WorkerTask | 显式保存新阶段、attempt、队列并一次提交 |
| 阶段输出保存 | `AiStageWorkflow` 的保存入口，部分路径重置审核 | 显式表达输出变更与审核重置，保留当前有效产物 |
| 阶段审核 | `_stage_review` 元组 + `_actor` | 审核命令携带阶段、结论、评论和操作人 |
| 修订/重试 | `_operation` 及 revisionInstruction | 显式命令区分修订与重试，冻结输入和本人授权 |
| Worker 事件 | `_worker_event`，先检查当前 Worker | 当前 attempt 的事件与状态更新同一事务应用 |
| 授权失败/租约超时 | `worker_authorization` / `worker_task` 触发状态同步 | 保留失败理由、旧 attempt 拒绝和事务完整性 |
| 正式导入 | API/UI/功能导入流程设置导入状态后 commit | 资产与导入账本原子提交，审核不自动导入 |
| 历史/详情读取 | 仓储调用 project/project_many，回填兼容属性 | 将读取投影与写入命令分开，不让读取隐式推进状态 |

`persist()` 当前扫描 session 的 identity map/new；不能用另一个名称包住扫描后宣称完成。
目标是业务入口明确给出本次要应用的执行变更，取消仓储 commit 的业务副作用。
迁移期间暂时保留旧路径时，必须列出尚未迁移入口；最终不得同时存在两条写状态路径。

### 当前实现与验证

已替换上述入口的隐式写入：业务命令显式传入单个 run、`ExecutionIntent` 和本次
WorkerTask，`ExecutionWriter.save()` 只 flush，不提交调用者事务。移除了两个仓储的
业务 commit 覆盖、session 全量扫描及 ORM 私有命令标记。

- `repositories/ai_execution.py` 负责兼容读取投影；
  `domain/ai_execution_format.py` 负责阶段布局与纯格式规则。
- `GenerationRunLauncher.launch()` 协调快照准备、结束准备事务、当前权限重查及最终原子写入。
  任务管理入口保留原有 HTTP 调用面；阶段操作和正式导入继续由各自模块负责。
- 代码风险分析改为依赖共享输出模块，解除与任务管理入口的双向依赖。
- 新增行为验证证明普通 commit 不发布产物，保存一个 run 不会发布另一个被读取的 run。
  架构检查阻止仓储恢复业务 commit、执行模块扫描 session 或使用旧命令标记。
- 编排测试显式注入内存写入器；真实执行存储测试保留 SQL 写入器。两个只建正式资产表、
  使用虚拟 run 的导入约束测试也声明该替身，不在生产实现中增加测试对象分支。

初轮全量回归发现 6 项测试适配失败（旧临时属性断言 2 项、缺少写入器依赖 4 项）；
修正后相关 28 项通过。运行编排与执行存储等专项 136 项通过。
真实 MySQL 全部 55 项通过。最新静态入口通过 Ruff、501 个文件格式检查和
353 个源码文件类型检查。最终六组全量回归共 1,489 项：1,425 通过、64 项环境跳过、
0 失败；另有 6 个通过的 subtest 不计入收集项。结合 55 项真实 MySQL 复验，
本批有 1,480 项通过证据，剩余 9 项是真实存储未启用。B1 验收完成。

## B2 实施中

已增加不可变的 AI/API/UI 执行上下文和 `read_worker_context()` 仓储查询。
查询从所属 run 和冻结 attempt 读取关联身份，不修改 WorkerTask、不复制租约状态。
9 项数据库测试覆盖五种执行形态、缺失关联、未知任务域及队列对象不变性，全部通过。
已将原 `services/worker_context.py` 的查询迁入仓储并删除原文件，
解除两个仓储反向依赖 service 的路径，架构允许清单同步收紧。
旧调用方暂由集中式 `project_worker_context()` 兼容投影衔接；租约过期入口不再调用仓储私有方法。
当前 503 个文件格式检查和 354 个源码文件类型检查通过。
上下文、队列、AI 执行、Worker 契约、UI 快照及架构专项共 110 通过、1 项 MySQL 环境跳过；
随后在独立临时 MySQL 中单独验证该领取 `SKIP LOCKED` 用例，1 项通过。

现有调用方直接消费类型化上下文、移除动态兼容字段、拆分各域快照与结果处理尚未完成；
本批只建立并验证读取入口及分层，不能据此宣称 B2 完成。

## 待完成

- B1 已完成；后续批次继续保留上述事务与旧回传保护。
- B2：Worker 上下文、域载荷与生命周期。
- B3：集成凭据、查询、绑定和导入职责；列表测量。
- B4：通用删除中的业务编排移出。
- B5：模块组织、依赖约束、剩余夹具迁移、统一诊断和文档。
