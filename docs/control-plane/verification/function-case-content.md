# 功能用例正文与验证

功能用例正文以 `content_json` 保存前置条件和操作/预期成对的结构化步骤。前端与禅道接口使用的文本字段通过领域转换函数适配；`from_legacy`、`set_legacy_content` 是仍在使用的接口转换，不是旧数据库升级脚本。

新库初始化见 [ADR-0006](../adr/0006-fresh-database-baseline.md)，已移除旧库正文转换迁移。

验证入口：`tests/test_function_case_content.py`、`tests/test_function_case_zentao_bulk_import.py`，覆盖结构化创建/修改、文本接口兼容、非法正文拒绝和禅道多行步骤导出。
