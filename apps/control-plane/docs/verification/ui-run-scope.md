# UI 运行归属与验证

UI 用例运行和套件运行通过套件→需求→迭代推导当前项目归属。需求移动后权限随当前项目变化；历史日报保留已保存的数值，实时统计遵循当前归属。

新库直接初始化最终结构，见 [ADR-0006](../adr/0006-fresh-database-baseline.md)。开发期间的归属字段收缩迁移已移除；前端与 Worker 接口字段继续由业务关系生成。

验证入口：`tests/test_ui_run_scope.py`、`tests/test_ui_run_snapshot.py` 和初始化测试。
