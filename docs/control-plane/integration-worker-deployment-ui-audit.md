# integration-worker 拆分：部署与 Studio 调研

本文件记录拆分前的代码审查依据，旧同步方法和行号属于历史参考。2026-10-07 当前环境已全量切换，控制面旧远端写工作流及 Studio 同步调用已移除，旧 POST/PATCH 写路由已删除；同路径 GET 查询保留。当前结构、接口和验证结果见[实施记录](integration-worker-implementation.md)。

状态：2026-10-06 的方案调研基线。本文的源码事实和“未实施”描述限于调研当时；后续交付及验收以[实施记录](integration-worker-implementation.md)为准。调研依据工作区第一方源码，当时未部署、未调用远端服务、未读取本地密钥。范围包含已有禅道 Bug 创建、附件、正文同步和影响版本/指派人远端修改，不包含生命周期状态同步、反向同步或新的集成功能。后一次源码核对已补充 fields update 与 Studio edit 模式。

## 结论

新增 `apps/integration-worker` 为独立部署、反向领取任务的执行服务可复用仓库现有部署模式。它不监听公开端口，不连接业务数据库，不持有长期 S3 密钥或集成解密密钥；control-plane 继续提供浏览器接口、身份权限、任务与同步状态的持久化，以及按任务下发个人授权和短期文件票据。Studio 继续只访问 control-plane。

这是实际增加一个独立进程/容器，并非仅在 control-plane 内建立新的 services 包。第一期只迁移外部写入任务；版本/人员候选查询等交互式查询是否随后迁移，另行评估。主方案采用 control-plane 所有的独立 `integration_jobs` 与 `integration_job_steps`，不复用现有 `worker_tasks`；新 Worker 通过 claim/input/access/heartbeat/steps-prepare/results 协议执行 IO，控制面负责步骤预约与结果事务。任务执行状态与远端结果分别保存；外部写入结果不明禁止重新执行。

## 已核对的源码事实

| 事实 | 第一方来源 |
| --- | --- |
| 根部署有 control-plane、AI Worker、API/UI Worker、Studio；两个 Worker 不发布端口，反向依赖 control-plane 健康 | `compose.yaml:38–85` |
| control-plane 健康检查来自镜像，访问 `/v1/health` | `apps/control-plane/Dockerfile:48–49` |
| API/UI Worker Dockerfile 遗留 `EXPOSE 9010`，实际没有文件下载监听和健康检查；不可据此给新 Worker 增设公开端口 | `apps/api-ui-worker/Dockerfile:28`；`docs/api-ui-worker/README.md:57–75` |
| 配置源是 platform 示例和本地 platform，运行配置由 manage.py 生成；项目列表、配置模板、local 输出路径和命令入口均显式枚举现有项目 | `AGENTS.md:3–7`；`scripts/manage.py:20–25,194–202,253–264,362–366` |
| Docker Worker base_url 统一为 `http://control-plane:9000`，本地模式由 local_host/control_plane_port 拼接 | `scripts/manage.py:184–188,219–234` |
| CP、AI、API/UI 当前共用一个 `shared.worker_token`；控制面内部鉴权只比较 `X-Worker-Token` 与同一 key，没有按 Worker domain 绑定令牌 | `config/platform.example.toml:12`；`scripts/manage.py:211–230`；`apps/control-plane/src/testing_agent/api/deps.py:99–104`；三个 `routers/*_worker.py` 的路由级 dependency |
| API/UI worker.id 不填时自动生成 hostname+pid；AI 示例 worker_id 固定为 nanobot-worker-01，配置模型也有固定默认值，不会自动因扩容变成唯一身份 | `apps/api-ui-worker/src/test_worker/core/config.py:49–55`；`apps/ai-worker/config/worker.example.toml:2`；`apps/ai-worker/src/testing_agent_ai_worker/config/models.py:8–13`；`config/loader.py:15–35` |
| Worker HTTP 请求带 workerId，队列记录有 worker_id 与 lease_expires_at；唯一实例 ID 是租约归属与回写校验所需身份，不能把共享令牌当实例 ID | `apps/ai-worker/src/testing_agent_ai_worker/platform/task_source.py:94`；`apps/control-plane/src/testing_agent/services/worker.py:497–509` |
| Bug 推送 HTTP 当前 await 完整 pushes.push；字段修改 PATCH await pushes.update_fields；核对 HTTP await pushes.reconcile，不是入队后返回 | `apps/control-plane/src/testing_agent/handlers/bug_zentao_push.py:36–42,53–59,62–68` |
| 创建先原子预约 operation_id，并写 preparing 状态；绑定变更与预约共用项目锁 | `apps/control-plane/src/testing_agent/services/bug_zentao_push.py:209–275` |
| 附件会再次检查个人授权、MCP 实例、远端 Bug、文件归属与 sha256；通过文件存储 ticket 向 MCP 上传工具提供 downloadUrl | `apps/control-plane/src/testing_agent/services/bug_zentao_attachment.py:102–116,118–150,224–285` |
| Studio 的图片长期存储只有 data-file-id，签名 URL 不落库；新任务快照不能把一次生成的签名地址当永久业务数据 | `docs/studio/adr/0003-rich-text-editor.md:15–20` |
| Studio 只通过 control-plane 的 Bug 路径 GET 状态/候选、POST 推送/核对、PATCH 影响版本/指派人 | `apps/studio/src/features/bugs/api/bugs.api.ts:26–36`；`compose.yaml:79–82` |
| 同步面板已对 preparing/creating、attachmentStatus/descriptionStatus=syncing 和 fieldUpdateStatus=preparing/updating 每 3 秒查询；未涵盖独立 queued 字段 | `apps/studio/src/features/bugs/components/BugZentaoPushPanel.tsx:22–25` |
| 面板 saved() 对非完整成功结果调用 message.error；updateFields 对非none/succeeded的fieldUpdateStatus也调用message.error，入队返回必须调整两种回调 | 同文件 `:48–54,69–88` |
| 当前 busy 是三个 mutation pending；fieldBusy 额外覆盖 preparing/updating。POST/PATCH 提前返回后，所有动作均需纳入共享服务端活动任务状态 | 同文件 `:94–96,108–123` |
| Bug activities 查询没有轮询；saved()/updateFields 当前只在 HTTP 返回时 invalidate 一次 | `apps/studio/src/features/bugs/hooks/useBugDetail.ts:31–35`；`components/BugZentaoPushPanel.tsx:52,79` |
| 面板保留 unknown 人工核对，附件 unknown 不允许重试创建，正文 unknown 可进行读取核验；不能把 unknown 都统一当自动重试 | `components/BugZentaoPushPanel.tsx:93,113–130,160`；`BugZentaoPushPanel.test.tsx:66–135` |
| 外部 MySQL 部署覆盖只修改数据库/migrate/control-plane 的依赖；新 Worker 无 DB 可原样继承 control-plane 依赖 | `deploy/compose.external-db.yaml:3–16` |
| 工作区新增 ADR 0005 替代 Bug 六状态机：本地模型为 active/resolved/closed，confirmed 与 resolution 独立；该 ADR 明确未新增远端写入 | `docs/control-plane/adr/0005-bug-zentao-lifecycle.md:3–15`；`apps/studio/src/features/bugs/types.ts:3,25–27` |
| 当前已有 fields service：远端原Bug归属与product校验、预期字段基线校验、只提交变化字段、PUT后回读，unknown仅在回读等于desired时恢复 | `apps/control-plane/src/testing_agent/services/bug_zentao_fields.py:60–82,123–154,196–289` |
| 字段修改存于 push.payload_json._fieldUpdate，拥有自己的operationId与before/desired；成功写Bug动态但不改平台责任人 | 同文件 `:84–121,158–194`；`tests/test_bug_zentao_fields.py:100–119` |
| 实例切换已检测 _fieldUpdate preparing/updating；新增作业后仍需保留此保护并兼容新任务执行权 | `apps/control-plane/src/testing_agent/services/zentao_mcp_reset.py:57` |

## 最新字段修改入口与迁移要求

当前独立远端写入口为 `PATCH /v1/bugs/{bugId}/zentao-push`，路由位于 `apps/control-plane/src/testing_agent/routers/bugs.py:44–46`，handler 位于 `handlers/bug_zentao_push.py:53–59`。它与创建/补传的同路径 POST 是不同动作。Studio 的 `updateBugZentaoFields` 直接调用 PATCH（`api/bugs.api.ts:32–34`）；“修改禅道版本和指派人”按钮设置 mode=edit，读取当前远端选项，提交 expectedRemoteBugId/expectedTarget/expectedOpenedBuild/expectedAssignedTo 与 desired 值（`components/BugZentaoPushPanel.tsx:28–42,69–88,108–112,133–160`；`types.ts:181–198`）。

第一期须把该已有写入迁为独立 `zentao_bug_fields_update` 作业，与 `zentao_bug_sync` 竞争同一个 Bug 写入执行权。字段修改只由用户明确打开 edit 并保存发起，不随创建、补传、正文同步或平台转派自动触发；它只改远端影响版本与指派人，不改本地责任人或生命周期状态。

字段作业冻结本次 expected 与 desired，Worker 读取远端当前值核对基线，保留只修改变化字段、保留未变化历史/删除候选值、允许清空指派人、PUT后回读和未知禁止盲目重写的已有语义。无变化保存不应发起远端写入。字段 options GET 还会在 unknown 且实际值等于 desired 时更新本地核对结果（`bug_zentao_fields.py:123–138`），因此虽是远端只读查询，它并非纯本地无副作用读；保留在control-plane时必须按job/step/operation映射同事务恢复，不能遗漏。

灰度时旧 POST 与旧 PATCH 均应接受同一执行方式门控，并禁止绕过任务共享执行权。所有旧字段 preparing/updating/unknown 状态参与切换、排空和回滚核对；不能只处理创建/附件/正文记录。已有 fields 测试覆盖修改与清空、历史值保留、无变化无写、远端基线冲突、超时/回读失败、unknown只读恢复、并发，见 `tests/test_bug_zentao_fields.py:100–220`。

## 部署与配置的拟改文件

1. 新建独立项目 `apps/integration-worker/`：`AGENTS.md`、导航 README、`pyproject.toml`、`uv.lock`、`.python-version`、`Dockerfile`、`config/local.example.toml`、独立 `src/` 入口与 `tests/`。按新增结构要求采用 control-plane 风格的 main/app、core/schemas/domain、handlers/services/repositories，并按 Worker 职责增加 worker/gateways，详见主方案。依赖仅按实际 MCP/HTTP、配置校验、日志需要选择，不复用 AI 的 Nanobot 镜像或 API/UI 的 Playwright 镜像；不得跨目录 import control-plane ORM/service。
2. 更新 `scripts/manage.py`：PROJECTS、configurations specs、生成 cp_url/token、local_files 和 run commands 注册 integration-worker；新入口建议 `mtx-integration-worker`，命令由 `python3 scripts/manage.py run integration-worker` 启动。配置与 control-plane 命名一致：模板 config/local.example.toml，生成的本地运行文件 config/local.toml，Docker 挂载 /app/config/local.toml，注入新服务自己的 APP_CONF。
3. 更新 `config/platform.example.toml`：新增 integration-worker 执行参数和独立集成 Worker token 的配置项（名称实施时统一），由 init 为新 key 生成随机值；已有 platform 文件需通过 init 或兼容补齐流程补新 key，禁止仅在新安装可用。
4. 更新 `compose.yaml`：增加独立 build/image、`restart: unless-stopped`、只读运行配置挂载、`depends_on: control-plane: service_healthy`，不设置 ports，不依赖 mysql/migrate，不挂载 AI runtime 或浏览器 artifacts 卷。临时文件如需要使用容器临时目录，日志优先 stdout。
5. 更新控制面 config/deps 与新的 integration-worker router：集成 token 只准访问新增 domain 接口，既有 AI/API/UI 路由不接受它；反过来，既有共享 token 也不能获取 integration-worker 的个人凭据。此处不要求同步改造旧三个 domain 的所有鉴权。
6. 更新 `tests/test_management.py`：配置生成、独立 token、端口不新增、每个模式 cp_url、secret 转义、已有配置补齐、run 注册；检查新配置不含 DB DSN、JWT、集成解密 key、S3 access/secret key。更新相关 Compose/存储配置测试。
7. 新建 `docs/integration-worker/CONTEXT.md` 与 `README.md`；更新根 `AGENTS.md` 的项目数量、`CONTEXT-MAP.md` 和根部署导航；按实施决定记录服务边界 ADR。新项目 README 仅作入口与启动导航。
8. `deploy/compose.external-db.yaml` 原则上不需要修改，但必须验证与新主 Compose 合成的结果；不得因新增 Worker 改变外部数据库初始化规则。

integration-worker 示例配置仅需要 control-plane 地址、该 domain 内部调用 token、实例 ID（空值自动生成 hostname+pid+启动随机标识）、轮询/心跳/请求超时、执行并发上限、日志配置。建议初始并发为 1，先完成重复写保护后再增加副本。每个进程唯一 worker_id，不能在所有副本挂载同一个固定 ID。

## Studio 异步交互方案

1. 保留现有目标确认弹窗、影响版本、指派人和 expectedTarget；不增加新的公开服务地址或跳转。control-plane POST 验证身份、项目 write、输入及目标版本，原子保存预约和待执行任务；HTTP 成功只表示已接受。
2. 保留现有 `BugZentaoPush` 外部结果主状态与子同步状态，额外返回少量活动摘要（如 operationId、taskStatus=queued/claimed/running）；字段以主方案确定的协议为准。创建入队可以沿用 preparing，但页面要区分“等待执行”与实际核对；附件补传保持原 remoteBugId，pending 时通过 taskStatus 继续轮询。队列状态与外部状态分开，不把本地 Bug active/resolved/closed 混入同步结果。
3. `saved()` 收到已接受时关闭弹窗、缓存新的状态并显示“已提交，等待同步”；不能宣称已经创建，也不能显示错误。对即时验证失败维持现有 HTTP error 提示。
4. 扩展现有 3 秒轮询，条件包含 queued/claimed/running、preparing/creating/syncing 与 fieldUpdateStatus=preparing/updating；不是从零新增轮询。字段任务的queued/claimed阶段同样持续轮询。无活动任务、成功、失败、unknown 时停止固定轮询。refresh/重新打开页面通过 GET 恢复同一状态，不需要浏览器保持 POST/PATCH 连接。
5. busy/按钮禁用同时考虑任务活动状态；操作从服务器接受到终态之间禁止重复创建或再次补传。后端幂等/预约仍是最终保护，前端禁用不是可靠并发控制。
6. 收到新的 operation 终态时刷新 bugActivities；当前只在 POST 返回时刷新会错过稍后 Worker 写出的事件。终态提示按 operationId 去重，避免每次轮询重复弹 toast。用户仅打开历史记录不应无故提示旧操作成功。
7. 沿用 existing 的补传、unknown 创建核对、附件未知结果禁止盲重传、正文未知结果先 readback 的交互。若 reconcile 也迁为 Worker 任务，同样显示已提交并轮询；不可表面显示已关联再等待远端核对。
8. edit 模式复用原有字段选择、远端基线与确认按钮，异步 accepted 关闭弹窗并显示“已提交”；字段终态按fieldUpdateStatus/fieldUpdateError提示。字段作业与同步作业互斥时所有写动作共同禁用；未知字段更新继续通过明确用户重新加载options只读核对，不能自动新建写任务。

拟改前端文件：`apps/studio/src/features/bugs/types.ts`、`api/bugs.api.ts`（仅响应契约有变化时）、`components/BugZentaoPushPanel.tsx`、`components/BugZentaoPushPanel.test.tsx`；终态刷新逻辑优先局限于面板。`useBugDetail.ts` 不必扩大全详情轮询。公共 request 现有 response.ok 可接受 202，但仍要求 `{code:0,data:...}` envelope，见 `shared/api/request.ts:98–115`。

## 启动、健康、扩容与回滚约束

- 新服务不提供公开 HTTP；进程存活与 loop 存活要分开验证。建议提供内部 CLI healthcheck，读取仅含最后 loop 成功时间/任务心跳时间的本地健康文件；空闲时仍更新时间，处理长任务时心跳线程仍更新时间。控制面不可达可标记不 ready，不能把远端禅道故障当进程死亡不断重启。Docker unhealthy 本身不会保证重启，必须明确由进程对不可恢复错误退出、运维告警处理可恢复依赖故障。
- 启动后轮询退避并保留心跳，不能只依赖 Compose 启动顺序；control-plane 重启是正常情况。SIGTERM 停止领取并让已领取任务有有限排空时间；未排空写入保留明确 unknown/待核对状态，不能自动视作失败重新创建。
- 复制副本前验证原子领取、租约、operationId/attempt 校验、旧实例不能覆盖新尝试、每个文件写入预约。新 Worker 不应照搬当前 Worker 租约超时通用失败逻辑：外部写可能已成功，失联后不能推断没有写入。
- 当前 downloadUrl 由 MCP 工具读取；部署网络必须保证 Worker→control-plane HTTP、Worker→MCP，以及 MCP→签名 S3 地址可达。新 Worker 不需接受控制面的入站 HTTP。即使新 Worker 没有 S3 密钥，也不能遗漏 MCP 的下载路径。地址票据在执行前申请，过期可重新申请；不能长期存进任务快照或日志。
- 发布顺序为数据库兼容扩展与 CP 新协议 → 可消费但暂不开启新入队的 Worker → Studio accepted/轮询兼容 → 切换新推送入队。切换点保留 operationId 和状态，不能同一 Bug 同时跑旧同步实现和新队列。
- 回滚先停新入队并停止领取，排空/逐条核对新任务，再恢复同步入口。不能直接降级 DB 或删队列；queued 无外部写可撤销/迁移，running/creating/附件 uploading 或正文 writing 必须按实际写边界确定结果，未知保留人工核对。已存在 remoteBugId 绝不重建。

## 验证计划（实施时运行，调研未执行）

```sh
# 仓库根目录；本地配置已按部署规范初始化
python3 -m unittest discover -s tests -v
python3 scripts/manage.py compose config --quiet

# apps/control-plane
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run --extra dev mypy

# apps/studio
npm run verify
npm test

# 新 apps/integration-worker：在其 pyproject 固化这些检查
uv run --extra dev pytest
uv run --extra dev ruff check .
```

专项验收：POST/字段操作入队后快速返回；accepted 不显示错误；queued 补传/字段任务持续轮询；终态动态刷新；刷新页面恢复状态；两副本只产生一次远端创建；字段任务与同步任务共享Bug执行权；只改变化字段且不改本地责任人；字段unknown仅只读核对；任务领取后权限/授权撤销；MCP 地址/实例切换；租约过期与旧结果回传；远端写成功但回传丢失；附件票据过期；正常 SIGTERM 和强制终止；使用 integration token 请求 AI/API/UI 接口被拒绝；新 Worker 配置没有数据库和长期存储凭据。测试使用本地伪 MCP/HTTP 服务，不对真实禅道执行验收写入。

调研限制：以上确认代码与部署结构，不证明当前生产请求耗时、CPU、积压量或规模；无真实负载数据。存在文档滞后：控制面 README 仍称“平台唯一后端”、列旧路由数量，且统计章节保留历史外部缺陷采集说明（`docs/control-plane/README.md:3,22,117`）。工作区正有其他变更，实施前重新核对 Alembic head 与最新 HTTP/TS 契约，不预占迁移编号；Bug 生命周期以最新 ADR 0005 和源码为准。第一期迁移已有创建/附件/正文同步与影响版本/指派人修改，不增加生命周期同步、反向导入或正文差异功能。

## 本轮遗漏核对：协议与恢复（2026-10-06）

以下核对针对当前 `integration-worker-split-plan.md` 第 68–164 行；都是草案尚未规定的具体协议，不代表功能已实现。不修改主计划，不运行测试或远端操作。前轮冻结完整输入、字段任务、专属token和配置批次的问题已在主计划补充，不重复计入。

1. **revision 没有定义自身推进与外部修改的区别，也没有跨步骤刷新规则。** 草案第 124–135 行仅说 input/target/access revision 与当前值逐项比较。创建成功会填 remoteBugId、上传成功会填 remoteFileId、正文/字段预约和结果会更新同一 push 的状态或时间；Worker 若沿用初始映射无法拼正文，若 revision 用整行 updated_at 则自己的 prepare/result 会使下一步冲突。代码依据：`bug_zentao_push.py:285–312,420–441` 更新状态并继续sync；`bug_zentao_attachment.py:185–198,294–300` 填远端文件ID；`bug_zentao_description.py:282–303` 必须读取刚上传成功的映射；`bug_zentao_fields.py:96–107` 更新同一payload和updated_at。补法：定义不可变 source revision（正文/文件/创建输入）、authorization/target revision 与按成功步骤推进的 derived mapping revision；不以同步记录updated_at作为源版本。result返回新的映射版本/最小结果，下一步重新读input/access并复核；只能接受本job已确认步骤产生的派生变化，真实外部编辑仍拒绝。加“创建→多附件→正文不自冲突”和“中途用户修改拒绝”的真实链路验收。

2. **prepare 的重试与 result 的幂等只写了原则，未写不可变内容和终态规则。** 草案第87、127–128、135、150行说步骤唯一、event ID幂等、prepare响应丢失保守unknown，但没有说明HTTP客户端重试prepare会返回可再次执行的operation，还是仅返回原意图查询；也没有同eventId不同内容、新eventId降级原succeeded的规则。代码依据：`bug_zentao_push.py:285–312` 每次终态会追加动态；`bug_zentao_attachment.py:185–198` 仅按operation更新状态；最新`bug_zentao_fields.py:89–129`已有成功幂等返回和状态CAS。这些方法不能未经封装直接处理重复消息。补法：prepare用requestId+输入摘要，重复只返回同一预约的状态，不再次授予写许可；响应不明确仍按已有保守unknown处理。result以job/step/operation/eventId唯一并存规范化摘要，同key不同内容409，重复返回原receipt，不重复动态；已succeeded不能被新的failed/unknown事件改写，unknown→succeeded需明确证据规则。跨事务重试必须先检查receipt，再检查当前租约，避免已提交结果响应丢失却被后续终态/租约检查拒绝。

3. **claim 响应丢失没有恢复协议。** 草案第86、123、147行规定原子领取和无写意图可重领，但没有claim requestId或“返回本实例尚未过期领取”的规则。数据库领取已提交、响应丢失时，Worker不知道jobId却继续claim，可让同一单并发实例持有多个任务，占满租约而无法心跳。现有领取源码正是在commit之后才返回任务：`worker_task.py:144–195`，新代码不能只照搬此窗口。补法：为每个claim请求生成并复用claimRequestId，按workerId/claimRequestId持久化或可重建原响应；同实例有未释放占用槽时优先恢复原领取，不继续获取第二项。返回claimedAt/leaseExpiresAt和代次；在确实未发出任何写意图的租约清理中重排任务而不是失败。验收“CP提交claim后丢响应→同请求重试恢复同job且不领取下一job”。

4. **独立心跳不等于失租后停止写入，草案缺Worker停止条件。** 草案第126、133、139、164行只有服务器续租/写前prepare，没有规定续租失败如何通知执行协程，也没有prepare许可的最晚发起时间。prepare成功后心跳被403/撤销拒绝或超时，执行线程仍可能在很久以后用内存Token发起PUT。现有API/UI心跳只记录警告、继续执行（`apps/api-ui-worker/src/test_worker/poller/task_poller.py:197–224`），AI心跳也吞异常继续循环（`apps/ai-worker/src/testing_agent_ai_worker/worker/runner.py:139–150`）；不能复用这种行为。补法：shared stop/fenced信号，明确403/409/失代次立即停止后续写，瞬态错误仅在保守本地单调时钟租约deadline前重试；heartbeat返回服务器期限，prepare返回短有效期写许可，执行前再次检查信号与期限。已发出的请求不宣称取消成功，保留unknown并只回证据；已预约但明确尚未发送可报告no-write证据，不能自动重新领写许可。

5. **受限晚到证据与所有运行接口必须当前领取的规则没有落成可调用协议。** 草案第131行拒绝旧operation/领取，152–153行又允许旧操作晚到和授权撤销后记录证据，但result接口没有区别，旧Worker遇失租或取消可能无法把已经成功的remoteId交回，unknown长期无法自动消除；放松通用校验又会让旧结果覆盖新关联。代码依据：旧`worker_task.py:51–63`在非claimed/running或租约过期一律拒绝；同步领域通过原operation限定目标（`bug_zentao_attachment.py:185–197`、`bug_zentao_push.py:285–296`），正文还绑定原instance/remoteBugId（`bug_zentao_description.py:389–397`）。补法：result定义evidence-only模式或独立receipt接口，以原claim+job/step/operation身份记录不可变证据，不发访问材料、不续租、不批准新写；原任务/映射未被替换且证据可核对时才受限应用，否则只归档。明确已接受receipt在取消/失租后重试仍返回原receipt。同Bug未知写入即使整体任务终态释放active scope，也要保留步骤/目标的冲突门禁；不能让仍在途的旧PUT与新冲突写并行。

6. **completed 丢失及“所有必需步骤”没有服务器闭环。** 草案第129行只有completed汇总持久化结果，第147–148行租约处理只有无意图重领/有意图结果缺失unknown。若最后一步result已提交但completed没发/响应丢失，所有外部结果已明确，job仍running；清理可能重领只读或误判unknown，页面继续轮询且active scope不释放。现有API/UI在完成回传异常时转报错误（`task_poller.py:152–187`），现有CP失租直接failed（`worker_task.py:121–142`），两者都不适合复用。补法：入队冻结expected step manifest/依赖与明确skip原因（无附件、无变化字段等）；result事务可在全部必需步骤可确定后幂等归并job终态并释放执行权，completed只作幂等确认/提前结束解释。租约清理对全步骤终态但job未归并者按持久化结果修复，禁止重发远端操作；只统计实际创建的步骤会把未执行的必要正文步骤漏算为成功。验收最后result提交后killWorker，以及completed响应丢失两种情况，任务仍显示正确终态且不重复动态。

这些补充不扩展第一期业务功能，目的是把已经提出的冻结输入、租约、去重和unknown恢复落成可实现且可测试的协议。
