# 裁剪只写留痕列并单源化 LLM 凭据

2026-10-10，基于全仓库字段使用审计（653 列三层检索加按域人工复核），用户确认删除 12 个"只写不读"的列并收敛 LLM API Key 的双列存储。审计背景与方法记录在排查会话中；本决策只影响已确认无任何读取方的存储位，不改变任何业务行为。

## 删除的列

- `requirements.document_storage_path`、`ai_generate_task_source_archives.storage_path`：模型注释自述的惰性遗留元数据，文件交付早已改走统一 `fileId`/S3。`requirements.document_download_url` 虽同批注释，但 AI Worker 任务源仍在消费，保留。
- `ai_generate_run_imports.artifact_attempt_id / imported_by / idempotency_key`：导入溯源实际经由 `ai_generate_run_stages.current_artifact_attempt_id`，幂等实际由 `run_id` 唯一约束加先查后插承担；三个字段全仓库零读取。
- `sprint_daily_metrics.metric_id`：行定位由 `uk_sprint_date` 承担，业务键零读取。
- `integration_jobs.claim_request_id`、`integration_claim_receipts.worker_id`、`integration_job_steps.input_digest`、`integration_restore_reviews.facts_json`、`bug_zentao_sync_baselines.applied_by`、`bug_zentao_pushes.source_json`：操作人或快照类留痕，零读取。恢复指纹（`integration_restore.py` 的全列反射打包）随结构自动收敛，两端同版本重算，不影响正确性；发布窗口内避免在恢复审查进行中时上线。

保留：`integration_jobs.claim_key` 虽无读取，但作为唯一约束承担并发领取栅栏；`api_case_runs.private_payload` 等加密信封列不进 API 是刻意设计。

## LLM 凭据单源化

个人连接历史上把加密后的 API Key 同时写入 `secret_json.apiKey` 与 `access_token`，靠"永远双写"维持一致，是副本漂移风险。新策略：`auth_type=api_key` 的连接只写 `secret_json.apiKey`；读取侧保留 `connection.access_token` 兜底以兼容迁移前的行，迁移 20261010_0039 清空存量重复副本。

## 领取回执保留窗口

`integration_claim_receipts` 按领取频率线性增长（本地环境 3 天 11 万行）且原设计永久保留。新策略：新增 `integration_execution.claim_receipt_retention_days`（默认 14 天），维护任务清理窗口外回执及指向已归档任务的回执；窗口外重放同一领取请求按新请求处理。这不削弱一次执行保证——远端写入的防重放由步骤级 `operation_id` 与 `receipts_json` 承担，永久保留；领取回执只保护领取调用本身的瞬时重放。

## 指标请求假接口收敛

`SprintDailyMetricRequest` 曾声明全部指标字段但服务端一律丢弃并按本地数据重算。请求体收敛为 `connectionId` 一个字段；指标数值不提供外部写入通道，口径解释权在服务端（与 ADR 0004 补充的缺陷指标口径一致）。

相关验证：`tests/test_initial_schema_migration.py`、`tests/test_schema_comments.py`、`tests/test_integration_maintenance.py`、`tests/test_sprint_daily_metrics_service.py`、`tests/test_go_field_contracts.py`。
