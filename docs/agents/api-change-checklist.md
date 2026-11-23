# 响应字段兼容检查清单

- 状态：现行
- 负责人：backend maintainers
- 最近复核：2026-11-19
- 复核周期：每季度
- 适用范围：控制面 HTTP/Worker 协议、各 Worker 回传与快照、Studio 消费方
- 变更/废弃：按[规范变更检查清单](domain.md#规范变更检查清单)执行；跨项目契约变化先记录 ADR 并通知消费方。

本清单用于控制面响应字段、状态值、错误格式、分页行为或 Worker 协议发生变化时，证明 Studio、Worker、历史导入文件和已保存任务快照的消费方式都已核对。规则依据见[通用后端接口演进与兼容](backend-development.md#接口演进与兼容)和[控制面接口规则](../control-plane/development-rules.md)。

## 何时必须使用

出现以下任一变化时，在实现前完成本清单，并在交付说明或提交说明中记录结果：

- 新增、删除、重命名响应字段，或修改类型、可空性、默认值、字段含义。
- 新增、删除或调整状态值、错误码、HTTP 状态。
- 修改分页字段、排序、总数语义或列表/详情拆分。
- 修改 Worker 领取、快照、心跳、完成回传、停止或错误回传协议。
- 修改被历史导入文件、任务快照、运行账本或审计 JSON 持久化的结构。
- 修改 Studio 与后端共享的导入格式、产物结构或别名。

只改内部实现、不改变对外结构且不改变持久化格式时，不需要填写本清单。

## 必查消费方

| 消费方 | 必须核对 | 典型位置 |
| --- | --- | --- |
| 控制面生产方 | `response_model`、序列化 alias、错误格式、状态机、分页语义 | `routers/`、`schemas/`、`handlers/`、`services/` |
| Studio | TypeScript 类型、API 模块、缺省/空值处理、筛选/统计/展示、缓存失效 | `apps/studio/src/features/*/api`、`types.ts`、页面/hooks |
| 对应 Worker | 领取、快照、心跳、完成回传、`stop_reason`、错误分类、协议解析 | `apps/*-worker/src/**/control_plane`、poller/runner |
| 历史导入文件 | 旧字段是否仍可读、未知字段是否拒绝、缺省值是否可推导 | 禅道/GitLab/OpenAPI 导入、fixture |
| 已保存任务快照 | 旧快照能否反序列化、缺省字段、状态值是否仍被识别 | 任务 `snapshotJson`、运行记录、审计/账本 JSON |
| 文档与契约测试 | README、开发规则、ADR、OpenAPI/契约样例是否同步 | `docs/<project>/`、`tests/test_*contract*.py` |

## 核对步骤

1. **列出变化**：字段/状态/错误码名称、旧值、新值、默认值、是否可空、是否必填。
2. **定位生产方**：确认唯一序列化入口，避免 handler 各自转换 alias。
3. **搜索 Studio 消费方**：按字段名、状态值、接口路径搜索类型、API 模块和页面；确认缺省、`null`、空数组、未知状态的展示与筛选。
4. **搜索 Worker 消费方**：四个 Worker 分别检查各自协议解析；确认旧 Worker 不发送新字段时控制面仍可处理，新 Worker 发送新字段时旧控制面不会误判。
5. **检查历史数据**：用旧 fixture/快照/导入文件验证读取；明确未知字段是拒绝还是忽略，不能依赖“测试环境恰好没有旧数据”。
6. **选择兼容策略**：新增可选字段定义缺省；删除/重命名使用兼容读取或过渡别名；状态值保留旧值解析或给出迁移范围；破坏性变化使用版本化方案。
7. **补验证**：至少运行受影响项目的契约测试和项目测试；跨项目协议同时验证生产方与消费方。
8. **记录结果**：把下表写入交付说明、PR 描述或提交说明；没有完成的项写“未验证”及原因。

## 交付记录模板

```markdown
### 响应字段兼容核对

- 变化字段/状态：
- 生产方：
- Studio 消费方：
- Worker 消费方：
- 历史导入：
- 已保存快照：
- 兼容策略（缺省/别名/版本/迁移范围）：
- 验证命令与结果：
- 未验证范围及原因：
```

## 示例：工单 42 停止状态分类

工单 42 调整 perf-worker 完成回传的停止状态，属于状态值变化，可按本清单核对：

- 变化：`stopped` 与 `canceled` 的触发条件；不新增字段。
- 生产方：`perf-worker` 的 `worker/poller.py`，按 `stop_reason` 选择状态。
- Studio 消费方：运行详情按既有状态词汇展示；没有新增展示分支。
- Worker 消费方：控制面完成接口已支持 `stopped`，无需扩展状态词汇；其他 Worker 不受影响。
- 历史导入/快照：不涉及导入格式；历史运行记录保留原状态值。
- 兼容策略：保留 `canceled` 原语义，`stopped` 仅用于 Worker 关闭和租约丢失。
- 验证：perf-worker 全量测试 103 项通过；控制面实时执行文档同步。
- 未验证：真实 SIGTERM 部署环境仍需在目标环境复验。

## 验证入口

```bash
# 控制面契约
cd apps/control-plane && uv run --locked --extra dev pytest tests/test_app_contract.py tests/test_go_field_contracts.py tests/test_full_route_parity.py tests/test_worker_contract.py -q

# 受影响 Worker / Studio 按项目命令矩阵执行
cd apps/<project> && <项目全量测试命令>
cd apps/studio && npm run verify
```

真实 MySQL、S3、禅道/GitLab、浏览器、LLM、Prometheus 的验收不能由 SQLite、模拟 HTTP 或 fixture 代替；相关项在“未验证范围”中单独说明。
