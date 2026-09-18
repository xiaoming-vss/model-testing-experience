# AI 生成运行存储与验证

数据库初始化采用 [ADR-0006](../adr/0006-fresh-database-baseline.md) 的单一基线，旧库回填与收缩迁移已移除。

- `ai_generate_task_runs` 保存运行身份、状态、输入快照及时间，通过生成任务推导当前归属。
- `ai_generate_run_stages` 保存阶段执行、审核状态及有效产物/活动执行指针。
- `ai_generate_stage_attempts` 保存每次生成、优化、人工重试的输入、指令、产物和错误。
- `ai_generate_run_imports` 保存成功导入记录，运行唯一约束与幂等键防止重复导入。
- `AiRunView` 保留前端和 Worker 接口字段，字段由规范化记录生成，不再是主表数据库列。

两个 AI Repository 在提交前同步运行、阶段、执行记录和 Worker 队列。优化失败保留旧产物；重试使用失败执行的输入；过期 Worker 回传不能覆盖新执行；列表批量读取，避免逐条查询。运行关联的生成任务缺失时拒绝访问，不再从历史快照恢复授权归属。

验证入口：`tests/test_ai_execution_storage.py`、功能阶段 retry/revise 测试、需求阶段 retry 测试，以及 `tests/test_initial_schema_migration.py` 和 `tests/test_mysql_initialization.py`。
