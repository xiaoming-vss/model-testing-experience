# ADR 0019：性能运行冻结监控接入快照，首期只提供 Grafana 入口

- 状态：已取代
- 日期：2026-11-17
- 取代：—
- 被取代：[ADR 0020](0020-performance-remote-write-only.md)（Grafana 看板入口、Grafana/默认筛选快照字段、查询地址与查询凭据）
- 关联：[ADR 0020](0020-performance-remote-write-only.md)（Grafana 相关决策）、性能测试模块需求（仓库外需求文档）、[数据库结构](../database-schema.md)、[Studio 性能测试](../../studio/performance-testing.md)

> 本决策中的 Grafana 看板入口、Grafana/默认筛选快照字段，以及查询地址与查询凭据的相关决策已由 [ADR 0020](0020-performance-remote-write-only.md) 取代。

## 背景

性能测试的监控接入是项目级基础服务，发起运行时才选择具体 Prometheus/Grafana。接入可以被重命名、改地址或删除，但历史运行仍需要展示当时的监控来源和看板入口。运行详情首期不在平台内查询 Prometheus 或绘制时序图，只提供带运行时间范围的 Grafana 跳转。

运行已经冻结 `monitoring_connection_id` 和 `monitoring_connection_name`，但没有保存查询地址、Grafana 看板和默认筛选，因此接入后续变化后无法复原看板链接。直接把凭据或完整接入配置复制进每次运行也不合适：凭据只需要留在后端和 Worker，不应扩散到运行展示或前端。

## 决策

1. `perf_runs` 新增 `monitoring_snapshot_json`，创建运行时写入非敏感公开快照：
   - `connectionId`
   - `name`
   - `queryUrl`
   - `remoteWriteUrl`
   - `grafanaUrl`
   - `grafanaDashboardUid`
   - `defaultFilters`
2. 快照不包含查询认证、Remote Write 认证、用户名、密码、Token 或 Headers。Remote Write 写凭据仍只存在加密的 `private_payload` 中，按 Worker 快照下发。
3. 运行详情响应新增 `monitoring` 字段，读取冻结快照；接入修改或删除不影响历史运行。历史运行没有快照时返回空值，页面提示“未保存地址快照”，不伪造当前接入配置。
4. 首期平台不提供 Prometheus 查询 API、不绘制时序图、不嵌入 Grafana。运行详情只展示 k6 摘要、阈值、日志和“在 Grafana 查看趋势”入口。
5. Grafana 链接由前端使用冻结快照生成：`/d/<dashboardUid>`，附加 `var-run_id`、运行开始/结束时间和 `defaultFilters` 转换出的 `var-<key>`。没有看板地址或 UID 时禁用入口。
6. 监控接入继续由「基础服务 → 性能监控」维护，不放在性能用例页；性能用例只引用运行时的接入选择结果。

## 后果

- 接入改名、换地址或删除后，历史运行仍能显示当时的数据源和看板配置。
- 前端永远拿不到监控凭据；凭据只在服务端解密并注入 Worker 快照。
- 运行展示与接入当前状态解耦，排查历史问题时能看到真实来源。
- 旧运行没有快照时只能展示接入名称，不能生成 Grafana 链接；需要重新运行才能获得完整入口。
- 后续若增加平台内查询，需要新增查询后端与凭据读取路径，不复用本快照中的凭据；本 ADR 不预埋查询接口。
- 快照是运行事实的一部分，不随后续接入更新而回填。

## 备选方案

- **只存接入 ID，展示时读取当前接入**：接入删除或改地址后历史运行无法复原，不采用。
- **在运行中保存完整接入配置（含凭据）**：扩大凭据暴露面，且运行展示不需要凭据，不采用。
- **运行详情直接调用 Prometheus 查询**：首期需要新增查询权限、超时、缓存和图表交互，超出当前闭环，不采用。
- **嵌入 Grafana iframe**：涉及 Grafana 登录态和跨域策略，首期先使用新窗口入口。
