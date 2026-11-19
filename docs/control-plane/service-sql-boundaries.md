# Service SQL 边界与纯读清单

- 状态：现行
- 负责人：control-plane maintainer
- 最近复核：2026-11-19
- 复核周期：每季度
- 适用范围：`apps/control-plane/src/testing_agent/services/`
- 变更/废弃：按[规范变更检查清单](../agents/domain.md#规范变更检查清单)执行；影响分层规则时更新开发规则并通知审查者。

控制面常规调用顺序是 `router → handler → service → repository → model`。Service 只在同一业务事务内保留直接 SQL：跨资源一致性检查、锁定顺序和原子条件更新。其余查询应进入 repository；本条说明存量例外如何登记，以及纯读查询的迁移状态。

## 登记方式

直接导入 SQLAlchemy 的 service 文件必须满足以下任一条件：

1. 在 `apps/control-plane/config/service-sql-allowlist.json` 中登记：
   - `classification`：`read-only`、`locking-read`、`read-write`、`write` 或 `types-only`；
   - `reason`：说明该文件为什么需要直接 SQL，或纯读为何暂不迁移。
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

| 原位置 | 迁移后 | 说明 |
| --- | --- | --- |
| `services/project.py::list_members` 的 owner/member 查询 | `ProjectRepository.owner`、`ProjectRepository.member_rows` | 项目访问校验仍在 service，成员读取进入 repository |
| `services/worker_skills.py::authorized_skill` 的默认技能查询 | `WorkerTaskRepository.default_skill` | 租约和 Worker 身份校验仍在 service |

## 暂不迁移的纯读

以下文件在 2026-11-19 的扫描中只有读 SQL（没有写语句和提交）。它们保留在 service 的理由如下，迁移由后续工单 `68-service-read-migration` 跟踪。

| 文件 | 保留理由 |
| --- | --- |
| `services/code_risk_analysis.py` | GitLab 绑定与凭据读取和任务授权、仓库范围绑定在一起，拆到 repository 会重复授权语义 |
| `services/environment_access.py` | 环境变量读取同时执行项目与个人授权过滤，属于访问策略 |
| `services/integration_runtime.py` | 集成执行开关与运行代次读取属于跨服务运行策略 |
| `services/repository_profile_versions.py` | 多表 attempt 投影为不可变版本视图，属于读模型组装 |
| `services/stage_storage/chain_view.py` | 生成链全景由 stage/attempt/version 多表组装，属于读模型 |
| `services/stage_storage/version_views.py` | 版本详情包含上游版本与来源投影，属于读模型 |
| `services/stage_storage/views.py` | 阶段与 attempt 的展示投影，拆开会使视图规则分散 |
| `services/standalone_worker_authorization.py` | 独立执行的当前权限和租约检查属于授权策略 |
| `services/stored_file_access.py` | 文件资源归属与下载授权属于访问策略 |
| `services/ui_generation_source.py` | UI 生成源选择读取仓库画像与冻结 commit，属于领域选择规则 |
| `services/worker_domains/perf.py` | 读取与性能任务状态迁移交织，待 worker 域拆分时再迁移 |
| `services/worker_domains/ui.py` | 读取与 UI 步骤/运行状态迁移交织，待 worker 域拆分时再迁移 |
| `services/zentao_bindings.py` | 禅道绑定解析包含项目共享服务选择规则 |
| `services/zentao_mcp_authorization.py` | MCP 个人授权校验属于访问策略 |
| `services/zentao_mcp_selection.py` | 共享服务/绑定选择涉及跨成员凭据隔离规则 |

## 事务标记示例

```python
# transaction-bound: the linked-authorization check must see the same
# transaction as the update.
linked = await self.repository.session.scalar(...)
```

标记只说明边界，不表示可以把任意查询留在 service。新增可复用查询、列表筛选或分页仍应放入 repository。
