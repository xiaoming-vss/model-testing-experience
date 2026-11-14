# 单用例图解实现与验证记录

日期：2026-11-14。代码已完成，未向业务环境部署；真实模型与人工语义验收尚未完成。

## 交付范围

- 1.0 JSON Schema、来源与身份校验、四类图块及受限数值范围；控制面与 Worker 独立打包，校验副本一致性。
- 单条生成、重新生成、失败重试、当前有效图解与最新任务分离；部分图解可用、unsupported 不覆盖旧结果。
- 权限、本人模型授权、请求幂等、活跃任务去重、迟到回传、条目/测试单/来源用例删除清理。
- 固定集合的批量提交回执、逐条结果、默认跳过已有图解、跨页勾选及当前页全选；筛选变化清空并提示。
- Studio 四类图形、原文定位、步骤联动、部分覆盖、文字回退及本次浏览偏好；不新增步骤判定和图解有误反馈。
- 迁移 `20261114_0003`、默认 Skill、50 条候选评估样本及人工质量门槛脚本。

## 已执行检查

| 检查 | 结果与范围 |
| --- | --- |
| 控制面定向回归 | 172 passed、2 skipped。覆盖图解协议/API、原有 HTTP/字段/Worker 契约、架构、权限、项目成员、开发成员、SQLite 迁移/注释、队列停止及资源删除。 |
| 真实 MySQL 图解专项 | 4 passed。一次性独立 MySQL 8.4 容器：三组并发派发与完成/删除交错，以及本次迁移升级/降级/再升级。未连接业务库。 |
| Worker 全量 unittest | 473 tests，OK，5 skipped。包含新任务的无工具执行、输入篡改、Skill 缺失、非法输出和 unsupported。 |
| Studio 定向 Vitest | 五文件 23 项通过，含四类渲染、模式切换、原文定位、批量选择冻结及上限、既有工作台和窗口 hook。 |
| 控制面类型检查 | 新增的 9 个业务模块 mypy 通过。 |
| 协议同步及 wheel | 同步检查通过；两个应用 wheel 都包含各自的 `output.schema.json`。 |
| 仓库 unittest | 38 tests，OK，4 skipped，包含新增的质量门槛脚本测试。 |
| 浏览器组件夹具 | 1440×1000 浅色、390×844 窄屏、1440×1000 深色；四类图解均可定位原文，无页面级横向溢出、无 pageerror。 |
| 独立界面复核 | 深色链接问题由错误的夹具主题配置造成；改为产品 ThemeProvider 后复核 resolved，ship 仅针对该修复。文字对比度正常约 6.85:1、点击后约 5.64:1。 |
| 文档与差异 | 本任务文档链接、JSON 语法、工单依赖及 `git diff --check` 检查。 |

控制面主要命令（在 `apps/control-plane`）：

```sh
uv run --locked --extra dev python -m pytest tests/test_case_visualization_contract.py tests/test_case_visualization_api.py tests/test_app_contract.py tests/test_go_field_contracts.py tests/test_full_route_parity.py tests/test_worker_contract.py tests/test_architecture_layers.py tests/test_auth_contract.py tests/test_project_membership_api.py tests/test_developer_access.py tests/test_initial_schema_migration.py tests/test_schema_comments.py tests/test_realtime_stop_and_queue.py tests/test_hard_deletion.py -q
```

真实 MySQL 使用显式指定的空测试库和 `tests/test_case_visualization_mysql.py`，测试库以 `_test` 结尾。不能直接把示例测试 URL 改成业务库执行。

## 发现并处理的问题

- MySQL 删除联表锁提前锁住绑定，与回调的队列/阶段锁形成死锁。新增稳定任务的 `execution_entry_id` 索引字段，删除先锁所属条目，再单表读取任务、清理队列，然后清理尝试/绑定。三组真实竞态均通过。
- 已完成图解的重复回调不应受旧租约状态阻止；新任务终态回调仅在 Worker/尝试身份匹配时确认收到，不重新发布或更改结果。
- 批量/摘要查询避免逐条读取大产物：有界集合查询仅取任务摘要，正文在单条详情读取。
- 真实 SDK 的工具控制在 adapter 内实现；Nanobot 显式禁用 MCP provider，避免只清工具列表但仍连接外部工具服务。

## 未通过或未完成的验证

- 首次 `npm run verify` 曾因接口库并行改动中的未使用导入停止；复跑时该问题已不再存在，完整 verify 已通过。本任务未改写该接口库文件。此条保留排查过程，不作为当前阻塞。
- 扩大执行 MySQL 原有完整初始化测试时，44 passed、2 failed：接口库迁移降级删除 `idx_api_interface_requirement_req` 时受外键约束阻止；原有 GitLab 群组删除/绑定竞态测试等待验证事件超时。本次迁移自身的完整 roundtrip 已通过。已移除该显式索引删除（`DROP TABLE` 会随表移除索引），MySQL 降级尚未复跑；GitLab 竞态超时仍未定位。
- 浏览器证据来自挂载真实组件、固定 API 响应的夹具，不代表完整登录后的工作台端到端，也不代表真实模型输出已正确。文件位于仓库本地 `.scratch/test-order-case-visualization/browser/`。
- 50 条样本均为待人工确认的候选；没有伪造评审人、模型输出或通过率。当前质量门槛脚本报告 reviewComplete=false、passed=false。需要用户指定测试项目、本人的模型连接及人工评审人后完成。
- 未执行业务部署、业务库迁移、系统默认 Skill 发布；部署步骤见 [Worker 说明](../ai-worker/case-visualization.md)。

## 最终补记

- 本功能涉及的 Studio 文件 ESLint 通过；公共主题检查通过（111 CSS、391 TS/TSX），Vite 构建通过。构建提示大 chunk 警告。
- 控制面新增业务模块 mypy 通过，相关 Ruff 检查通过；Worker 新模块及适配器 Ruff 检查通过。Schema 及 fixture 同步检查通过。
- 浏览器复核已使用产品 ThemeProvider；本地证据夹具副本已同步，临时应用预览入口已移除。
- 最终 `npm run verify` 通过（类型检查、全量 ESLint、主题检查和构建）；其他模块仍有 6 条 hooks 警告，无错误。
- 最终 Worker 全量复跑仍为 473 tests、OK、5 skipped；前端定向复跑为 23 passed。
- 临时 Vite 服务与独立 MySQL 容器在验证后关闭；工作区保留源码、文档和本地证据，不保留应用内临时预览入口。
