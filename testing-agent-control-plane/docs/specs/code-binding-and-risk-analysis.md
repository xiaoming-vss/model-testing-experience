# 模块需求:testing-agent-control-plane(控制面)

Feature: `code-binding-risk-analysis`

> 需求文档副本。源文件位于 zcode_data 仓库 `.scratch/code-binding-risk-analysis/`;两处如有出入,以源文件为准。
>
> ⚠️ 本副本已于 2026-08-20 按质询结论更新(配套决策记录 `docs/adr/0002-project-shared-gitlab-bindings.md`),领先于源文件;源文件需反向同步本次变更后再作为唯一权威。

## 范围

新增代码绑定数据模型与 API、GitLab 资源代理端点(供前端级联下拉)、基线解析服务、风险分析任务扩展与凭据下发、报告读取接口。本模块不直连 GitLab 拉 diff(diff 由 ai-worker 直连拉取),但凭据与绑定清单由本模块下发。

## 需求条目

### RC-1 数据模型:`resource_bindings` 支持 GitLab 绑定

- `provider` 支持 `gitlab`(当前服务层硬编码 `zentao`,需改造为 zentao/gitlab 双提供商)。
- 项目级绑定:`local_resource_type=project`、`remote_resource_type=group`、`remote_parent_id` 为空;一个项目可绑多个群组,同一群组不允许重复绑定((项目, provider, 群组)唯一);`user_id` 记录创建者,`connection_id` 指向创建者的 GitLab 连接。
- 需求级绑定:`local_resource_type=requirement`、`remote_resource_type=repository`、`remote_parent_id=群组 id`;`extra_json` 携带 `{branch, baseline_branch?}`;一个需求可绑多个仓库;不携带 `connection_id`(凭据经由所属群组的项目绑定解析,见 ADR-0002)。
- 约束校验:仓库必须位于该项目已绑群组的群组树内(**含子群组**,与 RC-2 仓库列表同口径);绑定仓库必须携带 `branch`;`baseline_branch` 可选。
- **项目级可见性**:绑定查询按项目范围返回,不过滤 `user_id`(**项目内所有用户**可见可用;平台暂无成员模型)。
- **接管**:任何项目内用户可将绑定的 `connection_id` 更新为自己的连接(PATCH)。
- **删除保护**:删除群组绑定时,若存在引用其下仓库的需求绑定,则阻止删除并返回受影响绑定清单。

验收标准:

- [ ] 通过 API 可完成 GitLab 绑定(项目级、需求级)的创建、查询、更新、删除
- [ ] 绑定仓库不在项目已绑群组范围内(含子群组)时返回参数错误(沿用现有错误码体系)
- [ ] 绑定仓库缺少 `branch` 时返回参数错误
- [ ] 项目内其他用户 B 可见用户 A 创建的项目级绑定,并能更新 `connection_id` 完成接管
- [ ] 同一群组重复绑定被拒绝;删除被需求绑定引用的群组绑定被阻止并返回受影响绑定清单
- [ ] 禅道绑定行为不受影响(回归)

### RC-2 GitLab 资源代理端点(供前端级联下拉)

- `GET /projects/{project_id}/integrations/gitlab/connections/{connection_id}/groups?search=&page=&page_size=`:列出 PAT 可见群组(含子群组,支持搜索与分页)
- `GET /projects/{project_id}/integrations/gitlab/connections/{connection_id}/groups/{group_id}/repositories`:列出群组内仓库(`include_subgroups=true`,覆盖子群组仓库;支持分页)
- `GET /projects/{project_id}/integrations/gitlab/connections/{connection_id}/repositories/{repository_id}/branches?search=`:列出分支
- 客户端**手写 httpx**(沿用 `services/gitlab_auth.py` 风格,不引入 python-gitlab);GitLab 异常映射为统一错误码(归入现有 **3401 集成系列**,不引入 42xxx/51xxx);`repository_id` 需支持 GitLab 的项目 id 与 URL 编码 path。

验收标准:

- [ ] 三个端点可正常拉取,群组/分支支持搜索与分页;仓库列表覆盖子群组仓库
- [ ] PAT 失效或 GitLab 异常时返回结构化错误码(3401 系列)而非 500
- [ ] 端点校验连接属于该项目、当前用户有权使用(项目内所有用户)

### RC-3 基线解析服务(修订版规则)

对需求绑定的每个仓库独立解析基线:

1. 手工 `baseline_branch` 已设置 → 直接使用,不查历史;
2. 否则自动查找:当前迭代之前的所有迭代中,该仓库最近一次绑定的分支(迭代按 `end_time` 排序,空则创建时间);
3. 该仓库从未被绑定 → 无基线(整体视为全新变更);
4. 查找失败(分支已删等)→ 返回结构化错误,提示手工指定基线。
5. 命中迭代内该仓库存在多条绑定(绑了多个分支)→ 取绑定记录 `created_at` 最新的一条,解析结果标注「发现多条绑定,已取最近一条」;查找范围**严格限于之前迭代**,本迭代内其他需求的绑定不作基线。

解析结果(每仓库:仓库标识、分支、基线 ref 或 `none`、失败原因)随任务快照下发给 worker;解析逻辑独立成服务,便于单测。

验收标准:

- [ ] 四种情形分别返回正确结果(单元测试覆盖)
- [ ] 手工基线设置后,解析结果不随历史绑定变化
- [ ] 同一需求多仓库时按仓库独立解析
- [ ] 同一仓库在最近迭代存在多条绑定时取 `created_at` 最新并标注;本迭代内绑定不作基线

### RC-4 风险分析任务扩展与凭据下发

- `ai_generate_tasks.task_type` 新增 `code_risk_analysis`。
- 任务快照 payload 增加:需求文档、绑定清单(含 RC-3 基线解析结果与**任务创建时解析快照的 `connection_id`**)、现有测试内容(该需求下功能/API/UI 用例的名称/步骤/断言 + 执行结果字段:**功能用例暂无执行记录、留空标注**(run 表后续补齐);API/UI 取每用例最近一次 run 的 status 与完成时间,不带日志)、GitLab 凭据获取指引。
- 新增内部端点 `GET /internal/ai-worker/tasks/{task_id}/gitlab-credentials`(仿 llm-credentials 模式,worker token 鉴权):下发 `base_url` + `access_token`(解密后传输)+ 绑定清单。
- 任务失败态支持错误消息回显(`completed` 回调携带失败原因与补救建议)。

验收标准:

- [ ] 可创建 `code_risk_analysis` 任务,快照包含全部新字段
- [ ] gitlab-credentials 端点按 worker token 鉴权,凭据与绑定清单正确
- [ ] 失败任务的错误消息可经任务详情接口读回

### RC-5 报告存储与读取

- 复用通用 run 表保存 `result_yaml`(结构化风险报告:变更概览 / 风险点清单 / 受影响用例 / 覆盖缺口与建议 + 基线/head SHA)。
- **worker 回传契约**:`completed` 回调的 `resultYaml` 携带报告 YAML,顶层含 `analyzedAt`(分析时间,字符串)、`repositories`(每仓库 `repositoryId`/`branch`/`baselineCommit`/`headCommit`)、`changeOverview`(对象)、`risks`/`affectedCases`/`coverageGaps`(列表);顶层键与仓库条目键均接受 camelCase 与 snake_case 拼写。
- 任务详情接口(run 详情与任务 runs 列表)返回解析后的 `report` 结构(同上述六键:四区块 + 仓库 SHA + 分析时间),供前端渲染;`resultYaml` 原文仍原样返回。报告缺失、无法解析、或不含任何报告区块、或已出现区块形态不符契约时 `report` 为 `null`。

验收标准:

- [ ] worker 完成回调后,任务详情接口可读到完整报告结构
- [ ] 重复发起同一需求的分析,产生多次任务记录且互不覆盖

### RC-6 代码变更概览接口(迭代)

- `GET /sprints/{sprint_id}/code-overview`:返回该迭代内所有需求绑定的仓库/分支(按仓库去重聚合),每仓库:分支、基线解析结果、commits 数、增删行数、「新增仓库」标记(无基线时与空树对比)。**项目级概览本轮不做**。
- 计算方式:复用 RC-3 基线解析服务;调 GitLab compare API,无基线仓库以 git 空树 SHA `4b825dc642cb6eb9a060e54bf8d69288fbee4904` 为 `from`(GitLab 无 `empty_tree` 参数);结果带短缓存(默认 5 分钟,可配置);**绑定变更(创建/接管/删除)时主动失效缓存**。
- 失败处理:单仓库统计失败仅该仓库标注错误(含补救建议),不影响其余仓库与整体返回(概览为展示场景,不同于分析任务的 fail-fast)。

验收标准:

- [ ] 迭代概览返回结构正确,仓库按去重聚合
- [ ] 变更量口径与基线规则一致;无基线仓库以空树 SHA 对比并标记「新增仓库」
- [ ] 短缓存生效(缓存窗口内重复请求不重复调 GitLab);绑定变更后缓存主动失效
- [ ] 无任何绑定时返回空态结构
- [ ] 单仓库失败仅标注该仓库错误,整体接口仍返回 200

## 依赖

无外部依赖,可最先动工。ai-worker 依赖 RC-3/RC-4 的接口契约;Studio 依赖 RC-1/RC-2/RC-4/RC-5/RC-6。

## 明确不做

- 不在本模块实现 diff 计算(由 ai-worker 直连 GitLab 完成);
- 不引入迭代级绑定与快照机制。
