# 本地开发库性能运行迭代字段升级

- 日期：2026-11-20
- 状态：已完成（仅本地开发库）
- 负责人：control-plane maintainer
- 来源：用户要求升级此前实现的性能运行迭代字段
- 关联：[数据库结构](../database-schema.md)、[预发布阶段单一基线](../adr/0014-pre-release-single-baseline.md)、[性能运行指标规格](../../perf-worker/records/2026-11-20-performance-metrics-spec.md)

## 范围与方法

本次仅针对本地 MySQL 8.4 的 `testing-agent-control-plane-b`，在用户明确要求下补齐 `perf_runs` 和 `perf_suite_runs` 的 `sprint_id`、`sprint_name` 列；不新增 Alembic revision，也不修改数据库版本标记。其他数据库不受本记录覆盖。

升级前生成完整逻辑备份，验证备份包含两张表的结构与已有数据；本地备份文件在 git 忽略目录，访问权限为 0600，不作为长期审计证据。先在临时表验证对既有记录的默认值，再检查两表没有排队、运行或停止中的性能运行，使用 MySQL `ALGORITHM=INSTANT` 为两张 InnoDB 表新增列；控制面服务保持运行。

## 验证结果

- 升级前后 `perf_runs` 均为 8 行，`perf_suite_runs` 均为 3 行；已有记录的 `sprint_id` 为 NULL、`sprint_name` 为空字符串。
- 四列的类型、可空性与注释均与模型一致；`alembic_version` 保持 `20261103_0001`。
- 结构对比不再存在新增字段差异；仍有 33 处与本次范围无关的既有字段注释差异，本次未修改。
- 运行中的控制面 `/v1/health` 返回 HTTP 200；本次未部署新代码，未验证新代码的完整性能运行或夜莺集成。

这是经用户明确要求针对保留数据的本地库进行的一次性操作，不改变仓库关于空库初始化和预发布单一 baseline 的常规政策。
