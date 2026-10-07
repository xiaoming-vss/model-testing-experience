# 内置 ZenTao-MCP 连接

用户自行部署服务，项目所有者填写 MCP 服务地址，成员分别配置本人的 Token。平台不创建、启动、重启、停止容器或分配端口。可复用模板与多项目说明见 [手动部署指南](zentao-mcp-deployment.md)。

## 配置接口

- `GET /v1/projects/{projectId}/services/mcp/templates`：返回固定模板 `zentao`、名称 `ZenTao-MCP`、协议 `streamableHttp`、授权头 `token`。未配置时也返回模板，不自动创建连接。
- `POST /v1/projects/{projectId}/services/mcp`：所有者提交 `name`、`templateId: "zentao"`、完整 `baseUrl`。名称由所有者填写，去除首尾空白后保存；当前只支持 `zentao` 类型，每项目可以配置多份，名称在项目内不可重复，旧名称原样保留。地址仅接受 HTTP/HTTPS，拒绝凭据、查询参数、片段和空白，保留有效路径及末尾斜杠。无须个人凭据，不启动服务。
- `PATCH /{serviceId}`：所有者修改 `baseUrl` 时同时提交 `confirmInstanceSwitch: true`（页面复选框确认），在同一次保存中核对新 MCP 并完成目标切换；未确认拒绝修改地址。目标变化或混杂历史关联时，清理旧关联与更新地址在同一事务完成。连接失败、缺少本人 Token、权限失败或正在推送时保持原配置和关联。名称可修改；历史客户端提交的 `zentaoInstanceUrl` 不决定实际目标。其他服务保持原编辑规则。
- `PUT /{serviceId}/authorization`：成员保存 `{"token":"本人 Token"}`，按既有机制加密；只读取和使用本人授权。保存后检查该项目端点及实例信息，连接失败仍保留 Token 供修复后重查。
- `DELETE /{serviceId}/authorization`：撤销本人的授权，不影响其他成员。
- `POST /{serviceId}/instance-reset`：保留历史客户端兼容，页面已不再调用或提供独立切换按钮；新流程统一使用编辑配置的 PATCH 保存。
- `DELETE /{serviceId}`：所有者删除项目连接与相关个人授权，不停止外部 MCP，不删除绑定或 Bug 推送历史。

响应包含只读 `zentaoInstanceUrl`、`zentaoApiBaseUrl`、`instanceError` 、`instanceResetRequired`、`pendingInstanceUrl` 和 `connectionStatus`（`unchecked`、`available`、`error`）。没有本人 Token 时保存地址并显示待检查。目录读取或刷新使用当前成员 Token 重新检查，检查中由页面展示；不借用其他成员凭据。响应不返回 Token。

## 实例身份与端点变更

MCP 通过 `get_zentao_instance` 返回配置中的 `schemaVersion: 1`、`instanceUrl`、`apiBaseUrl`。禅道目标由部署负责人维护，平台不推测地址映射。MCP 协议及元数据可读取不等于 Token 具有禅道业务权限；授权状态只表示本人保存了凭据。

项目绑定保存所选 `mcpServiceId`；迭代、需求绑定、Bug 推送、附件补传、用例推送和结果核对统一沿用项目绑定所选 MCP 地址，不回退到固定本机 9090。每次操作核对实际实例与该服务关联的绑定和 Bug 推送历史；不一致时阻止业务。其他未被选中的 MCP 可独立配置和授权。修改 MCP 地址同步更新该项目个人连接的端点，但保留已核对的禅道身份，业务使用前重新检查。

同一目标的端点迁移可以保留成员授权。实际目标变化时卡片展示新目标与“需更新配置”；所有者在编辑服务中勾选确认后保存，即可若该 MCP 承载项目绑定，则清除本项目所有禅道项目/迭代/需求绑定、测试单外部缺陷号、Bug 和附件推送关联。旧 Bug 及附件信息归档到 Bug 动态；平台业务资产、GitLab 绑定、其他项目和禅道侧数据保留。旧目标个人授权失效，所有者明确为新目标保存的 Token 可保留。正在进行的 Bug/附件写入完成前不清理。删除重建同样需要确认，GET 和个人授权保存不自动清理。用例推送没有新增持久化历史表，沿用已有绑定保护与推送限制。

## 业务调用

项目、迭代、需求候选由 `GET /v1/projects/{projectId}/zentao/mcp/{kind}` 提供，kind 为 projects、executions、stories；后两者要求正整数 parentId。项目绑定窗口传 `mcpServiceId` 读取对应候选；省略时沿用项目绑定所选服务，未绑定且只有一份服务时兼容旧客户端。未绑定且有多份服务时要求先选择，所选服务被删除时不自动借用另一份。查询需要项目读取权限，绑定修改沿用管理权限，保存 Token 不增加业务权限。

项目、执行按 100 条分页，最多 100 页；重复或不完整分页报错。需求使用全量列表。项目详情工具缺失时以完整项目列表核对，执行和需求必须属于对应上级。历史绑定身份和编号保留，访问只用操作者当前授权。

- [Bug 手动推送](bug-zentao-push.md)
- [用例 MCP 推送](zentao-mcp-case-push.md)

Bug 统计、禅道测试单读取、禅道用例读取／导入及 connector-zentao 已停用。AIWork、Worker、nanobot 的任务级 MCP 集成不属于本次调整。

## 数据兼容

继续使用既有 `shared_services`、`service_authorizations` 和 `zentao_instance_url` 字段。运行前应用迁移 `20261004_0027`，移除每项目每类型唯一限制，并在旧禅道绑定 `extra_json.mcpServiceId` 补记原服务，保留远端编号与实例身份。存在同项目同类型多份服务时拒绝降级，以免丢失配置。原记录保存的 MCP 地址现在实际决定请求端点；升级前核对旧记录是否仍是可达的实际部署地址。旧手填实例身份仅作核对来源，不能覆盖 MCP 响应；实际身份变化及混杂历史关联可通过所有者确认清理恢复，不再永久禁止切换。

项目绑定创建提交 `mcpServiceId`，更新可更换该服务。同一禅道实例内更换服务保留远端绑定编号，并更新下级绑定与既有 Bug 推送的服务归属；有进行中、待核对推送或正在同步附件时拒绝更换。切到另一套禅道时，项目所有者须提交 `confirmInstanceSwitch: true`，核对新项目可访问后原子清理旧禅道关联并创建新项目绑定。Bug、附件与用例推送接口不提供 MCP 选择参数，统一使用项目选择及操作者自己的 Token。
