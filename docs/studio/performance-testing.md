# 性能测试（Studio）

性能测试复用现有测试工作区与基础服务的页面骨架。代码位于 `apps/studio/src/features/performance/`。

## 导航与路由

- 顶部「测试」悬停浮层：测试单 → API 测试 → UI 测试 → 性能测试；选中性能测试落在 `/testing?tab=perf`。
- 性能用例详情：`/performance/cases/:caseId`。
- 运行记录：`/performance/runs`，支持 `?caseId=` 过滤。
- 运行详情：`/performance/runs/:runId`。
- 顶部「基础服务」悬停浮层新增「性能监控」，落在 `/base-services?tab=monitoring`。

性能监控属于项目级共享基础服务，不放在性能用例页面内。发起运行时在对话框中同时选择性能环境和监控接入。

## 性能用例列表

- 使用公共 `tp-list-panel`、`tp-list-toolbar`、`tp-list-body`、`tp-list-scroll` 与 `EntityCard`。
- 工具栏包含性能环境、状态筛选、名称/描述搜索、环境管理、运行记录和新建性能用例。
- 卡片展示名称、启用状态、版本、数据文件数、最近更新；操作与 API/UI 测试一致：运行、编辑信息、删除。
- 新建/编辑基础信息使用右侧 Drawer。新建后进入 YAML 详情编辑器；用例是项目级资产，不绑定需求或迭代。

## 用例编辑

- YAML 使用公共 `TextCodeEditor`，它是唯一可编辑来源；前端只做语法和顶层结构提示，完整校验由控制面完成。
- 工具栏显示版本、启用状态、未保存标记、环境选择、运行记录、编辑信息、保存和发起运行。
- 保存会提交 YAML 与启用状态；有未保存修改时禁止发起运行。
- 数据文件通过 `uploadStoredFile(..., 'perf_case_data')` 直传 S3，再由 `PATCH /v1/perf-cases/{caseId}` 关联。上传前必须先在 YAML 的 `case.data` 声明 `source`，控制面会校验引用与文件元数据；上传/移除会连同当前 YAML 一起提交。
- 侧栏展示用例信息、数据文件和最近运行；数据文件可从 S3 下载，移除前需要先在 YAML 中删除对应 `source`。

## 运行

- 发起运行对话框必须选择 `kind="perf"` 的环境和已启用的监控接入。没有环境或接入时给出跳转入口。
- 运行记录使用服务端分页与筛选，列包括用例、环境、监控接入、状态、结果、开始时间、耗时和 k6 版本。
- 运行详情轮询排队/运行/停止中的状态；展示 k6 摘要指标、阈值结果、日志尾部、运行事实和数据文件。
- 平台不在页面内查询 Prometheus 或绘制时序图。Grafana 链接由运行冻结的接入快照生成，带 `var-run_id`、运行时间范围和默认筛选；未配置看板时按钮禁用。
- 监控快照由控制面在创建运行时写入 `perf_runs.monitoring_snapshot_json`，不包含凭据；之后修改或删除接入不影响历史运行。

## 监控接入管理

- 性能监控面板沿用基础服务卡片、工具栏和分页结构。
- 查询认证与 Remote Write 认证分别配置，支持 none/basic/bearer/headers。
- 编辑时凭据不会回显；认证方式不变且凭据留空表示保持原凭据，修改认证方式时必须重新填写。
- 默认筛选使用 JSON 对象，运行时转换为 Grafana 的 `var-<key>` 参数。
- 仅项目所有者可以新建、编辑和删除接入；成员发起运行时只能选择已启用接入。

## 相关代码

- 页面：`pages/PerformancePage.tsx`、`PerformanceCaseDetailPage.tsx`、`PerformanceRunsPage.tsx`、`PerformanceRunDetailPage.tsx`。
- 组件：`components/PerfCaseDrawer.tsx`、`StartPerfRunModal.tsx`、`PerfMonitoringPanel.tsx`、`PerfMonitoringDrawer.tsx`。
- API 与工具：`api/performance.api.ts`、`utils/perf.ts`、`utils/monitoringConnection.ts`。
- 控制面：`apps/control-plane/src/testing_agent/services/perf_run.py`、`schemas/perf_run.py`。
