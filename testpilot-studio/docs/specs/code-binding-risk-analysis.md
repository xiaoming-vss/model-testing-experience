# 模块需求:testpilot-studio(前端工作台)

Feature: `code-binding-risk-analysis`

> 来源:本文件复制自 `.scratch/code-binding-risk-analysis/03-testpilot-studio.md`;该 feature 的完整文档集(00 总览 / 01 control-plane / 02 ai-worker / 04 决策记录)在 `.scratch/code-binding-risk-analysis/` 下,修改需两边同步。
>
> 条目级报告契约决策见 `docs/adr/0001-risk-analysis-report-contract.md`(2026-08-26 质询定稿)。

## 范围

新增四块 UI:项目 GitLab 群组绑定、需求代码绑定(仓库/分支/基线)、代码风险分析任务与报告页、迭代代码概览。

## 需求条目

### RS-1 项目主页:GitLab 群组绑定

- `ProjectsPage` 增加「GitLab 群组绑定」入口,与禅道绑定入口并列;**平行实现**新的 `GitlabBindingModal`/`GitlabBindingSummary`(放 base-services,与 `ZentaoBindingPanel` 并列),级联选择骨架仅作模式参考,不改动禅道绑定代码。
- 流程:选择 GitLab 连接(连接列表仅返回**当前用户自己的**连接;无连接时提示先去基础服务页创建)→ 实时搜索群组(含子群组)→ 多选保存(每个群组单独创建;已绑定的群组在搜索结果中标记并禁选,3503 兜底提示)。
- 绑定列表展示:群组名、绑定状态(`status`/`lastSyncError`);**创建者不展示**(后端绑定响应无创建者字段,见接口备注);**本人连接上的绑定**额外展示连接状态(`status`/`lastAuthError`),失效时提示并可接管;他人连接的绑定连接状态不可见,接管按钮仍可用。
- 支持解除绑定(被需求绑定引用时展示 3506 受影响清单)与接管(切换 `connection_id` 为自己的连接)。

验收标准:

- [ ] 完整绑定 / 解绑 / 接管流程可用
- [ ] 群组选择支持实时搜索与分页
- [ ] 连接失效有明确提示且可接管(口径:**本人连接上的绑定**;他人连接的绑定前端无法读取连接状态)

### RS-2 需求代码绑定弹窗

- 需求列表行操作新增「代码绑定」入口(与禅道绑定并列),打开 `RequirementCodeBindingModal`(平行实现,样式与交互参照 `ZentaoBindingModal`;可作用于任意需求,不受编辑模式限制):
  - 弹窗内展示当前需求已绑仓库列表(仓库名 + 分支 + 基线分支),支持切换分支、设置/清除基线分支、删除;
  - **添加代码绑定**:仓库下拉——限项目所绑群组(含子群组)内的仓库,由前端聚合所有已绑群组的仓库 + 本地防抖搜索(后端仓库接口无 search 参数,见接口备注);
  - 分支下拉:依赖所选仓库,服务端实时搜索,**必选**(选了仓库必须选分支,未选不可添加);
  - 基线分支:可选字段,设置后直接作为基线(提示:设置后不再自动查找历史迭代);
  - 一个需求可绑多个仓库;**弹窗内增删改即时生效**(各条增/改分支/改基线/删分别直接调 API)。
- 项目未绑任何群组时,弹窗提示先去项目主页绑定群组。

验收标准:

- [ ] 需求绑定增删改完整可用,弹窗内即时生效
- [ ] 仓库/分支级联正确,未选分支不可添加(前端拦截 + 后端 3504 兜底)
- [ ] 仓库下拉覆盖项目所有已绑群组(含子群组)的仓库,本地搜索与滚动/按钮加载更多可用
- [ ] 基线分支为可选项,填写后保存,并提示「设置后不再自动查找历史迭代」
- [ ] 行操作「代码绑定」入口与禅道绑定并列,弹窗交互参照 ZentaoBindingModal

### RS-3 风险分析任务创建

- ai-testing 任务列表「新建任务」→ 选择「代码风险分析」模板 → 抽屉创建任务(**与其他任务类型一致**:任务名称必填、所属迭代可选(筛选)、所属需求必选、补充指令可选);创建成功进入任务列表,点击行进入详情页;**运行在详情页手动发起**,需求代码绑定弹窗不承载发起入口。
- 前端校验:所选需求未绑定任何仓库时,保存按钮禁用并提示「请先到需求列表做代码绑定」。

验收标准:

- [ ] 新建任务流程与其他任务类型一致(模板入口/抽屉/列表)
- [ ] 未绑定仓库的需求:保存按钮禁用并提示先去绑定
- [ ] 重复创建允许,每次生成独立任务记录
- [ ] 代码绑定弹窗只做绑定管理,无发起入口

### RS-4 ai-testing:新任务类型列表与报告页

- ai-testing 增加 `code_risk_analysis` 任务列表/详情页(复用现有任务页框架):`UnifiedAiTestingPage` 新增 kind `codeRisk` 行,详情路由 `/ai-testing/code-risk-tasks/:taskId`;「发起运行」按钮复用 `LlmConnectionSelectModal`(选择 LLM 连接)→ `POST /run` → 轮询运行详情(参考功能用例页 5s 间隔)直至成功/失败;多 run 历史可切换(默认最近一次),失败可重新发起运行。
- 报告页展示四区块(**条目级字段契约见 ADR-0001,worker 按此实装**):
  - 变更概览:全局汇总(`changeOverview`: filesChanged/additions/deletions)+ **按仓库明细行**(`repositories[]` 条目携带同名字段);
  - 风险点清单(等级色标:high 红 / medium 橙 / low 蓝,未知值灰 + 位置 + 理由);
  - 受影响已有用例(用例名 + 所属套件/集合 + 影响说明;字段 caseType/caseId/title/suiteId/suiteName/impact);
  - 覆盖缺口与建议新增测试点(gap/suggestion)。
- 报告标注:各仓库基线 commit 与 head SHA、分析时间;失败态展示错误消息与补救建议(`report` 为 `null` 时回退展示 `resultYaml` 原文)。

验收标准:

- [ ] 报告四区块正确渲染
- [ ] SHA 与分析时间展示
- [ ] 失败任务展示错误与补救建议
- [ ] 发起运行 / 轮询 / 重跑流程可用,多 run 历史可切换

### RS-5 迭代代码概览

- 迭代总览 `SprintDetailPage` 新增「代码变更」区块:本迭代内需求绑定的仓库/分支列表(按仓库去重),每仓库展示 commits 数、增删行数、基线信息、「新增仓库」标记;统计失败的单仓库展示错误与补救建议。
- 打开页面时拉取 + 手动刷新按钮。

验收标准:

- [ ] 迭代概览正确渲染,空态/错误态完整
- [ ] 变更量口径与风险报告页一致
- [ ] 手动刷新可用

## 依赖

- control-plane RC-1/RC-2(绑定 API 与资源代理端点)、RC-4/RC-5(任务与报告接口)、RC-6(变更概览接口)。

## 明确不做

- 不做性能测试相关 UI(单独立项);
- 不做 commit 级变更查看器(仅 diffstat + 风险报告);
- 不做项目级代码概览(仅迭代概览;项目可能多迭代并行,「当前迭代」口径不清)。

## 接口交接信息(control-plane 后端,2026-08-25)

> 后端 8 张工单(01~08)已完成,以下为 RS-1~RS-5 所需接口契约。所有接口位于 `/v1` 前缀下,以联调环境 `/v1/openapi.json`(或 `/docs`)为准;响应统一 `{code, message, data}` 包裹,成功 `code=0`;字段一律 camelCase;鉴权沿用现有用户 token(项目内所有用户可见可用)。

### 通用错误码

| code | 含义 | HTTP |
| --- | --- | --- |
| 3401 | 集成连接不存在 | 404 |
| 3403 | 集成连接鉴权失败(含凭据解密失败) | 400 |
| 3405 | GitLab 远端资源不可用 | 400 |
| 3501 | 资源绑定不存在 | 404 |
| 3503 | 该远端资源已被绑定 | 409 |
| 3504 | 绑定关系不合法(仓库不在已绑群组范围内 / 缺 branch) | 400 |
| 3506 | 仍有需求代码绑定引用该群组(删除被阻止,data 携带受影响绑定清单) | 409 |
| 400/401/403/404/500 | 通用错误 | 对应状态码 |

### RS-1 项目 GitLab 群组绑定

| 用途 | 接口 |
| --- | --- |
| 连接列表(含接管入口) | `GET /projects/{projectId}/integrations/gitlab/connections` |
| 创建连接 | `POST /projects/{projectId}/integrations/gitlab/connections`,body `{name, baseUrl, accessToken}` |
| 群组搜索(含子群组,实时搜索+分页) | `GET /projects/{projectId}/integrations/gitlab/connections/{connectionId}/groups?search=&page=&pageSize=` |
| 绑定列表 | `GET /projects/{projectId}/bindings` |
| 创建绑定 | `POST /projects/{projectId}/bindings` |
| 接管(切换 connectionId) | `PATCH /projects/{projectId}/bindings/{bindingId}`,body `{connectionId}` |
| 解绑 | `DELETE /projects/{projectId}/bindings/{bindingId}` |

- 群组条目:`{id, name, fullPath, parentId, description, webUrl}`;`pageSize` 上限 100。
- 创建绑定 body:`{provider:"gitlab", connectionId, remoteResourceType:"group", remoteResourceId, remoteNameSnapshot}`(`remoteParentId` 留空)。
- 绑定响应:`{bindingId, provider, connectionId, localResourceType, localResourceId, remoteResourceType, remoteResourceId, remoteParentId, remoteNameSnapshot, status, boundAt, lastVerifiedAt, lastSyncError, createdAt, updatedAt}`。
- 连接失效提示:看连接的 `status`/`lastAuthError`(仅本人连接可读);群组绑定同步失败看 `lastSyncError`。解绑被需求绑定引用的群组返回 3506 + 受影响绑定清单,需展示提示(清单项含仓库 snapshot 与分支;前端 join 本地需求列表取需求名,取不到时展示需求 id)。
- ⚠️ 绑定响应**无创建者字段**(`user_id` 未暴露),连接列表接口仅返回**当前用户自己的**连接——前端降级:绑定列表不展示创建者;他人连接上的绑定无法判断连接失效(仅展示绑定自身 `status`/`lastSyncError`)。

### RS-2 需求抽屉代码绑定

| 用途 | 接口 |
| --- | --- |
| 仓库列表(限群组内,含子群组仓库) | `GET /projects/{projectId}/integrations/gitlab/connections/{connectionId}/groups/{groupId}/repositories?page=&pageSize=` |
| 分支搜索 | `GET /projects/{projectId}/integrations/gitlab/connections/{connectionId}/repositories/{repositoryId}/branches?search=&page=&pageSize=` |
| 需求绑定列表 | `GET /requirements/{requirementId}/bindings` |
| 创建绑定 | `POST /requirements/{requirementId}/bindings` |
| 更新(改分支/基线) | `PATCH /requirements/{requirementId}/bindings/{bindingId}`,body `{branch?, baselineBranch?}`(只传要改的字段) |
| 删除绑定 | `DELETE /requirements/{requirementId}/bindings/{bindingId}` |

- 仓库条目:`{id, name, path, pathWithNamespace, namespaceFullPath, defaultBranch, webUrl}`;分支条目:`{name, isDefault, isProtected, commitId, commitTitle}`。
- 创建绑定 body:`{provider:"gitlab", remoteResourceType:"repository", remoteResourceId, remoteParentId(群组id), remoteNameSnapshot, extraJson:{branch, baselineBranch?}}`——**不传 connectionId**(凭据经所属群组绑定解析)。
- 校验:仓库不在项目已绑群组范围内 → 3504「仓库不在项目已绑群组范围内」;**branch 必填** → 3504「绑定仓库必须携带 branch」。绑定响应额外带 `branch`、`baselineBranch`。
- 前端需自行实现「未选分支不可保存」「项目未绑任何群组时区块提示先去项目主页绑定」「区块仅编辑模式显示/块内即时保存」。
- ⚠️ 仓库列表接口**无 `search` 参数**(仅 `page`/`pageSize`)——仓库「实时搜索」由前端实现:按已绑群组逐个拉取(每页 100,滚动到底加载下一页),客户端防抖过滤;聚合时记录各仓库来源群组 id,作为创建需求绑定的 `remoteParentId`。
- ⚠️ `groupId`/`repositoryId` 支持数字 id 或 URL 编码 path(如 `team%2Finfra`),传 path 时需 `encodeURIComponent`(后端路由以 `:path` 转换器支持斜杠解码)。

### RS-3 风险分析发起

- `POST /projects/{projectId}/code-risk-analysis-tasks`,body `{name?, requirementId, instruction?}` → 任务 `{taskId, taskType:"code_risk_analysis", name, projectId, sprintId, requirementId, creatorUserId, sourceType, sourceContent, instruction, createdAt, updatedAt}`。
- 重复发起允许,每次生成独立任务记录;需求无仓库绑定时按钮禁用(前端按需求绑定列表判空)。
- 前端仅创建任务并跳转详情页;运行在详情页「发起运行」(`POST .../{taskId}/run`)。

### RS-4 任务列表/详情与报告页

| 用途 | 接口 |
| --- | --- |
| 任务列表 | `GET /projects/{projectId}/code-risk-analysis-tasks` |
| 任务详情 | `GET /code-risk-analysis-tasks/{taskId}` |
| 发起运行 | `POST /code-risk-analysis-tasks/{taskId}/run`,body `{llmConnectionId, instruction?, triggerType?}` |
| 运行列表 | `GET /code-risk-analysis-tasks/{taskId}/runs` |
| 运行详情(报告) | `GET /code-risk-analysis-runs/{runId}` |

- 运行响应 = 通用 run 字段(`runId, taskId, status, currentStage, stageStatus, errorMessage, remediation, resultYaml, triggerType, createdAt...`)+ 解析后的 `report` 结构(条目级契约见 ADR-0001):
  - `report.analyzedAt`:分析时间;
  - `report.repositories[]`:每仓库 `{repositoryId, branch, baselineCommit, headCommit, filesChanged, additions, deletions}`;
  - `report.changeOverview`:`{filesChanged, additions, deletions}` 全局汇总(不按仓库分组);
  - `report.risks[]`:风险点清单 `{level, location, reason}`(level 取 high/medium/low);
  - `report.affectedCases[]`:受影响已有用例 `{caseType, caseId, title, suiteId, suiteName, impact}`;
  - `report.coverageGaps[]`:覆盖缺口与建议 `{gap, suggestion}`。
- 失败态:展示 `errorMessage` + `remediation`;`report` 为 `null` 时回退展示 `resultYaml` 原文。
- ⚠️ 条目级字段由本规范 + ADR-0001 定义(worker 按此实装),后端只做宽类型透传 + 结构校验、不改字段名;报告字段需与 `.scratch/code-binding-risk-analysis/02-ai-worker.md` 同步。

### RS-5 迭代代码概览

- `GET /sprints/{sprintId}/code-overview` → `{sprintId, projectId, generatedAt, repositories[]}`。
- 每仓库条目:`{repositoryId, name, groupId, branch, baselineRef, baselineNote, isNewRepository, commitsCount, additions, deletions, error, remediation}`。
- 单仓库统计失败:仅该仓库 `error`/`remediation` 非空,整体仍返回 200;无绑定返回空 `repositories`。
- 后端有 5 分钟短缓存(绑定变更自动失效),前端「手动刷新」直接重新请求即可;无绑定展示空态,单仓库统计失败仅展示该仓库 `error`/`remediation`。
