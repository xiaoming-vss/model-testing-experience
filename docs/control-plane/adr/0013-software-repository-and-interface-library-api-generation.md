# 软件仓库作为代码上下文，API 生成改用接口库

- 状态：已取代
- 日期：2026-11-15
- 取代：[ADR 0012](0012-project-interface-library.md) 的接口应用分组、启用状态和需求直接绑定仓库部分
- 被取代：[ADR 0015](0015-software-repository-direct-gitlab-binding.md)（GitLab 群组绑定）、[ADR 0017](0017-api-design-before-generation.md)（三阶段 API 工作流）
- 关联：[ADR 0012](0012-project-interface-library.md)、[ADR 0015](0015-software-repository-direct-gitlab-binding.md)、[ADR 0017](0017-api-design-before-generation.md)

2026-11-15。接口库原「应用」实体更名为软件仓库，需求不再直接绑定 GitLab 仓库；API 用例生成的输入从 OpenAPI/Swagger 文档改为接口库中选中的接口。本决策取代 [ADR 0012](0012-project-interface-library.md) 中「接口应用」分组、接口/应用启用状态和需求直接绑定仓库的部分。

> 本决策中「项目级 GitLab 群组绑定保持不变」及「无 Git 仓库的项目需先完成 GitLab 群组绑定」已由 [ADR 0015](0015-software-repository-direct-gitlab-binding.md) 取代。

## 决策

- **软件仓库 1:1 Git 仓库**：项目级软件仓库固定对应一个 GitLab 仓库，创建与换绑时必须选择仓库，不能清空。软件仓库保存名称、说明、仓库级 base path 和 Git 仓库快照；软件仓库或接口都不再有 `enabled` 状态。
- **需求关联替代直接绑定**：需求与软件仓库为多对多关联，每条关联保存需求级工作分支和基线分支，关联时必填并校验存在且当前操作人可访问。需求不直接绑定 GitLab 仓库；项目级 GitLab 群组绑定保持不变。
- **权限**：软件仓库由项目所有者维护；项目成员（write）可新增、修改和解绑需求关联；只读成员只读。
- **删除保护与换绑**：软件仓库仍有接口或需求关联时禁止删除；换绑后清空所有需求关联上的分支/基线，要求重新填写。
- **接口归属**：接口属于软件仓库，OpenAPI/Swagger 导入与手工创建都必须选择软件仓库。接口与需求的多对多关联继续在接口库维护。
- **数据迁移**：删除无仓库的存量应用及其接口；保留有仓库的应用并改名为软件仓库；清空全部存量接口和需求直接仓库绑定，接口按新导入流程重建。存量 API 生成任务、运行记录和候选产物删除，正式导入用例保留。预发布阶段按 [ADR 0014](0014-pre-release-single-baseline.md) 以空库初始化执行，不提供历史数据迁移脚本。
- **API 生成输入**：API 任务只保存有序、去重的接口 ID，不保存 OpenAPI/Swagger 原文；运行开始时读取接口最新定义并校验存在。任务创建与需求配置不再接受 `sourceType` / `sourceContent`。
- **选择器范围**：有成功的仓库画像版本时，默认展示画像识别出的后端／全栈软件仓库下的接口；没有画像、画像未识别出后端仓库或需求未关联软件仓库时，依次回退到需求关联软件仓库或项目全部接口。允许随时切换到需求关联仓库或项目全部接口；画像建议只用于缩小范围，不限制 API 生成。
- **两阶段不变**：继续使用 `interface_extract` → 人工审核 → `generate` 两阶段；第一阶段 skill 输入改为选中接口的结构化 JSON，输出仍为 `apiExtraction`；第二阶段使用已审核配置，不重新读取接口库。该阶段划分已由 [ADR 0017](0017-api-design-before-generation.md) 扩展为三阶段。
- **不冻结接口**：运行只冻结本次读取到的接口 JSON 快照，供本次 Worker 使用；接口编辑在下一次运行生效，接口删除则拒绝运行并列出缺失项。
- **base path 与 security**：接口 JSON 的 `fullPath` 由软件仓库 base path 与接口 path 拼接；导入保留文档级 `securitySchemes` 和接口级 `security`，提取阶段据此生成认证头或参数占位符。
- **工作流版本**：两阶段 API 工作流升级为 `api_two_stage/2.0`，历史 API 任务已清理，不兼容旧输入语义。现行标记已由 [ADR 0017](0017-api-design-before-generation.md) 改为 `api_three_stage/1.0`。

## 接口

- `GET/POST /v1/projects/{project_id}/software-repositories`，`GET/PATCH/DELETE /v1/software-repositories/{software_repository_id}`。
- `GET/POST /v1/requirements/{requirement_id}/software-repositories`，`PATCH/DELETE /v1/requirements/{requirement_id}/software-repositories/{software_repository_id}`。
- 接口继续使用 `/v1/api-interfaces`，归属字段为 `softwareRepositoryId`。
- API 任务创建与配置接受 `interfaceIds`；任务详情和运行快照返回选中接口及所属软件仓库。

## 后果

- 需求、接口库、代码风险分析、仓库画像、迭代代码概览和 UI 生成源码配置共用软件仓库这一代码上下文锚点，不再维护两套仓库关系。
- 接口库成为 API 生成的唯一输入来源；历史 OpenAPI 文档上传、粘贴和文档快照路径移除。
- 存量接口和需求仓库绑定需要按迁移清除并重建；无 Git 仓库的项目需先完成 GitLab 群组与个人授权绑定，才能创建软件仓库和导入接口。
- 接口 security 本期在接口详情只读展示，编辑能力留待后续。

## 拒绝的替代方案

- **保留「应用」名称**：一个应用只能对应一个仓库，名称与业务语义不符，且与项目共享服务等术语冲突。
- **需求继续直接绑定仓库**：同一代码关系需要在需求与接口库维护两遍，容易漂移且无法复用接口归属。
- **任务保存接口快照**：接口库更新后历史快照会掩盖最新定义，违背接口库作为单一事实来源的定位。
- **保留 OpenAPI 上传兼容入口**：会继续制造接口库与生成入口两套来源，并保留历史文档正文。
- **自动跳过已删除接口**：会静默改变用户选择范围，生成结果难以追溯。

相关文档：[控制面上下文](../CONTEXT.md)、[数据库结构描述](../database-schema.md)、[生成链](../generation-chain.md)、[需求生成配置](../requirement-design.md)、[Studio 上下文](../../studio/CONTEXT.md)、[AI Worker 上下文](../../ai-worker/CONTEXT.md)。
