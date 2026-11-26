# Service SQL 边界与纯读清单

- 状态：现行
- 负责人：control-plane maintainer
- 最近复核：2026-11-26
- 复核周期：每季度
- 适用范围：`apps/control-plane/src/testing_agent/services/`
- 变更/废弃：按[规范变更检查清单](../agents/domain.md#规范变更检查清单)执行；影响分层规则时更新开发规则并通知审查者。

控制面常规调用顺序是 `router → handler → service → repository → model`。Service 只在同一业务事务内保留直接 SQL：跨资源一致性检查、锁定顺序和原子条件更新。其余查询应进入 repository；本条说明存量例外如何登记，以及纯读查询的迁移状态。

## 登记方式

直接导入 SQLAlchemy 的 service 文件必须满足以下任一条件：

1. 在 `apps/control-plane/config/service-sql-allowlist.json` 中登记：
   - `classification`：`read-only`、`locking-read`、`read-write`、`write` 或 `types-only`；
   - `reason`：说明该文件为什么需要直接 SQL，或长期例外为何不迁移；
   - `migration`（可选）：`migrated` 或 `long-term-exception`，用于标记纯读迁移结果；不登记视为普通 allowlist 例外。
2. 在相关语句或模块顶部写 `# transaction-bound: <理由>`，说明事务边界。

`apps/control-plane/tests/test_architecture_layers.py` 会扫描 `services/**/*.py`：

- 新增直接 SQL 文件未登记且没有标记时失败；
- 清单条目缺少分类或理由时失败；
- 清单条目对应的文件已无直接 SQL 时失败（防止清单腐烂）。

运行：

```sh
cd apps/control-plane
uv run --locked --extra dev pytest tests/test_architecture_layers.py -q
```

新增纯读查询时优先加到 repository，不通过登记清单绕过分层。只有确实属于权限策略、读模型投影或与写路径共享事务的查询才保留在 service。

## 已迁移的纯读

| 原位置 | 迁移后 | 回归入口 |
| --- | --- | --- |
| `services/project.py::list_members` 的 owner/member 查询 | `ProjectRepository.owner`、`ProjectRepository.member_rows` | `test_project_membership_api.py` |
| `services/worker_skills.py::authorized_skill` 的默认技能查询 | `WorkerTaskRepository.default_skill` | `test_worker_contract.py` |
| `services/code_risk_analysis.py::gitlab_credentials_payload` | `IntegrationConnectionRepository.get_active_for_user` | `test_code_risk_snapshot.py`、`test_code_risk_credentials.py`、`test_code_risk_worker_api.py`、`test_code_risk_latest_runs.py` |
| `services/environment_access.py::authorized_environment_vars` | `ApiEnvironmentVarRepository.list_by_environment` | `test_ai_task_snapshots.py`、`test_ui_variables.py` |
| `services/integration_runtime.py` | `IntegrationRuntimeRepository.restored`、`isolated_scope` | `test_integration_maintenance.py` |
| `services/ui_generation_source.py::_access` | `SoftwareRepositoryRepository.get` | `test_ui_generation_repository_source.py` |
| `services/worker_domains/perf.py::get_run` | `PerfRunRepository.get_run` | `test_perf_api.py` |
| `services/zentao_mcp_authorization.py::invalidate_others` | `IntegrationConnectionRepository.list_authorized_by_service` | `test_zentao_mcp_bindings_api.py` |
| `services/zentao_mcp_selection.py` | `ResourceBindingRepository.active_project_binding`、`SharedServiceCatalogRepository.zentao_mcp_services` | `test_zentao_mcp_bindings_api.py`、`test_zentao_mcp_cases_api.py` |

文件仍保留 `AsyncSession` 类型导入时，allowlist 记为 `types-only` + `migration: migrated`；完全移除 SQLAlchemy 导入的文件从 allowlist 删除，避免清单腐烂。

## 长期例外

以下纯读保留在 service，并在 allowlist 中标记 `migration: long-term-exception`。这些查询与授权策略、跨表读模型或状态迁移共享同一读取上下文，迁移会分散规则或引入额外读取；行数或复杂度不再作为是否迁移的依据。

| 文件 | 长期保留理由 | 重新评估条件 |
| --- | --- | --- |
| `services/stage_storage/chain_view.py` | 生成链全景由 stage/attempt/version/import 多表组装，属于读模型投影 | 生成链读模型整体收口时 |
| `services/stored_file_access.py` | 下载授权按文件用途跨需求、Bug、运行、技能等资源验证归属，属于访问策略 | 文件访问策略抽为独立领域服务时 |
| `services/worker_domains/ui.py` | 读取与 UI 任务状态迁移、结果应用和计数更新交织 | worker 域拆分时 |
| `services/zentao_bindings.py` | 绑定解析同时执行共享服务选择、子绑定校验和推送状态汇总 | 绑定选择规则进入 domain 时 |

## 事务标记示例

```python
# transaction-bound: the linked-authorization check must see the same
# transaction as the update.
linked = await self.repository.session.scalar(...)
```

标记只说明边界，不表示可以把任意查询留在 service。新增可复用查询、列表筛选或分页仍应放入 repository。
