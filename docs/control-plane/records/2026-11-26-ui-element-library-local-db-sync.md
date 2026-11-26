# 本地开发库元素库补表

- 日期：2026-11-26
- 范围：本地 MySQL 开发库 `mtx_candidate_20261121`
- 关联：[元素库接口](../ui-element-library.md)、[预发布单一基线](../adr/0014-pre-release-single-baseline.md)

Studio 在「Zata-Platform → demo → 元素库」显示加载失败。开发库的 Alembic 标记已是 `20261103_0001`，两张新增表尚未创建。使用该库复现时，分组查询报 MySQL 1146，元素和分组列表均返回 HTTP 500。

使用控制面 ORM 元数据定向创建 `ui_element_groups` 和 `ui_elements`。核对了两表的列注释、外键、唯一约束和索引，并确认数据库新增对象只有这两张表，Alembic 标记仍为 `20261103_0001`。原项目及仓库数据保持原样。

使用同一项目和仓库再次运行控制面列表请求，两条接口均返回 HTTP 200，分组和元素总数均为 0。
