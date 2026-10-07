# 集成执行灰度与回退

本流程对应[拆分计划](../control-plane/integration-worker-split-plan.md)的 P3/P4/P5。配置来源是忽略的 `config/platform.toml`，示例见 `config/platform.example.toml`；修改后通过 `scripts/manage.py` 生成。实施验收环境与正式环境分别记录结果，隔离环境通过不等于正式项目已经切换。

## 切换前准备

保存当前控制面、Studio、Worker 镜像版本以及相应生成配置的受控副本。配置包含秘密，副本不得提交仓库。完成数据库/S3 备份并验证恢复流程；应用回退保留加法迁移、任务账本和副本结果日志。

先部署控制面协议、迁移至当前 head 和 Studio，再部署 Worker。运行配置升级只能补齐缺项，不轮换已有解密密钥；专属 Worker 令牌与运行代次须在控制面实例间一致。正式切换不沿用验收环境凭据。

验证目标 MCP 的实例身份、工具列表、附件来源白名单及 PHP 限额。禅道 22.6 的编辑器 uid 修复与连续创建后的文件归属检查是上线条件，见[部署说明](../control-plane/zentao-mcp-deployment.md)。上传来源使用实际签名 Endpoint；浏览器、控制面及 MCP 均须可达，目标桶 CORS 须覆盖部署后的 Studio Origin。

## 配置状态

以下字段都位于 `[control_plane.integration_execution]`：

| 阶段 | enabled | all_projects / project_ids | accept_submissions | claim_enabled | 行为 |
| --- | --- | --- | --- | --- | --- |
| 部署准备 | false | false / 空列表 | true | true | 异步提交暂停；Worker 不执行新集成任务，旧写路由已删除 |
| 指定项目灰度 | true | false / 明确的灰度项目编号 | true | true | 指定项目提交异步任务；其他项目暂停，旧写路由已删除 |
| 停止新增并排空 | true | 保持原灰度范围 | false | true | 拒绝新提交，已有队列可完成，结果与心跳继续接收 |
| 暂停领取 | true | 保持原灰度范围 | false | false | 已领取任务继续处理在途结果；queued 保留并显示暂停 |
| 全量异步 | true | true / 原灰度列表可保留 | true | true | 所有项目使用异步入口；进入 P5 收尾的前提之一 |

关闭 `enabled` 或移出项目列表会暂停对应范围的新写入，不能代替排空。已有 queued、活跃及 unknown 任务必须先处理；unknown 不证明远端未执行。恢复环境即使关闭开关也禁止旧写入口，仍通过异步协议及只读核对处理。

Docker 部署在仓库根目录生成并验证配置，再更新读取配置的控制面进程：

```sh
python3 scripts/manage.py upgrade-config
python3 scripts/manage.py configure --mode docker
python3 scripts/manage.py compose config --quiet
python3 scripts/manage.py compose up -d --no-deps --force-recreate control-plane
python3 scripts/manage.py compose up -d --no-deps integration-worker
```

镜像构建、数据库迁移及 Studio 发布沿用当前部署流程；配置检查通过只证明配置可解析。生成文件内容变化不会必然触发 Compose 自动重建，以上显式重建控制面进程使配置生效。切换后核对实际进程已加载新配置，不能根据文件内容推断运行开关。独立启动部署使用 `configure --mode local` 并重启对应进程。

## 灰度验收与扩大范围

每批记录项目编号、版本、配置状态、验收时间和任务编号。分别验证 Bug 创建、附件上传、正文图片及字段修改；Studio 返回 202 后应立即显示任务，刷新页面仍能查询，终态刷新领域结果。通过禅道页面和只读接口核对原 Bug、文件归属、大小/摘要及实际图片显示。

在 Worker 停止时提交一次新任务，确认 queued 和等待上线提示，普通 Bug/资产接口可用；恢复 Worker 后只执行一次。长调用期间对比普通接口基线与 P95，并检查实际租约心跳。上传限额、源下载速度、MCP 总时限 160 秒及 Worker 180 秒等待截止须分别记录；单纯等待测试不能证明真实文件传输能力。

执行只读观测命令，按项目比较任务积压、首次领取等待、步骤耗时、失败/unknown/失租及权限撤销。阈值依据本环境基线与容量制定并记录，不把 fixture 延迟当作部署环境服务水平目标。

```sh
# apps/control-plane；使用该部署生成的配置
uv run --extra dev python -m testing_agent.cli.integration_maintenance observe --config config/local.toml --project-id <项目ID> --window-hours 24 --limit 100
```

出现重复远端对象、文件错属、未知写入未核对、结果日志未确认，或普通接口延迟超出本批阈值时停止扩大范围。先关闭提交，必要时关闭领取，保留范围和账本；通过原关联的只读恢复入口核对，不重新提交相同远端写入。

## 回退演练与实际回退

1. 关闭新增提交，记录当前 queued/claimed/running/unknown 任务及每副本的结果日志。需要完成积压时保留领取；需要立即暂停时关闭领取。保持当前项目范围。
2. SIGTERM 停止 Worker，等待排空并确认退出。默认排空 210 秒，Compose 停止宽限 215 秒；不要在途强删容器或运行卷。强制终止留下的写入意图按 unknown 核对。
3. 使用兼容的控制面确认已知结果或只读核对 unknown。核对后旧依赖不会自行继续，后续动作由新的手动任务发起。检查每个副本 outbox 已确认或安全导出，原 event/operation/领取代次保持不变。
4. 优先回退 Worker/Studio，保留能读取当前协议和证据的控制面。回退控制面镜像之前，逐项确认旧版本接受当前 schema、事件字段、任务查询与门控；不兼容时继续运行兼容控制面，仅暂停执行。配置使用对应版本快照，不能通过删观测字段或改回执适配旧版本。
5. 保留数据库加法迁移，不执行删表降级。确需恢复备份时按[恢复流程](../control-plane/storage-operations.md)更换代次和专属令牌并隔离任务；数据库恢复不会回滚禅道。
6. 重新启用后先查询原任务并检查外部数量；确认旧任务没有重放，再提交一个新的手动任务。已关联 Bug 和文件应 no-op，只有尚未完成的必要步骤可以执行。

回退验收记录须区分“配置暂停/恢复”“进程停止/重启”和“实际旧镜像回退”。只有实际执行并验证过的镜像组合可列为可用回退版本。

## P5 旧路径移除条件

所有目标项目已通过异步验收并全量切换；旧同步入口无剩余调用者；历史活跃预约、unknown、恢复隔离及 outbox 已处理或保留明确运维责任。完成这些条件后，另交付旧 POST/PATCH 写入口和对应远端工作流的移除变更，保留短只读查询及原操作核对能力。

2026-10-07 当前环境已全量切换，旧远端写工作流和 Studio 调用已移除。旧 POST/PATCH 路由及提示 handler 已删除，同路径 GET 保留；关闭开关后不会恢复同步写入。收尾变更需通过控制面、Studio、Worker、根编排回归及运行验证；协调源码暂停回退已验证，旧 Docker 镜像未验证。回退保持同一执行权和暂停门控，不启动拆分前单体写链路。
