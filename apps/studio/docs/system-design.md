# TestPilot Studio 设计文档

## 1. 文档说明

本文档基于当前前端仓库代码反向梳理而成，描述 TestPilot Studio 的前端系统设计、模块职责、数据流转和当前实现边界。

- 文档范围：当前 React 前端工作台
- 技术基线：React 19、TypeScript、Vite、Ant Design、TanStack React Query、Zustand
- 现状说明：仓库根目录中的 `README.md` 仍为 Vite 模板内容，不能代表当前业务实现
- 设计原则：只描述代码中已经落地的能力；未完成模块明确标记为占位或待后端接入

## 2. 项目概览

TestPilot Studio 是一个围绕测试活动构建的前端工作台，核心目标是把项目、迭代、需求和多种测试资产组织在同一个协作界面内。当前前端的主线能力包括：

- 项目、迭代、需求管理
- 需求维度的测试工作台
- 功能测试集与功能测试用例编辑
- API 测试集、环境、用例、断言、提取规则和运行报告
- UI 测试集、步骤编排、调试运行、测试集运行报告
- AI 测试中的 API 用例生成任务管理
- 禅道连接管理与项目/迭代/需求绑定

从业务层级看，当前系统的核心实体关系为：

```text
Project
  -> Sprint
    -> Requirement
      -> FunctionTestSuite
      -> ApiCollection
      -> UiTestSuite

Project
  -> ApiEnvironment
  -> ApiCaseGenerateTask

User Scope
  -> LlmConnection

Project / Sprint / Requirement
  -> ZentaoBinding
```

## 3. 技术架构

### 3.1 应用壳层

应用入口位于 `src/app`，整体由三层组成：

- `AppRoutes`
  - 定义 `/login`、`/register` 和受保护业务路由入口
- `ProtectedRoute`
  - 检查登录态，未登录时跳转登录页
- `AppShell`
  - 提供左侧导航、顶部工具栏、项目切换器和业务内容区

`AppShell` 是业务工作台的统一容器，主导航固定为：

- 项目总览
- 测试
- AI 测试
- 基础服务

### 3.2 UI 层

UI 层以 Ant Design 为基础组件库，辅以大量业务样式文件实现工作台布局和卡片化交互。

- 组件来源
  - Ant Design：表单、弹窗、抽屉、分页、选择器、卡片、提示等
  - 自研共享组件：`PageFrame`、`JsonEditor`、`TextCodeEditor`、`TestPilotLogo`
- 样式组织
  - `src/app/styles`：全局布局、主题和工作台基础样式
  - `src/shared/styles`：共享组件样式
  - `src/features/*/styles`：各 feature 自有页面与组件样式

### 3.3 数据层

前端采用轻量 HTTP 封装加 React Query 的方式管理接口访问。

- `src/shared/api/request.ts`
  - 统一注入 `Authorization` token
  - 自动处理 JSON 请求头
  - 约定后端响应结构为 `ApiEnvelope<T>`
  - 在 `401` 或业务码 `1001` 时执行登出
- `src/services/api.ts`
  - 聚合各 feature 的 API 方法与导出类型
  - 对外暴露统一 `api` 对象
- 各业务模块的 `api/*.api.ts`
  - 按领域划分请求方法，避免把所有接口堆叠在全局文件中

### 3.4 状态层

当前状态管理遵循“服务端状态归 React Query、本地 UI 状态归 Zustand/组件 state”的分层原则。

- React Query
  - 负责项目、迭代、需求、测试集、测试用例、运行记录、环境等服务端状态
- Zustand
  - `auth.store.ts`：登录 token、当前用户、退出登录
  - `theme.store.ts`：明暗主题模式
  - `workbench.store.ts`：当前项目、部分工作台弹窗状态
- 组件局部状态
  - 负责当前页筛选条件、选中项、分页、抽屉开关、临时草稿等交互状态

## 4. 路由与页面结构

### 4.1 顶层路由

当前路由树的顶层入口如下：

- `/login`
- `/register`
- `/*` 进入受保护业务工作台

### 4.2 业务路由

业务工作台内部的主要页面如下：

| 路由 | 页面职责 |
| --- | --- |
| `/projects` | 项目总览页，管理项目、迭代、需求 |
| `/projects/:projectId` | 项目详情承接页 |
| `/projects/:projectId/sprints/:sprintId` | 迭代详情承接页 |
| `/projects/:projectId/sprints/:sprintId/requirements/:requirementId` | 需求测试工作台 |
| `/testing` | 测试主工作台，基于 `tab` 在功能/API/UI 间切换 |
| `/test-cases/suites/:suiteId` | 功能测试集详情页 |
| `/ai-testing` | AI 测试首页 |
| `/ai-testing/tasks` | API、功能与 UI 生成任务统一列表 |
| `/ai-testing/tasks/:taskId` | API 用例生成任务详情 |
| `/ai-testing/function-tasks/:taskId` | 功能用例生成任务详情 |
| `/ai-testing/ui-tasks/:taskId` | UI 用例生成任务详情与源码包、候选审核及正式套件导入工作区 |
| `/base-services` | 基础服务页 |
| `/api-automation/collections/:collectionId` | API 测试集详情页 |
| `/ui-automation/suites/:suiteId` | UI 测试集详情页 |
| `/profile` | 个人设置页 |

### 4.3 页面组织方式

页面分为两类：

- 工作台总览页
  - 如项目总览、测试首页、AI 测试首页、基础服务页
- 详情工作区页
  - 如需求测试工作台、API 测试集详情、UI 测试集详情、功能测试集详情

详情页普遍采用“左侧导航或列表 + 右侧编辑工作区 + 运行结果/报告”的结构，适合连续编辑和频繁切换测试资产。

## 5. 核心业务实体模型

### 5.1 项目域

- `Project`
  - 顶层业务容器
  - 作为全局项目选择器的数据来源
- `Sprint`
  - 隶属于项目
  - 用于组织需求和测试活动
- `Requirement`
  - 隶属于迭代
  - 是功能测试、API 测试、UI 测试的直接归属对象

### 5.2 功能测试域

- `FunctionTestSuite`
  - 隶属于需求
  - 作为功能测试用例的集合
- `FunctionTestCase`
  - 隶属于功能测试集
  - 包含模块、优先级、类型、前置条件、步骤、预期结果、排序号

### 5.3 API 自动化域

- `ApiEnvironment`
  - 隶属于项目
  - 保存 Base URL 和环境变量集合
- `ApiEnvironmentVar`
  - 隶属于运行环境
  - 用于请求模板和变量提取
- `ApiCollection`
  - 隶属于需求
  - 代表 API 测试集
- `ApiCase`
  - 隶属于 API 测试集
  - 包含方法、路径、请求头、Query、Body、超时、启用状态等
- `ApiAssertRule`
  - 隶属于 API 用例
  - 定义断言来源、比较器、预期值等
- `ApiExtractRule`
  - 隶属于 API 用例
  - 定义提取来源和变量写回规则
- `ApiCollectionRunReport`
  - 表示测试集运行后的汇总与明细报告

### 5.4 UI 自动化域

- `UiTestSuite`
  - 隶属于需求
  - 代表 UI 测试集
- `UiTestCase`
  - 隶属于 UI 测试集
  - 由多步骤编排构成
- `UiTestCaseRun`
  - 单用例调试运行记录
- `UiTestSuiteRunReport`
  - 测试集运行报告，包含用例级和步骤级结果

### 5.5 AI 测试域

- `ApiCaseGenerateTask`
  - 隶属于项目
  - 同时关联迭代和需求
  - 用于管理 OpenAPI/Swagger 来源的 API 用例生成任务
- `ApiCaseGenerateTaskRun`
  - 记录任务执行状态、快照、审核状态等
  - 运行时需要显式传入一个可用的 `LlmConnection.connectionId`
- `UiCaseGenerateTask`
  - 隶属于项目，同时关联迭代和必填需求
  - 以可替换的 `UiCaseSourceArchive` 作为唯一生成来源，不保存或展示 `sourceContent`
- `UiCaseSourceArchive`
  - 保存 ZIP 文件名、字节大小、SHA256 与上传时间元数据
  - 浏览器不读取或解压其源码内容
- `UiCaseGenerateTaskRun`
  - 记录 pending、claimed、running、success、failed 状态以及完整候选 YAML
  - 成功且待审核时允许编辑，批准或拒绝后冻结；审核与正式资产导入相互独立

### 5.6 基础服务域

- `LlmConnection`
  - 用户级 LLM 连接配置
  - 包含连接名称、请求地址、模型 ID、鉴权信息和连接状态
  - 作为 AI 测试任务运行时的模型连接来源
- `ZentaoConnection`
  - 禅道连接配置
- `ZentaoBinding`
  - 业务对象与禅道远端资源的映射
  - 绑定目标类型包括 `project`、`sprint`、`requirement`

## 6. 模块职责拆解

### 6.1 `projects`

职责：

- 项目 CRUD
- 迭代 CRUD
- 需求 CRUD
- 项目级项目选择上下文管理
- 禅道绑定入口

设计要点：

- `useActiveProject` 负责拉取项目列表并保证当前项目有效
- 页面内部通过卡片视图展示迭代和需求
- 需求列表支持按迭代筛选
- 项目、迭代、需求均可发起禅道绑定

### 6.2 `requirements`

职责：

- 提供需求级测试上下文容器
- 在同一需求下切换功能测试、API 测试、UI 测试
- 管理需求编辑与删除

设计要点：

- 通过路由参数携带 `projectId`、`sprintId`、`requirementId`
- 通过 `scope` 向下传递上下文，锁定子模块筛选范围

### 6.3 `test-cases`

职责：

- 管理功能测试集列表
- 编辑功能测试用例详情

设计要点：

- 功能测试集绑定到需求
- 详情页使用左右分栏编辑器模式
- 支持用例搜索、唯一标题校验、排序号编辑
- 当前未看到独立执行能力，主要侧重测试资产维护

### 6.4 `api-automation`

职责：

- 管理 API 测试集
- 管理 API 环境与环境变量
- 编辑 API 用例
- 管理断言与提取规则
- 执行单用例和测试集
- 查看运行历史与运行报告
- 导入 YAML 用例

设计要点：

- 测试集按需求组织，可在项目维度按迭代/需求筛选
- 运行测试集前依赖环境选择
- 详情页支持请求构造、动态变量插入、Body 编辑、后置操作管理
- 报告层包含汇总、明细、快照与 HTML 报告导出能力

### 6.5 `ui-automation`

职责：

- 管理 UI 测试集
- 编辑 UI 测试用例与步骤
- 单用例调试运行
- 测试集运行与报告查看
- 导入 YAML 用例

设计要点：

- 测试用例由步骤数组组成，支持步骤增删改与顺序调整
- 内置函数模板可插入到步骤字段中
- 调试运行展示步骤级结果
- 测试集报告展示用例级与步骤级执行结果

### 6.6 `ai-testing`

职责：

- 通过统一列表管理 API、功能与 UI 用例生成任务
- 查看任务运行记录
- 在任务运行前选择可用的 LLM 连接
- 管理 UI 任务的 ZIP 源码包、候选结果编辑和审核
- 将符合资格的已批准 UI 候选显式导入同需求下既有 UI 测试套件

设计要点：

- 三类生成任务使用同一列表，并以任务类型标签和来源列区分
- UI 任务创建采用“先创建任务、再上传 ZIP”的两请求流程；上传失败保留任务供详情页重试
- 源码包与运行服务端状态由 React Query 管理，本地文件、弹窗和 YAML 草稿保持为页面临时状态
- UI 候选使用 YAML 解析器做结构化预览，但保存始终提交完整原文，避免丢失未知字段
- 导入资格严格由运行成功、审核批准和待导入三项状态共同决定；导入状态以 `importStatus`、`importedTargets`、`importedAt` 为准
- 导入首次请求只预览冲突，后端零写入；确认请求使用同一套件并整批覆盖，前端完整保留和展示未知步骤字段
- 导入弹窗、套件选择与冲突快照属于页面临时状态；运行和套件服务端状态继续由 React Query 管理
- 列表页与详情页的“运行”操作都会先弹出 LLM 连接选择弹窗
- 仅允许选择状态为 `active` 的 LLM 连接
- 若没有可用连接，前端引导用户跳转到基础服务页完成配置

### 6.7 `base-services`

职责：

- 管理基础服务入口和集成模块
- 承接 LLM 连接管理
- 承接禅道连接管理
- 承接 GitLab 连接管理

设计要点：

- LLM 模块已具备连接列表、创建、编辑、删除、详情查看能力
- LLM 连接以用户维度组织，并被 AI 测试模块复用
- 禅道模块已具备连接列表、创建、编辑、删除、重新鉴权、详情查看
- GitLab 模块已具备连接列表、创建、编辑、删除、重新鉴权和详情查看能力

## 7. 数据流与状态流

### 7.1 登录态与请求注入

登录态流程如下：

1. 登录成功后把 token 写入 `localStorage`
2. `useAuthStore` 保存 token 与用户信息
3. 所有接口请求通过 `request` 自动注入 `Authorization: Bearer <token>`
4. 若接口返回 `401` 或业务码 `1001`，前端自动清空登录态并回到登录流程

### 7.2 当前项目上下文

当前项目是整个工作台的基础筛选条件。

- 顶部项目选择器来自 `useActiveProject`
- 若首次进入未选项目，默认选择第一个项目
- 若当前项目已不存在，会自动回退到最新有效项目
- 测试、AI 测试、基础服务等模块都会依赖这个上下文发起查询

### 7.3 筛选与 scope 传递

测试相关模块存在两种进入方式：

- 从 `/testing` 进入
  - 用户自行选择迭代和需求
- 从需求测试工作台进入
  - 子模块接收 `scope`
  - 当前需求和迭代会被锁定，不再允许用户切换到其他需求

这种设计保证了：

- 通用测试工作台适合横向管理多个需求
- 需求测试工作台适合围绕单个需求持续编辑

### 7.4 React Query 查询与失效策略

当前查询键以业务实体为中心进行组织，常见模式包括：

- `['projects']`
- `['sprints', projectId]`
- `['requirements', sprintId]`
- `['functionTestSuites', requirementId]`
- `['apiCollections', ...scope]`
- `['apiCases', collectionId]`
- `['uiTestCases', suiteId]`
- `['apiCaseGenerateTasks', projectId]`
- `['apiCaseGenerateTaskRuns', taskId]`
- `['llmConnections']`
- `['zentaoConnections']`

更新策略以“操作成功后失效对应列表查询”为主，局部详情会在成功后通过 `setQueryData` 进行缓存回写，兼顾列表刷新和详情联动。AI 测试任务运行成功后，还会联动失效任务详情、运行记录和任务列表缓存。

### 7.5 长耗时任务与轮询

当前有多类轮询场景：

- API 测试集运行历史和运行报告
- UI 单用例调试运行
- UI 测试集运行历史和运行报告
- AI 用例生成任务运行记录

轮询策略通常采用：

- 仅在页面已打开且存在有效运行 ID 时启用
- 运行状态结束后自动停止轮询

## 8. 外部系统与依赖边界

### 8.1 后端 API 约定

当前前端默认后端返回结构为：

```ts
type ApiEnvelope<T> = {
  code: number
  message: string
  data: T
}
```

这意味着：

- HTTP 200 不代表业务成功
- 只有 `response.ok` 且 `payload.code === 0` 才视为成功
- 失败信息以 `message` 为主

### 8.2 字段兼容策略

当前后端字段风格并不完全统一，前端对多处实体同时兼容：

- camelCase
- snake_case

因此项目中存在较多 `normalize*`、`pick*`、`build*Payload` 工具函数，用来：

- 读取兼容字段
- 构造差量更新参数
- 降低前端页面直接处理字段差异的复杂度

### 8.3 禅道集成边界

当前禅道集成已经是活跃模块，职责范围包括：

- 禅道连接配置管理
- 连接重新鉴权
- 业务对象与禅道资源绑定

但文档中不推断未在前端落地的同步策略、定时任务或远端流程，只将其视为“前端可配置和可绑定的外部系统”。

### 8.4 基础服务接入边界

当前基础服务中包含三类已接入的外部集成：

- 已接入的 LLM 模型服务
- 已接入的禅道服务
- 已接入的 GitLab 服务

其中，LLM 模型服务已经接入真实列表、详情、创建、编辑和删除接口，并被 AI 测试模块复用；禅道与 GitLab 服务均提供真实连接的列表、详情、创建、编辑、删除和重新鉴权能力。基础服务页不保存访问令牌明文，只依据服务端返回的脱敏状态展示连接是否已配置凭据。

## 9. 当前实现成熟度

### 9.1 已实现能力

- 登录态守卫、主题切换、项目上下文切换
- 项目/迭代/需求管理
- 需求测试工作台
- 功能测试集与功能测试用例编辑
- API 测试集列表、环境管理、用例编辑、断言、提取、运行报告、导入
- UI 测试集列表、步骤编排、调试运行、测试集报告、导入
- AI 测试中的 API、功能与 UI 用例生成任务管理
- UI 生成源码包上传与替换、运行轮询、候选 YAML 编辑和人工审核
- 已批准 UI 候选导入既有 UI 测试套件，包含冲突预览、整批覆盖确认和并发状态收敛
- AI 测试运行前的 LLM 连接选择流程
- 禅道连接管理与绑定入口
- LLM 连接管理

### 9.2 半实现或占位能力

- 项目详情页、迭代详情页更多业务深化能力未在当前代码中形成独立完整工作流
- 基础服务中的 GitLab 为待后端接入骨架
- 功能测试当前偏测试资产维护，未形成完整执行闭环

### 9.3 明确缺口

- 顶层 `README.md` 未反映真实业务形态
- 部分后端接口能力尚未齐备，因此前端保留空态模块
- 接口字段风格存在兼容成本
- 部分工作流已经可编辑和可查看，但是否具备完整后端执行闭环，需要以后端实际能力为准

## 10. 结论

当前 TestPilot Studio 前端已经不是通用模板项目，而是一个具备明确测试平台结构的业务工作台。其设计核心是：

- 用项目、迭代、需求组织测试资产
- 用统一工作台承接功能、API、UI、AI 和外部集成能力
- 用 React Query 管理服务端状态，用 Zustand 承接全局本地状态
- 对已实现能力与待接入能力进行明确分层

后续若继续完善文档，建议优先补充：

- 后端接口契约文档
- 测试数据模型字典
- 禅道、LLM、GitLab 的集成流程文档
- 关键运行报告字段说明
