# AI 测试任务 Worker

本上下文负责接收平台派发的 AI 测试任务，并生成可回传平台的测试产物。它是拉取式 Worker，不监听端口。

## Language

**源码归档**：
`ui_case_generate` 任务携带的 ZIP 格式前端源码文件，通过 `sourceArchiveDownloadUrl` 获取；其解压后的根目录是 UI 用例生成技能的源码输入。
_Avoid_: 源码文件、下载包

**UI 测试用例**：
由 `ui_case_generate` 生成的可执行 UI 自动化用例；任务产物是 YAML 顶层列表，每一项均包含 `name`、`enabled`、`stepsJson` 和 `orderNo`。
_Avoid_: UI 用例 JSON、测试步骤列表

**用例编号**：
功能用例产物中的 `case_id`，由平台在生成校验通过后分配，UUID，跨所有用例集唯一，代表用例身份。修订时按「同模块 + 标题」→「同模块 + 内容」→「同模块 + 相对顺序」依次认回旧用例：编辑不改编号，只有用例被删除时其编号才随之消失，且永不复用。技能或模型输出的同名值一律丢弃。
_Avoid_: 模型生成的编号、集合内顺序编号

**技能预置**：
部署侧按项目把技能包（`SKILL.md`）放进该项目的 workspace `skills/` 目录，作为任务执行的前置条件；worker 不下载、不更新技能。
_Avoid_: 技能同步（worker 侧下载机制，已移除）

**代码绑定**：
需求与（仓库 + 分支）的关联，可绑多个；代码风险分析按绑定计算代码差异。区别于「项目群组绑定」。
_Avoid_: 需求绑定

**需求理解记录**：
需求分析任务经三步技能链产出的最终需求理解文本；代码风险分析的需求输入必须是它，而非原始需求文档。
_Avoid_: 增强文本

**现有测试内容**：
代码风险分析快照输入中，该需求下全部功能/API/UI 用例的定义与执行状态（API/UI 取最近一次 run）；模型据此判断影响面。
_Avoid_: 受影响用例（那是输出子集，勿与输入混用）

**受影响用例**：
风险分析报告中标出的、被代码改动影响的已有用例子集。
_Avoid_: 受影响测试、被影响用例

## 任务类型

`worker/dispatcher.py` 分派七种任务，未知类型返回 `不支持的任务类型: <type>`：

`requirement_analysis`、`functional_case_generate`、`api_case_generate`、`ui_case_generate`、`code_risk_analysis`、`test_report_generate`、`test_order_graph`

`test_order_graph` 的图谱输入由控制端组装（需求、用例、需求用例关联）经 `configJson.graphInput` 传入，`cases[]` 字段名与 `analyze-test-case-relations` 的输入契约一致，因此不需要转换层。当前执行体返回 mock 空图谱，真实图谱分析逻辑待定稿后替换 `tasks/test_order_graph/executor.py` 的 `run_graph_analysis`。
