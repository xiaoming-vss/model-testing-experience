# control-plane 结构与质量排查记录

日期：2026-10-20。范围：当前工作区内的 `apps/control-plane`。
对应[整改方案](control-plane-remediation-plan.md)。

## 结论

当前适合做模块化整改，尚无证据要求拆成多个独立部署服务。主要风险集中在：

- AI 执行的提交语义藏在 repository 覆盖方法中。
- 通用删除、集成生命周期、权限和凭据模块形成跨层依赖环。
- 多个大型编排模块同时承担不同业务操作。
- 全项目类型与格式检查尚未通过，测试公共准备代码耦合于测试文件。

这些是维护性和可验证性问题；不能仅据此认定存在数据损坏、循环导入崩溃或线上性能瓶颈。

最终分组回归：1,477 项中 1,410 项通过、3 项失败、64 项跳过。
失败包括两个与 ADR 冲突的正文漂移断言，以及一个 OpenAPI 字典结构约束。
真实 MySQL 检查跳过 55 项，真实存储检查跳过 9 项，不能声明这些外部环境已验收。

## 基线和方法

基准提交为 `ea7fb1d8a3fbf85bdf9cfbef05fe9334733f992b`，但排查对象是包含未提交修改的工作区，
不是该提交的纯净检出。开始检查时存在 125 条 Git 状态记录，包含既有账号治理、LDAP 和认证整理。

方法包括 Python AST 文件/函数/依赖扫描、重点调用链人工阅读、全源码静态检查、全量测试收集和行为测试。
代码计数排除 `.venv`、生成目录和迁移，采用物理行数，包含空行和注释。
测试文件数分别统计 `test_*.py` 和全部测试辅助 Python 文件。

原始结构结果、静态检查输出、Git 基线和源码摘要保存在仓库根
`.scratch/control-plane-audit/`。源码摘要仅覆盖本次检查的 Python 源码和测试，
用于核对排查期间是否发生变动，不包含配置或凭据。

## 规模

| 范围 | 文件数 | 物理行数 |
| --- | ---: | ---: |
| 全部 Python 源码 | 348 | 44,342 |
| services | 115 | 24,747 |
| repositories | 39 | 4,297 |
| handlers | 45 | 3,800 |
| schemas | 39 | 3,151 |
| models | 42 | 2,947 |
| routers | 34 | 1,987 |
| domain | 11 | 1,011 |
| 测试及辅助文件 | 141 | 38,781 |

另有 43 个迁移文件、139 个 `test_*.py` 文件；测试收集得到 1,477 项。
services 约占源码的 56%。这表示编排职责集中，不是“大文件必然错误”的判定线。

## 已确认的问题与证据

### A0 两项正文漂移测试与已接受决策冲突

全量测试发现两个失败，随后单独运行以下命令再次复现：

```sh
uv run --locked --extra dev python -m pytest \
  tests/test_bug_zentao_inline_images.py -k remote_description_changes -q --tb=short
```

结果：2 failed、19 deselected。两个参数分别模拟远端正文内容和样式改变，
均在测试文件第 153 行期望 `latestJob.jobStatus == "partial"`，实际为 `"succeeded"`。

[ADR 0007](adr/0007-description-drift-overwrite.md) 已于 2026-10-08 明确正文漂移按平台内容覆盖，
不再因该漂移拒绝执行。`services/integration_bug_steps.py:222` 的对应分支遵循此策略；
测试 fixture 的 `get_bugs_bugID` 返回当前模拟正文，并非忽略了被修改的正文。
因此可以确认失败断言与当前决策冲突，不能为了让旧断言通过而恢复旧阻断策略。

整改应将这两个场景改成验证覆盖结果、`overwrote` 事实和已上传图片复用，
并保留未知结果不重复写及字段更新仍阻止漂移的独立测试。
本轮没有修改断言；当前全量测试不能报告通过。

### A0b OpenAPI 字典字段违反现有结构约束

`test_openapi_tags.py::test_openapi_does_not_emit_additional_properties_placeholders`
在分组回归及独立复验中均失败。独立复验命令：

```sh
uv run --locked --extra dev python -m pytest \
  tests/test_openapi_tags.py::test_openapi_does_not_emit_additional_properties_placeholders \
  -q --tb=short
```

结果：1 failed。直接遍历当前 OpenAPI 确认以下六处 `additionalProperties: true`：

- `ZentaoBugImportPreview` 的 `snapshot`、`converted`、`description`。
- `ZentaoRemoteGroupPreview` 的 `local`、`remote`、`baseline` 非空分支。

来源为 `schemas/bug_zentao_import.py` 和 `schemas/bug_zentao_pull.py` 中的字典类型声明，
并非 LDAP 设置接口。当前可以确认实现与测试约束不一致，不能仅据此判断字段都应禁止扩展。
整改先区分固定响应与有意开放的外部结构，再选择命名模型或精确的兼容例外，
并验证既有调用方；禁止全局放宽测试或直接全局设置 `extra="forbid"`。

### A1 AI 执行提交带有隐式业务行为

证据：

- `src/testing_agent/repositories/ai_generate_task.py:24` 的 `commit()` 调用 `services.ai_execution.persist()`。
- `src/testing_agent/repositories/worker_task.py:20` 同样覆盖 `commit()`。
- `src/testing_agent/services/ai_execution/__init__.py:410` 扫描 session 的 identity map/new 集合，
  检查 `_execution_state`、`_operation`、`_stage_review` 和 `_worker_event`，再同步阶段与队列。

影响：调用者看到的“提交”不只是保存显式修改，还会触发执行状态同步；换一个 repository 或遗漏临时标记可能改变语义。
该机制也承担原子一致性，不能直接删除。整改首先明确事务入口和兼容投影，再逐条迁移调用方。

已有测试保护：`test_ai_execution_storage.py` 包含队列与阶段原子提交、回滚、旧 Worker 晚到事件、
修订失败、当前产物和审核/导入分离等场景。不能把“复杂”解释为这些行为没有测试。

### A2 通用存储基础层依赖业务生命周期

证据：

- `repositories/base.py:20` 的 `hard_delete()` 调用通用 `delete_resource()`。
- `repositories/deletion.py:157` 根据资源类型调度清理，对 Bug/Project/SharedService 调用
  `services.integration_lifecycle` 的保护和撤销逻辑。
- AST 扫描共发现 5 个 repository 文件中的 11 处 service 导入。
- 包含函数内部导入的静态依赖图存在一个 22 模块的强连通集合，
  涉及通用仓储、删除、集成执行、凭据、权限和禅道操作；另有 AI 任务/代码风险分析的双模块集合。

影响：基础层调整可能经业务反向依赖影响多个领域，单看文件夹无法判断影响范围。
强连通集合表示存在依赖路径闭环，包含延迟导入和类型相关引用，不等于 Python 导入时一定报错。
整改应移出删除编排和业务提交行为，不能用更多延迟导入掩盖依赖关系。

### A3 编排模块职责过于集中

| 文件，均位于 `src/testing_agent/` | 行数 | 人工核对的职责集中点 |
| --- | ---: | --- |
| `services/ai_generate_task.py` | 927 | 任务管理、运行、报告、阶段操作、审核、正式导入入口 |
| `services/integration_connection.py` | 874 | 个人连接管理、重新认证、凭据处理和外部资源查询 |
| `services/resource_binding.py` | 847 | GitLab/禅道以及项目/需求不同层级的绑定 |
| `services/zentao_bug_import.py` | 1,112 | 远端候选读取、内容准备、附件和本地导入事务 |
| `services/worker.py` | 656 | 多任务域快照、事件更新、运行结果和条目汇总 |
| `services/ai_execution/__init__.py` | 617 | 阶段/attempt 持久化与兼容输出投影 |

`AiGenerateTaskService.run()` 为 171 行；执行同步 `sync_run()` 为 185 行；
恢复证明读取 `read_restore_proof()` 为 221 行。长度仅用于选择阅读入口，
不要求拆掉为维持原子性而合理聚合的步骤。

### A4 跨模块使用私有实现

已核实：

- `services/worker_task.py:122` 调用 `self.repository._hydrate()`。
- `services/shared_service.py`、`bug_zentao_push.py`、`bug_zentao_attachment.py` 和
  `zentao_mcp.py` 存在对连接模块 `_decrypt_secret()` 的调用。

影响：调用方必须了解另一个模块的内部对象组织和凭据表示，内部调整会扩散。
这些私有调用本身不证明越权；整改要提供包含本人归属校验的公共访问接口，
不能为了消除下划线而让解密成为可随意调用的通用能力。

### A5 已确认的静态检查失败

全 `src/tests` Ruff 检查为 0 项错误。格式检查报告 9 个文件需要格式化：

```text
src/testing_agent/core/security.py
src/testing_agent/handlers/admin_users.py
src/testing_agent/repositories/project.py
src/testing_agent/routers/admin_users.py
src/testing_agent/services/ldap_settings.py
src/testing_agent/services/project.py
tests/test_hard_deletion.py
tests/test_local_account_management.py
tests/test_ui_case_source_archive.py
```

全源码 mypy 检查 348 个文件，报告 6 个文件中的 7 处错误：

| 文件及行号，均位于 `src/testing_agent/` | 错误 |
| --- | --- |
| `core/object_storage.py:59` | boto3 Config 的 S3 配置字典类型不匹配 |
| `repositories/api_run_scope.py:15` | Mixin 未声明其依赖的 session |
| `services/worker_context.py:50` | API/UI ORM 模型变量联合类型不一致，两处 |
| `repositories/test_order_entry.py:147` | SQLAlchemy Row 序列与声明的 tuple 列表不一致 |
| `repositories/bug.py:180` | ORM 列属性与 SQL 表达式变量类型不一致 |
| `services/builtin_skills.py:29` | 字典列表与 SkillFileInput 列表类型不一致 |

这些是当前实际检查失败，不是推测的业务故障；本轮未修复。
AST 另外统计到 642 个公开函数存在返回值或参数标注缺失，
它不等于 642 个类型错误，也不作为全量加注解的整改任务。

### A6 测试共享准备依赖测试文件

74 个 `test_*.py` 文件会从另一个 `test_*.py` 导入内容，共 192 处导入。
其中 `test_project_membership_api` 被引用 52 次，
`test_ai_execution_storage` 被引用 20 次。次数按 import 语句计，不是调用次数。

影响：修改或移动测试文件可能影响其他业务域的夹具和收集；测试实现逐渐承担公共库职责。
建议先迁移本次要改的 AI/Worker/集成支持代码，再扩展到其余范围。

核对收集清单与实际结果时还发现 7 个 ZIP 参数化测试 ID 随时间变化：
`test_ui_case_source_archive.py` 在收集时调用 `ZipFile.writestr()` 生成 ZIP，
默认归档时间戳进入二进制参数及 pytest 自动 ID。
已解码并核对两次参数的文件名、文件属性和内容一致；它们不是遗漏用例。
建议使用稳定的显式 ID，避免失败复验和结果比对依赖二进制时间戳。

现有架构测试保护 router/handler 不直接导入持久化细节，以及业务文件拆分等约定，
但没有全面约束 repository → service 或模块私有方法引用。
没有发现 `.github/workflows`、`.gitlab-ci.yml`、`Jenkinsfile`、`azure-pipelines.yml`；
这仅表示仓库中未发现这些常见入口，不证明团队没有外部 CI。

## 待测量和待核实的风险

### A7 共享服务列表串行探测远端实例

`services/shared_service.py:119` 的列表逐项 `await self.dump(...)`。
`dump()` 对满足条件的 MCP 授权调用远端 `discover_instance()`，
并查询本人连接和实例状态。

可以确认列表响应包含串行远端等待；没有请求规模和时延测量，不能声称已发生线上性能问题。
下一步用受控延迟模拟统计外部调用数量与耗时，再判断是否需要批量读取、独立探测或受限并发。
不得并发复用同一个 AsyncSession，也不得缓存可用于重新授予执行权限的过期结果。

### A8 未知异常入口缺少显式的统一诊断

`app.py` 的 `handle_unexpected_error()` 直接返回稳定错误信封，
该处理器没有显式记录关联标识和脱敏堆栈。
框架或服务器可能仍记录异常，因此不能解释成“系统完全没有异常日志”。
实施前应核对实际日志路径；统一入口要防止重复记录以及第三方异常中的凭据泄露。

### SQL 所在位置需要逐项判断

54 个 service 文件导入 SQLAlchemy。该数字不是违规数量：
项目规则允许同一事务内的跨资源一致性检查和加锁查询留在 service。
整改时区分普通查询与事务必需查询，不批量搬运全部 SQL。

## 已有合理设计

- 控制面拥有业务数据库，三个 Worker 分别执行 AI、API/UI 和集成任务，已有运行隔离。
- 角色动作规则与本人凭据分开，认证和会话刚完成集中整理。
- 集成执行具有写入意图、步骤身份、未知结果和恢复隔离；这些是必须保留的业务复杂性。
- 文件模块对同步存储 IO 使用线程委托；不能仅凭使用 boto3 就认定异步事件循环被阻塞。
- 已有较多状态、授权、回滚和迁移测试，整改应利用它们，而不是重新建立一套浅层替身测试。

## 实际验证命令

工作目录为 `apps/control-plane/`，使用现有锁定依赖环境：

```sh
uv run --locked --extra dev ruff check src tests --output-format json
uv run --locked --extra dev ruff format --check src tests
uv run --locked --extra dev mypy --python-version 3.12 --check-untyped-defs src/testing_agent
uv run --locked --extra dev python -m pytest --collect-only -q
uv run --locked --extra dev python -m pytest -q -rs --tb=short
```

前四项分别为 Ruff 通过、9 文件格式未通过、7 项类型错误、1,477 项测试收集成功。
串行行为回归运行 518.97 秒后主动中断，已完成 261 项通过和上述 2 项失败。
随后按文件将全部 1,477 项重新分为六组独立运行，不将中断轮次计入最终总数。
各组分别包含 292、215、223、232、272、243 项；分组文件清单见
`.scratch/control-plane-audit/shards.json`。

可在仓库根目录运行 `python3 .scratch/control-plane-audit/run_shard.py 0`
复验第一组，将编号换为 1–5 可复验其余组；使用同样的 pytest 参数和现有锁文件。
分组回归覆盖所有收集到的测试，但不证明跨组的执行顺序依赖不存在。
最终结果如下，串行中断和独立复验不重复计数：

| 分组 | 收集项 | 通过 | 失败 | 跳过 |
| --- | ---: | ---: | ---: | ---: |
| 0 | 292 | 292 | 0 | 0 |
| 1 | 215 | 215 | 0 | 0 |
| 2 | 223 | 174 | 0 | 49 |
| 3 | 232 | 219 | 2 | 11 |
| 4 | 272 | 272 | 0 | 0 |
| 5 | 243 | 238 | 1 | 4 |
| 合计 | 1,477 | 1,410 | 3 | 64 |

另有 6 个通过的 subtest，不加入 1,477 个收集项的总数。
分组日志和 `test-results.json` 保存在 `.scratch/control-plane-audit/`；
除上述已核实的 ZIP 时间戳差异外，node ID 与收集清单一致，没有重复或遗漏。
源码摘要复核显示排查期间 Python 源码和测试文件没有变动。
上次认证重构的局部通过结果不替代本轮全量检查。

本轮没有性能压测、生产日志采样或真实外部写入验证；没有访问开发/生产数据库。
55 项 MySQL 检查因未设置 `CONTROL_PLANE_TEST_DATABASE_URL` 跳过；
9 项真实存储检查因未显式启用 `CONTROL_PLANE_STORAGE_LIVE` 跳过。
