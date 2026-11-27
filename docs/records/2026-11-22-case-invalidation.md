# 2026-11-22 正式用例失效标记

- 日期：2026-11-22
- 状态：已实施
- 负责人：platform maintainers
- 来源：2026-11-22 用例失效状态需求讨论与实施计划
- 关联：[ADR 0026](../control-plane/adr/0026-case-invalidation-marker.md)、[数据库结构](../control-plane/database-schema.md#正式用例失效标记)、[控制面上下文](../control-plane/CONTEXT.md)、[Studio 上下文](../studio/CONTEXT.md)

## 结论

功能、API、UI、性能四类正式用例统一使用可空 `invalidated_at` 表示失效：空值有效，非空已失效并保留首次失效时间，可恢复。失效用例退出新的执行与 AI 分析，但历史运行、测试单执行条目、执行结果、历史统计和已冻结 AI 快照保持不变；它仍占用原名称/标题并保留在原测试集或 Collection 中。该标记与 API/UI 的 `enabled` 正交，不是软删除。

## 实施内容

- 四张用例表增加 `invalidated_at DATETIME NULL` 和同名索引；按 ADR 0014 直接修改唯一 Alembic baseline，不新增迁移。
- 四类响应增加 `invalidatedAt`，列表接口增加可选 `invalidated` 查询参数；新增四个项目级 `batch-invalidation` 端点，要求项目 `write` 权限，按项目范围整体成功或失败，重复失效保留首次时间。
- API 单用例运行、UI 单用例调试、性能单用例运行拒绝失效用例；API Collection、UI 测试集、性能测试集运行在控制面过滤失效用例，全部失效时返回“没有有效用例”。
- 测试单新加入失效用例整体拒绝并返回 `invalidCaseIds`；既有条目仍可分配、执行和更新结果。
- 代码风险分析和 UI 生成只读取有效用例；功能/API/UI 生成导入覆盖同名用例时清空失效标记。
- API 每日指标只统计有效 API 用例；功能/UI 历史统计不重算。
- Studio 四类管理列表默认显示全部，增加「全部 / 有效 / 已失效」状态胶囊、橙色失效标签和失效时间提示；API/UI/性能共用「管理用例状态」弹窗，功能用例库沿用勾选条批量标记/恢复；筛选态禁用拖拽排序；单用例运行入口禁用并显示测试集运行排除提示；测试单加入与 UI 生成选择只请求有效用例。
- 新增共享实现 `shared/utils/caseInvalidation.ts`、`shared/components/CaseInvalidatedTag.tsx`、`shared/components/CaseInvalidationModal.tsx`。

## 契约与兼容

- 四类响应与列表查询新增字段/参数，属于向后兼容扩展；项目级批量端点为新增路由。
- Worker 执行协议、运行快照和冻结输入结构未变；控制面在创建任务或运行前完成过滤，在途任务继续使用原快照。
- 失效用例仍参与测试集资产计数与名称唯一约束；要复用同名标题需改名、删除或通过生成导入覆盖恢复。
- 按旧 baseline 建表的本地开发库需要重建数据库或手工补列。

## 验证

- 新增 `apps/control-plane/tests/test_case_invalidation.py`：7 项通过，覆盖四类批量失效/恢复、幂等与首次时间、列表筛选、单用例/测试集运行拒绝或过滤、测试单拒绝与既有条目执行、AI 输入与每日指标过滤、生成导入覆盖恢复。
- 控制面关联回归：失效、功能用例库、API/UI 运行、性能测试集、测试单、代码风险快照、生成根输入、每日指标与请求契约共 89 项通过；契约与迁移测试 46 项通过、1 项跳过。
- 控制面全量 `uv run --locked --extra dev python scripts/check.py`：Ruff、格式、mypy 与测试全部通过，结果为 `1803 passed, 140 skipped, 3 subtests passed`；跳过项均为未提供一次性 MySQL、S3 或存储环境的测试。
- Studio `npm run verify`：type-check、lint、主题、CSS、边界、Tailwind、构建、bundle 与单测全部通过，`205` 个测试文件、`1044` 项用例通过。新增覆盖共享状态弹窗、功能用例库状态筛选与批量操作、API/UI/性能页面标签/筛选/弹窗/运行入口，以及测试单加入与 UI 生成选择只请求有效用例。
- 文档：`python3 scripts/check_docs.py` 通过，检查 `144` 个 Markdown 文件与 `95` 个 skill 文件的链接。

## 边界

- 本轮不提供跨类型统一检索页；四类字段、查询参数和项目级批量端点已按后续聚合修改的方式设计。
- 不记录失效原因、操作者和恢复历史，只保留首次失效时间。
- 禅道推送、用例导出、测试单图谱和用例图解不按当前失效状态额外过滤；它们使用显式选择或执行条目快照，保持历史语义。
- 本记录未执行真实浏览器视觉验收；页面结构、交互与响应式行为由 Studio 单测覆盖，浅色/深色及真实数据下的视觉检查仍需在本地浏览器补做。
