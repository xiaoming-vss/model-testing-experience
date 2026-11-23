# 请求契约：未知字段与更新三态

- 状态：现行
- 负责人：control-plane maintainer
- 最近复核：2026-11-19
- 复核周期：每季度
- 适用范围：`apps/control-plane/src/testing_agent/schemas/` 与 HTTP 更新入口
- 变更/废弃：按[规范变更检查清单](../agents/domain.md#规范变更检查清单)执行；影响 Studio/Worker 请求体时先通知消费方。

浏览器请求和 Worker 内部请求都通过 Pydantic 模型校验。请求模型默认拒绝未声明字段；更新请求必须区分“未提交”“显式 null”和“空字符串”。

## 未知字段

`schemas/common.py::StrictRequest` 设置 `extra="forbid"`。新增请求模型应继承它，或在自己的 `model_config` 中声明 `extra="forbid"`。FastAPI 的 `RequestValidationError` 统一映射为 HTTP 400 和 `code=400`。

历史上允许扩展字段的 AI 任务协议保留 `extra="allow"`，由任务域校验载荷：

| 模型 | 保留理由 |
| --- | --- |
| `CodeRiskAnalysisTaskRequest` | 代码风险任务载荷由任务域解析 |
| `RepositoryProfileTaskRequest` | 仓库画像任务载荷由任务域解析 |
| `TestReportGenerateTaskRunRequest` | 测试报告任务载荷由任务域解析 |

其他请求模型新增或修改后必须使用 `extra="forbid"`。`tests/test_request_contract.py` 会导入全部 schema 模型并检查这一点，例外只承认上表。

## 更新三态

| 请求 | 含义 |
| --- | --- |
| 字段未提交 | 保持当前值 |
| 显式 `null` | 只有声明为可清空的字段才允许；其他字段返回 400 |
| 空字符串 | 只有业务定义为清空的字段才允许；其他字段按各自校验处理 |

实现约定：

- Handler 对字典型更新调用 `model_dump(..., exclude_unset=True)`，不把未提交字段传给 service。
- Service 对请求对象使用 `body.model_fields_set` 判断是否提交，不用 `is not None` 代替。
- `services/common.py::apply_patch` 默认拒绝 `None`；确实允许 null 清空的字段通过 `nullable` 参数显式登记。
- 可清空字段在 schema docstring 中说明；创建请求的 `exclude_none` 载荷不在此约定内，创建接口必须显式定义缺省值。

已按此约定处理的更新入口：

| 入口 | 判定方式 |
| --- | --- |
| API 用例/集合/环境/变量/断言/提取规则 | `exclude_unset` + `apply_patch` |
| Bug 编辑 | `exclude_unset`；`plannedFixSprintId`/`requirementId` 允许 null 或空串清空，其余 null 拒绝 |
| 功能用例/功能测试集、UI 用例/UI 测试集 | `exclude_unset` + `apply_patch` |
| 测试单、执行条目 | `exclude_unset` + `apply_patch` |
| 资源绑定、集成连接 | `exclude_unset`；连接显式 null 统一拒绝 |
| 项目、需求、迭代、个人资料 | `model_fields_set`，非可清空字段拒绝 null |
| 需求软件仓库绑定 | `model_fields_set`，分支字段拒绝 null |
| 监控连接、API 接口库、软件仓库、性能用例/测试集 | 已有 `model_fields_set` 实现 |

新增更新入口必须按上表任一模式实现，并在 `test_request_contract.py` 或对应业务测试中覆盖未知字段、缺省、null 和空串。

## 契约测试

```sh
cd apps/control-plane
uv run --locked --extra dev pytest tests/test_request_contract.py tests/test_architecture_layers.py -q
```

`test_request_contract.py` 覆盖：

- 所有请求模型的 `extra` 策略及例外清单；
- 未知字段校验失败；
- HTTP 未知字段返回 400；
- 项目 PATCH 的缺省保持、空串清空、null 拒绝。

本次没有新增响应字段；Studio 与 Worker 只需保证不再发送未声明的请求字段。
