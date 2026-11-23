# 夜莺性能运行查询

夜莺应查询接收 k6 Remote Write 的同一 Prometheus 数据源。筛选标签为 `project_id`、`sprint_id`、`suite_id`、`suite_run_id`、`case_id`、`run_id` 和步骤指标上的 `step`；字段缺省表示该运行没有对应身份。夜莺变量的多选条件用 `=~`，各变量引用上一级形成级联。

例如，在已选定一次用例运行后，可查询：

```promql
sum by (step) (rate(k6_mtx_step_results_total{run_id="$run_id",outcome="failed"}[1m]))
```

```promql
k6_mtx_step_request_duration_p95{run_id="$run_id"}
```

```promql
k6_mtx_case_request_duration_p95{run_id="$run_id"}
```

自定义耗时序列在 Prometheus 中以秒为单位，k6 summary 为毫秒。P95 是对应时间序列的统计值，不对不同时序或不同时间点的 P95 求平均作为总体 P95；比较完整运行应查看运行 summary。计数器在没有样本或运行时间过短时可能返回无数据，无数据不能直接解释为零或成功。

夜莺 9.3.0 的变量预览支持通过 `query_result` 和命名捕获组 `text`、`value` 显示名称并传递 ID，但当前平台尚未提供经过授权的实时名称映射数据源；因此以上查询示例只使用 ID。改名、删除、同名和跨项目权限问题解决前，不应把名称映射或完整级联看板声明为已交付。仅靠标签筛选不能隔离项目数据。
