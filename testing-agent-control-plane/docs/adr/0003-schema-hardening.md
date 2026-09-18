# 数据库结构加固

删除行为现已由 [ADR-0009](0009-child-first-hard-deletion.md) 更新为逐级硬删除；下文软删除描述保留作为当时决策背景。

项目使用凭据加密、与查询匹配的复合索引、正确的日期类型、业务唯一约束与单态血缘外键保护数据。初始化方式及软删除唯一键的修正见 [ADR-0006](0006-fresh-database-baseline.md)。

- **凭据加密**：ZenTao 密码、LLM apiKey/access_token、GitLab token 经 `IntegrationCredentialCipher` 加密入库，密钥来自 `security.integration.key`。ZenTao 会话 access_token 的现有存储方式保持不变。
- **索引**：软删除过滤与业务查询列建立复合索引，避免无查询支撑的单列索引。
- **日期**：`sprint_daily_metrics.snapshot_date` 使用 `DATE`。
- **业务唯一**：直接以业务字段组成唯一键，不增加软删除唯一性辅助列。当前软删除记录继续占用唯一键，物理删除后才可复用；删除接口后续再统一改为硬删除。
- **血缘外键**：requirements→sprints、api_collections/function_test_suites/ui_test_suites→requirements、api_cases→api_collections、api_case_runs→api_cases、api_collection_run_items→api_case_runs。多态关联继续由业务层校验；新库直接建立约束，不执行历史孤儿数据清理。
