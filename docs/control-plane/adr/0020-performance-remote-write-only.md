# ADR 0020：性能测试首期只保留 Remote Write 监控接入

- 状态：已接受
- 日期：2026-11-17
- 取代：[ADR 0019](0019-performance-monitoring-snapshot.md) 的 Grafana 看板入口、Grafana/默认筛选快照字段、查询地址与查询凭据
- 被取代：—
- 关联：[ADR 0019](0019-performance-monitoring-snapshot.md)、[ADR 0014](0014-pre-release-single-baseline.md)、[数据库结构](../database-schema.md)、[Studio 性能测试](../../studio/performance-testing.md)

> 本决策取代 [ADR 0019](0019-performance-monitoring-snapshot.md) 中 Grafana 看板入口、Grafana/默认筛选快照字段，以及查询地址与查询凭据的相关决策。

## 背景

ADR 0019 为运行详情提供了 Grafana 深链：控制面保存 Grafana 地址、看板 UID 和默认筛选，前端按运行时间范围拼接 `var-run_id` 等参数。该方案要求使用者在平台外手工创建并维护看板和数据源，且 `run_id` 等变量名必须与平台约定一致；平台本身不调用 Grafana API。

当前阶段性能测试只要求闭环：用例 → k6 执行 → 指标通过 Remote Write 写入 Prometheus → 回传执行结果。展示与查看延后。`query_url`、查询认证与查询凭据虽然被保存和展示，但没有任何查询消费方（`secret_values()` 无调用方，仓库内没有 Prometheus 查询请求），属于“填了但不生效”的配置。

## 决策

1. `monitoring_connections` 只保留 `name`、`remote_write_url`、`remote_write_auth_type`、`remote_write_secret_json`、`enabled` 和审计字段；删除查询地址、查询认证、查询凭据、Grafana 地址、Grafana 看板 UID 和默认筛选。
2. `perf_runs.monitoring_snapshot_json` 只冻结 `connectionId`、`name`、`remoteWriteUrl`，仍不包含凭据。
3. API 请求与响应同步收敛：创建/更新不再接受查询或 Grafana 字段（`extra="forbid"` 返回 400），响应不再返回 `queryUrl`、`hasQueryCredentials`、`grafanaUrl`、`grafanaDashboardUid`、`defaultFilters`。
4. 运行详情移除 Grafana 按钮、趋势入口和默认筛选展示，只保留执行事实、k6 摘要、阈值、日志和数据文件；运行信息展示冻结的 Remote Write 地址。
5. 监控接入表单只配置 Remote Write 地址、写入认证和启用状态。
6. 按 [ADR 0014](0014-pre-release-single-baseline.md) 直接修改唯一 Alembic baseline，不新增迁移。
7. 平台内查看、Prometheus 查询 API 和查询凭据后续另行决策，不在本期预留。

## 后果

- 接入配置与表单字段明显减少，不再出现无法生效的查询配置。
- 历史运行快照仍包含旧键时，Pydantic 默认忽略未知字段，不影响详情读取；前端不再展示这些字段。
- 已有开发数据库不会因编辑 baseline 自动删除列，需要重建或执行 `alembic downgrade base && alembic upgrade head`。
- 本期没有任何平台内趋势入口；需要查看时序时仍可在 Prometheus 或自行部署的 Grafana 中按 `run_id` 查询，平台不提供链接。
- 后续若增加平台内查看，需要重新引入查询地址、查询凭据和查询后端，并按新 ADR 设计。

## 备选方案

- **保留 Grafana 深链，只降低看板配置成本**：仍要求用户维护 Grafana 和看板变量，首期不采用。
- **保留查询地址与查询凭据供后续使用**：当前没有消费方，会继续制造“配置了但不生效”的误解，不采用。
- **本期直接实现平台内固定趋势面板**：需要新增 Prometheus 查询代理、凭据读取路径、超时/缓存和图表交互，超出当前闭环，不采用。
