# Bug 附件、富文本图片与状态同步可行性分析

日期：2026-10-04。状态：分析完成，附件与正文图片已实现，状态同步仍待实施。范围：平台已有 Bug 单向推送至禅道后的附件、富文本图片、当前状态及后续状态变更；普通评论不作为本次交付条件。未调用真实禅道写接口、未重启服务、未读取实际部署凭据。

2026-10-06 补充：本地状态模型已按 [ADR 0005](adr/0005-bug-zentao-lifecycle.md) 对齐禅道，原六状态映射分析作为历史保留。当前模型使用 active/resolved/closed、confirmed 和 resolution；远端状态同步仍待实施。

## 最新范围确认

用户已明确：**附件、富文本内图片和状态必须同步；普通评论非必需。** 首次推送及已有关联的文件补传、后续新增文件和状态变更均需支持；仅创建远端 Bug、显示图片占位或留在禅道初始状态不能满足新要求。原普通评论能力调查保留为可选扩展证据，不阻塞本次必做项。状态操作所附的修复说明、回归结果或拒绝原因仍属于原业务信息，与普通评论分开处理。

## 结论

附件与富文本图片可以实现，但当前 MCP 缺少真正的文件上传能力，需要扩展项目外的 MCP 服务。状态同步有官方接口基础，需要确定六状态到禅道状态的映射并补上确认接口或目标版本兼容能力。普通评论的独立接口与 Token 兼容性尚未确认，但已不属于本次必做；不能用“解决/关闭/激活时带备注”冒充“只发评论”。

| 内容 | 已确认的能力 | 当前缺口 | 可行性判断 |
| --- | --- | --- | --- |
| Bug 附件 | 官方 v2 `POST /files` 使用 multipart，关联 `objectType=bug`、`objectID`，返回文件 ID/URL | 本机 `/files` schema 退化为修改文件名；执行器只发 JSON | 可做，需 MCP 上传工具及文件映射 |
| 富文本图片 | 上传后的文件可在 HTML 中引用；Bug 编辑支持 `steps` | 当前明确把 `<img>` 替换成占位文本，平台 HTML 不保存 `src` | 可做，上传图片并重写禅道引用，实际显示待验证 |
| Bug 下方普通评论（非必需） | 官方原生 `action.comment(objectType, objectID)` 可创建 Commented 动作 | 当前工具和已核实官方 v2 schema 无独立评论路由 | 可选扩展；兼容性调查不阻塞本次交付 |
| 状态与状态变更说明 | v2 resolve/close/activate 支持 `comment`，较新版本有 confirm | 本地状态流转没有远端调用；当前 MCP 无 confirm | 可做，须版本核实、映射和有序同步 |

外部能力的来源见下文，表中“可做”不表示当前环境已经通过真实写入验收。

## 当前实现证据

- [首次推送](/home/xiaoming/GitCloneData/model-testing-experience/apps/control-plane/src/testing_agent/services/bug_zentao_push.py:273)：成功记录存在时直接返回，仍只有创建行为；281 行排除图片，284 行发送初始描述的 `steps`，没有附件和状态。这是正文已存在的背景，不把后续正文同步列为本次用户请求。
- [富文本契约](/home/xiaoming/GitCloneData/model-testing-experience/apps/control-plane/src/testing_agent/domain/rich_text.py:15)：图片仅保存 `data-file-id`，38 行白名单不允许 `src`。不能把本地 HTML 直接交给禅道显示，也不能把有时效的 S3 签名 URL 当成长期图片地址。
- [状态流转](/home/xiaoming/GitCloneData/model-testing-experience/apps/control-plane/src/testing_agent/services/bug.py:302) 和 [追加评论](/home/xiaoming/GitCloneData/model-testing-experience/apps/control-plane/src/testing_agent/services/bug.py:450)：只保存本地 Bug/activities，没有 MCP 远端同步调用。
- [MCP 输入 schema](/home/xiaoming/zentao-mcp-deploy/source/internal/service/schema/build_input.go:57) 只处理 `application/json`；[执行器](/home/xiaoming/zentao-mcp-deploy/source/internal/service/tool/execute.go:72) 把 payload JSON 编码并设置 `Content-Type: application/json`。只修改 OpenAPI 不能得到 multipart 上传。
- [本机 Bug 编辑 schema](/home/xiaoming/zentao-mcp-deploy/source/docs/zentao-openapi.json:12523) 没有 `status`、`confirmed`、`comment`；resolve/close/activate 分别位于 14348、14427、14481 行，支持状态操作备注；21596 行的 `/files` POST 仅定义 `fileName`。没有 confirm 或独立 actions/comment 路径。
- 现有 [创建推送记录](/home/xiaoming/GitCloneData/model-testing-experience/apps/control-plane/src/testing_agent/models/bug_zentao_push.py:12) 不足以表达每次附件上传、评论和状态写入的独立结果。

主分析任务定向运行 `test_manual_push_uses_bindings_persists_result_and_never_recreates` 与 `test_abandoned_preparation_can_retry_but_images_are_not_transferred`，2 项通过。只验证现有创建映射、排除图片和不重复创建行为，不证明真实图片/评论/状态同步成功。

## 官方接口、版本和权限证据

### 文件与图片

官方[上传附件文档](https://www.zentao.net/book/api/post-files-2325.html) 标明 v22.0 及以上，使用 `POST /api.php/v2/files`、成员 Token、表单文件与对象关联字段，返回 `id` 和 `url`。这与当前 MCP 的文件名 JSON schema 不同。官方 SDK 的 [file/create 说明](https://github.com/easysoft/zentao-api/blob/bf0950707def488123d16ec15a6b81724f3425c2/docs/zentao-api/file.md) 和 [上传实现说明](https://github.com/easysoft/zentao-api/blob/bf0950707def488123d16ec15a6b81724f3425c2/README.md#上传附件) 同样要求 multipart。SDK 默认文件大小限制不是禅道实际部署允许的大小，目标 PHP/Web 服务器限制仍需核实。

官方[文件控制器](https://github.com/easysoft/zentaopms/blob/master/module/file/control.php) 的 `read()` 检查登录与文件访问权限，`download()` 也检查文件权限；[文件模型](https://github.com/easysoft/zentaopms/blob/master/module/file/model.php) 通过 `file/read` 展示内部图片引用。推断：上传返回 URL 必须结合实际站点根路径和使用者的禅道登录权限验证，不能认为它是无需认证的公开地址。应使用禅道内部读取路径，不永久保存 API Token 在 URL，也不靠放开平台私有文件访问解决显示问题。

### 状态接口与操作备注

官方 [Bug API 注册说明](https://github.com/easysoft/zentao-api/blob/bf0950707def488123d16ec15a6b81724f3425c2/docs/zentao-api/bug.md) 明确 resolve/close/activate 的 v2 PUT 路由和 `comment` 参数；这些动作的最低系列版本为 `22.0 / biz13.0 / max8.0 / ipd5.0`。confirm 最低为 `22.5 / biz13.5 / max8.5 / ipd5.5`，当前本机 schema 尚未纳入。

`resolution` 是解决接口必填字段。官方 [Bug 模型](https://github.com/easysoft/zentaopms/blob/master/module/bug/model.php) 对 `fixed` 额外要求非空 `resolvedBuild`，`duplicate` 要求重复 Bug ID；因此不能只发送状态字符串。实际版本的表单/工作流可能附加约束，需要目标实例核实。

官方 SDK [0.7.0 变更说明](https://github.com/easysoft/zentao-api/blob/bf0950707def488123d16ec15a6b81724f3425c2/CHANGES.md#070---2026-09-15) 记录 confirm 必须预读并保留状态、指派、类型、优先级、截止日期和抄送信息，以免缺省值重置已有字段；预读失败则停止。确认已关闭且指派人为 `closed` 的 Bug 还需要明确有效指派人。扩展 MCP 时应采用同等保护，不能直接用空 payload 确认。

### 普通评论与历史归属（可选扩展证据）

官方 [action 控制器](https://github.com/easysoft/zentaopms/blob/master/module/action/control.php) 的 `comment(objectType, objectID)` 只创建 `Commented` 动作，并在 API 请求分支返回 action ID；这是支持“只追加评论、不改变状态”的原生证据。

但核实的官方 [v2 OpenAPI](https://github.com/easysoft/zentao-api/blob/bf0950707def488123d16ec15a6b81724f3425c2/data/zentao-openapi.json) 没有 actions/comment 路由，Bug PUT 也没有 `comment` 属性，不能由此推断 `/api.php/v2/actions` 或任意自造 REST 路由可用。原生网页/JSON方法是否接受目标环境的 v2 Token，以及对应权限、响应格式、附件支持，均未实测；若必须禅道登录 session，需要评估禅道端受权限约束的 API 扩展，再经项目 MCP 暴露，不能在平台重新引入旧连接器。

官方 [action 模型](https://github.com/easysoft/zentaopms/blob/master/module/action/model.php) `create()` 默认使用当前登录账号并记录当前时间。推断：一般同步应显示为执行该次同步的成员和实际同步时间；历史内容可以注明本地原作者、原时间、事件 ID，不能承诺用普通接口把远端真实作者/时间原样伪造。模型内部有 actor 参数不等于对外 REST 开放作者覆写。resolve 的 `resolvedDate` 也不等于 action 历史时间。

## 建议方案（待确定业务规则，不代表已决定）

1. 保持项目 MCP 为唯一禅道通道。控制面校验本地文件属于 Bug/项目，从私有 S3 读取内容；新增 MCP 上传工具负责转成 multipart 交给禅道。传输可用有限大小 base64 或受限短时文件领取票据；base64 有额外体积，票据下载需地址范围、大小和时效限制。禅道上传接口不会读取平台端本地路径。
2. 先确保远端 Bug ID，上传附件/图片，再保存平台文件 ID、内容 hash、目标实例、远端 Bug ID 到远端文件 ID/URL 的映射。根据映射生成禅道 HTML 图片 `src`，用既有 `steps` 编辑接口补上图片；该写入只是图片传输所需，不扩大为任意正文覆盖。远端图片读权限和实际渲染需验收。
3. 状态变更说明使用对应状态工具的 `comment` 参数；普通评论不进入本次必做工具扩展。若以后建设评论同步，须独立验证仅追加评论、不修改状态或 `steps` 的接口，并处理作者、时间与去重。
4. 每次文件和状态写入采用独立操作记录及去重标识。每个 Bug 串行处理，记录待同步、成功、失败、结果待核对；超时等未知写入先回读核对，不盲目重试。保留创建、附件、图片引用和状态的独立结果，部分失败不能标为全部同步成功；附件前端复用现有整体提示，不新增进度面板。
5. 本地状态操作先保留成功，不因远端失败回滚；界面展示同步状态和可恢复入口。后台重试须重新确认当前绑定、当前成员授权与项目权限，不能偷偷改用另一成员 Token。当前本地 `bug_handle` 与推送 `write` 不同，需明确外部状态同步权限和开发成员个人 Token 管理方式。

建议的状态语义映射如下，需产品确认后才能实施：

| 本地状态/动作 | 禅道建议动作或目标 | 未确定规则 |
| --- | --- | --- |
| 待确定 | active，未确认 | 首次推送已处于后续状态时是否补到当前状态 |
| 确认进入处理中 | confirm，保留 active | 目标版本是否支持，指派映射如何处理 |
| 提交修复进入待回归 | resolve，resolution=fixed | 解决版本的来源；不能把计划修复迭代当成构建 ID |
| 回归通过进入关闭 | close | 远端当前状态冲突时是否停止提示 |
| 回归失败/重新打开 | activate，并附原因 | openedBuild/assignedTo 应保留远端已有值 |
| 拒绝：设计如此/无法复现/遗留 | resolve，对应 bydesign/notrepro/postponed | 拒绝是否保留 resolved 或再 close，语义需明确 |

禅道主要状态为 active/resolved/closed，另有 confirmed 标志，不能直接一一对应本地六状态；定制工作流还须单独核实。建议保留本地完整状态，通过动作和备注表达差异。当前仅分析单向同步；双向回写和远端手工修改冲突处理不应被默认加入。

## 实施前需验证

- 目标禅道版本和发行系列，以及成员 Token 的上传、编辑、确认、解决、关闭和激活权限；未读取真实配置，不能声称实际目标满足 v22/22.5 条件。普通评论接口不作为本次验证门槛。
- 图片上传后的 URL、站点子路径、登录权限和 HTML 处理能否长期显示；相同图片同时出现在正文与附件时去重，删除本地附件是否删除远端附件需明确。
- 首次推送及已有 Bug 的附件/图片补传必须可用；以后新增文件和状态变化是自动同步还是手动增量同步需确定。当前状态须补齐，完整历史动作回放不默认纳入范围。
- 远端写入后超时、部分附件失败、重复文件、实例切换、Token 撤销、远端状态已被人工修改等场景的核对和恢复。

本报告没有对这些能力做真实写入验收。附件、图片和状态的必做范围已由用户确认；状态具体映射、同步触发方式及兼容细节仍需在实施时明确并验证。

## 附件优先实施方案（2026-10-04）

用户要求先处理“附件在禅道可查看、下载”，独立附件代码现已实现并通过后端、前端与临时 MCP 容器验证，未上传真实禅道附件。富文本内嵌图片和状态仍为已确认必做项，随后单独接入；本阶段沿用页面附件区的范围，即当前已关联文件排除正文内嵌文件与已归档文件。

### 上传链路与 MCP 扩展

建议采用：控制面验证文件 → 签发受限 S3 下载票据 → 项目 MCP 读取并校验文件 → multipart 上传到禅道 → 回传附件 ID → 控制面保存映射。

- 项目外 MCP 新增专用 `upload_bug_attachment` 工具，输入远端 Bug ID、原文件名、类型、大小、SHA-256 和控制面生成的短期下载票据。使用当前成员 Token 调用配置中同一实例的 `POST /files`，固定 `objectType=bug`，不让调用方指定任意禅道目标。
- 工具从配置允许的 S3 来源取文件，使用独立无授权头 HTTP 客户端，不复用会转发禅道 Token 的 transport；不跟随到未允许来源的重定向，不记录完整签名 URL。
- 文件分块下载到临时文件，完成大小及 SHA-256 校验后才发出禅道上传；处理结束释放临时文件。采用下载票据避免视频、日志通过 base64 膨胀为巨大 MCP JSON。最大文件、临时空间、下载和上传超时须匹配真实部署限制。
- 官方上传门槛为 v22.0+；本机只读容器清单显示禅道镜像为 `easysoft/zentao:22.6`，符合版本门槛。此事实尚不证明项目实际端点、权限和上传响应已验收；也未确认当前 MCP 容器已使用最新发布镜像。
- 沿用项目外独立 Dockerfile 的发布方式，新增工具需发布新镜像并更新固定摘要。实际服务升级仍由部署负责人手动完成，不在平台增加启动接口。

### 平台数据与调用组织

1. 独立附件同步服务复用现有 Bug 读取、项目写权限、本人 MCP 授权、实际实例及历史目标校验。按现有推送关联定位远端 Bug，避免把文件发送到新绑定的另一个 Bug。
2. 新建或复用远端 Bug 后先保存创建关联，再开始附件同步。已有 `succeeded` 创建记录也允许附件补传；附件失败不改写创建状态为 `failed`，避免后续重试再次创建 Bug。
3. 新增逐附件映射记录：本地 Bug/文件 ID、内容摘要、目标实例、远端 Bug ID、远端文件 ID、操作 ID、操作人、状态、时间与错误摘要。按本地 Bug 和文件身份建立唯一约束，已明确成功的文件跳过，重复及并发请求竞争同一上传执行权。
4. 逐文件持久化 `pending/uploading/succeeded/failed/unknown`。确定未写入的失败可重试；开始上传后的超时或进程中断进入待核对。回读远端 Bug 的附件进行核对，无法唯一确认时继续保留 unknown，不能仅凭同名文件自动认定成功或盲目重传。
5. 用户确认不需要新增附件完成情况展示。复用现有“推送到禅道/重试推送”按钮、整体成功/失败提示，附件失败时说明 Bug 已创建。不新增进度条、逐附件状态面板或恢复按钮；未知结果使用后端只读核对接口处理。当前用户主动同步；已有 Bug 与后续新增附件均可补传。每个文件处理完成后即时保存，部分失败不会重传已成功项。

建议修改区域为控制面附件同步 service/model/schema/router 与迁移、Studio 禅道同步面板、项目外 MCP 上传工具和镜像；通用 S3 文件状态及 Bug 创建去重保持各自职责。当前 [MCP 客户端](/home/xiaoming/GitCloneData/model-testing-experience/apps/control-plane/src/testing_agent/services/mcp_client.py:16) 统一 30 秒超时，附件工具调用需要单独的传输超时配置。

### 附件验收

- 使用隔离 Bug 和当前成员 Token 验证真实 `POST /files`，确认附件出现在正确 Bug 的附件区，登录后可查看和下载，原文件名和内容正确；图片可能受禅道压缩规则影响，需分别核验可读性及实际字节行为。
- 覆盖截图、视频和日志，以及已关联 Bug 补传、后续新增附件、重复点击、并发同步和同名不同文件。
- 覆盖下载票据过期、S3 从 MCP 不可达、权限撤销、文件超限、校验失败、部分上传成功、上传成功但响应丢失；未知结果不自动产生第二份附件。
- 核实 MCP 容器可访问签名 Endpoint；签发后不修改主机名或路径。只看元数据返回成功不足以证明“禅道可查看、下载”。

## 附件实现状态（2026-10-04）

已实现持久化逐文件去重、已创建 Bug 的附件补传、本人 Token 与原实例保护、MCP 二进制上传和未知结果内容核对。独立构建镜像为本机 `zentao-mcp:2026-10-04-attachments`，构建源只保存于项目外的独立 Dockerfile。前端不增加附件进度面板。

附件版镜像已发布，本机 MCP 已升级且五个附件的 S3 下载校验通过，PHP 上传和请求体上限均为 128M；真实禅道附件写入及附件区显示、查看、下载仍待验收，见[部署记录](zentao-mcp-deployment.md#本机升级与发布核对2026-10-04)。富文本内图片已随后接入，复用已发布 MCP 的上传及 Bug 编辑工具；状态同步仍待实施。详细行为与验证见 [附件和正文图片实现说明](bug-zentao-push.md)。
