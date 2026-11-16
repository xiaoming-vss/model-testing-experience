# 预发布阶段单一基线

2026-11-15。第一版正式发布前，控制面数据库结构只维护一个可编辑基线，不保留 update 迁移链。本决策暂时取代 [ADR 0010](0010-unified-ai-execution.md) 中“后续模型变更必须新增迁移、不改写 baseline”的部分；第一版发布后恢复冻结基线并新增迁移。

## 决策

- `Base.metadata` 仍是唯一结构来源，`alembic/versions/20261103_0001_v1_baseline.py` 是唯一 revision。
- 第一版正式发布前，表、字段、约束、索引、默认值和注释变更直接修改该 baseline，不新增迁移；迁移链保持单 head、单 revision。
- 空库仍通过 `alembic upgrade head` 初始化；downgrade 只用于空库测试往返。
- 第一版正式发布时冻结 baseline。发布后的结构变更新增迁移，不改写已发布的基线。
- 旧 revision 0002–0005 已移除；已有开发库在结构零差异确认后使用一次性 `alembic stamp --purge 20261103_0001`，或重建空库后重新初始化。

## 后果与边界

- 预发布期间不保留逐次结构变更历史；需要历史证据时查看 Git 提交记录。
- 已指向旧 revision 的数据库不能直接执行 `alembic upgrade head`；必须重建空库或按部署说明 stamp。
- `test_initial_schema_migration.py` 固定唯一 revision、空库升级、降级与再次升级，防止误加 update 迁移。
- 第一版发布后，本 ADR 的“直接修改 baseline”约定失效，按 ADR 0010 的冻结基线与增量迁移执行。
