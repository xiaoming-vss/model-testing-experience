# Bug 生命周期对齐禅道

2026-10-06，用户确认平台 Bug 按禅道状态模型对齐，为后续单向和反向同步建立一致语义。本决策替代 ADR 0004 的六状态机：主状态使用 active/resolved/closed，confirmed 与 resolution 独立保存；重新激活是动作，activatedCount 记录次数，处理历史保留原文。

选择这一模型，避免将禅道多种解决方案全部误归为“已修复”，或在双向转换中丢失“未确认/已确认”和“延期处理”。原六状态改为主状态加处理结果，页面直接展示主状态、确认情况和解决方案；本地 Bug 仍独立于禅道，未配置 MCP 也能正常处理。

解决方案采用 fixed/bydesign/duplicate/external/notrepro/postponed/willnotfix/tostory。fixed 要求填写真实解决版本，duplicate 要求当前项目另一条 Bug；本地 duplicateBug 使用列表 ID，未来同步须解析对应远端关联，不直接当成禅道编号。tostory 只记录已转需求的处理结论，不自动创建需求。

迁移 20261006_0029：pending→active/未确认，processing→active/已确认，pending_regression→resolved/fixed，closed→closed/fixed，reopened→active并恢复确认历史和激活次数，rejected→resolved并从最新拒绝记录读取 bydesign/notrepro/postponed。未知状态或缺失拒绝原因会阻止迁移；旧记录没有解决版本时保留空值，不假定 trunk。旧历史不改写，不新增远端写入。

状态操作采用 confirm/resolve/close/activate；确认保持 active 并置 confirmed，解决保存方案，关闭保留方案，激活清空当前解决方案/版本/重复关联、增加次数并保留确认标志。旧动作参数仍由后端兼容，返回主状态统一采用新模型。新历史记录确认标志及解决方案前后值，防止仅显示 active→active 丢失确认含义。

本次完成本地领域模型、API、页面和旧数据迁移；禅道远端状态调用、反向导入和正文差异处理仍是独立的后续实现。
