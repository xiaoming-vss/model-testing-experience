# 独立集成 Worker

开发与审查先阅读[通用后端规则](../agents/backend-development.md)和[集成 Worker 开发规则](development-rules.md)，遵守一次写入、租约和未知结果证据的边界。

integration-worker 是拉取式执行进程。控制面管理数据库、权限、个人授权、冻结输入、写入意图和结果事务；Worker 通过内部 HTTP 领取任务，通过 MCP 做只读复核及一次远端写入。它没有数据库连接、长期 S3 密钥或公开监听端口。执行决策见 [ADR 0006](../control-plane/adr/0006-independent-integration-execution.md)，总体切换步骤见[拆分计划](../control-plane/integration-worker-split-plan.md)。

源码使用 control-plane 风格的 src layout。`main/app` 负责启动及装配，`worker` 负责主循环和租约，`handlers` 分派两类任务，`services` 执行创建/附件/正文/字段工作流，`repositories` 实现控制面 HTTP Adapter，`gateways` 实现 MCP 传输和禅道工具，`domain` 保存纯规则，`schemas` 保存协议模型。

配置由根目录 `scripts/manage.py` 从 `config/platform.toml` 生成。命令及配置入口见 [应用 README](../../apps/integration-worker/README.md)。专用令牌与 AI/API/UI Worker 令牌分别管理；Worker ID 由主机、进程和随机启动标识生成。扩大副本前确认控制面已升级及数据库迁移完成。

控制面写许可只对当前任务/步骤/operation/领取代次有效，许可时间不超过租约。Worker 以请求开始的单调时钟和服务器剩余期限建立保守截止时间；心跳独立于远端调用。心跳拒绝、截止到期或停止信号后不开始下一次写入，已经发出的请求仍回传明确结果或 unknown。

控制面网络重试复用 claim/prepare/result 编号；外部写入不重试。失去 prepare 响应时只查询原意图，不能把第二次查询当成新的许可。结果回传失败时保留安全结果及原操作身份，用受限 evidence 接口回报，不把票据、Token、原始错误或冻结输入写入恢复日志。

用户授权的当前本地环境已全量启用独立 Worker，旧同步写链路已移除；示例配置仍默认关闭，关闭执行后暂停异步提交，不回落同步写入。原步骤恢复、留存、恢复隔离、核对放行、执行观测及真实 Studio 创建/上传/推送已验证。慢传输与 180 秒结果等待见[真实隔离验收](acceptance-2026-10-07.md)。当前环境暂停协调源码回退已演练，旧 Docker 镜像回退未验证。实际进度及收尾回归见[实施记录](../control-plane/integration-worker-implementation.md)，部署按[切换流程](rollout.md)。

2026-10-07 用户授权的当前环境沿用本地启动方式，Zata-Platform/test 两个项目已启用，独立 Worker 持续运行；实际异步任务与暂停源码回退后恢复的新任务均 succeeded 且全部 noop。全量切换与旧路径收尾尚未完成，示例配置继续默认关闭；当前环境配置及回退记录见实施记录。

## 启动与扩容

先完成控制面加法迁移和配置缺项升级，再构建 Worker。统一配置的 `[integration_worker.worker]` 控制轮询、心跳及排空时间；控制面 `[control_plane.integration_execution]` 控制启用项目、提交、领取、租约及运行代次。修改统一配置后重新生成，不直接编辑生成文件。

```sh
# 仓库根目录；这些命令不自行启用项目执行开关
python3 scripts/manage.py upgrade-config
python3 scripts/manage.py configure --mode docker
python3 scripts/manage.py compose build integration-worker
python3 scripts/manage.py compose up -d --no-deps --scale integration-worker=2 integration-worker
python3 scripts/manage.py compose ps integration-worker
python3 scripts/manage.py compose logs -f integration-worker
```

扩大副本不会扩大同一禅道实例允许的并发写入数：控制面通过数据库中的目标执行权协调不同副本，同一 Bug 也只允许一个活跃任务。副本之间不共享 MCP 会话或本地结果日志。Compose 只依赖控制面健康，不反向要求 Worker 在线才能启动控制面。

Docker 健康检查读取进程与最近循环/心跳进展；空队列及控制面暂时不可用时循环仍有进展。健康不表示禅道授权有效或任务成功。日志只记录任务、步骤、operation、状态和安全错误类别。

## 执行能力与观测

控制面迁移 `20261007_0033` 记录成功认证的 claim 能力声明与最近联系时间，成功续租更新心跳。默认 `worker_presence_ttl_seconds=120`，有效范围 10..3600，建议大于实际轮询及心跳间隔；超过期限显示离线，旧运行代次的声明不参与当前匹配。登记使用原子 upsert，过期七天的联系记录按维护批量清理；业务任务、租约、意图和回执继续保留。联系记录与能力声明仅用于观测，写许可仍逐步验证当前租约及本人授权。

排队状态增加 `queueReason`、`queueWaitSeconds`，Studio 继续查询本地状态：

| 原因 | 用户可见行为 |
| --- | --- |
| `worker_offline` | 等待执行服务上线 |
| `worker_incompatible` | 在线服务没有同时支持任务类型与协议的实例，提示升级执行服务；任务保留 queued |
| `target_busy` | 等待同一禅道实例的其他任务完成 |
| `paused` | 配置或恢复范围暂停，任务保留在队列 |
| `runtime_changed` | 任务属于旧运行代次，等待运维核对 |
| `waiting` | 能力匹配，等待实际领取 |

关闭执行时，已有 queued/unknown 任务继续使用异步查询；普通业务仍可读，旧同步写入口拒绝活跃或未知任务。恢复环境继续遵循恢复门控。终态不沿用排队提示。

在 `apps/control-plane` 使用生成配置执行只读观测命令；不需要停止服务：

```sh
uv run --extra dev python -m testing_agent.cli.integration_maintenance observe --config config/local.toml --project-id <项目ID> --window-hours 24 --limit 100
```

省略 project-id 查看当前数据库整体；时间窗口为 1..720 小时，明细上限为 1..1000，截断会显式标记。输出包括活跃/排队/unknown/隔离任务、最久等待、首次领取等待样本、有效/过期租约、最近成功心跳、按服务和步骤聚合的耗时，以及失败、unknown、失租和授权撤销的操作计数。停止的 Worker 也可查看其最近联系与心跳，在线数按当前代次及期限计算。

计数按原步骤的首次观测保存，重复回执不增加，成功核对不会抹掉曾经的 unknown/失租。步骤耗时由 Worker 的单调时钟测量远端操作及必要回读，通过可选 `remoteDurationMs` 回传；控制面将其与领域结果分开保存，不参与远端事实比较。缺省字段保持旧事件摘要，旧 outbox 可以照原身份回传；新字段需要先升级控制面，再升级 Worker。清理输入快照不会删除观测值。旧迁移之前缺失的测量显示 null/零样本，等待时间受数据库时间戳精度影响；这些数据不是外部系统的耗时证明。

认证失败和当前授权拒绝输出安全日志；HTTP 拒绝请求通过这些日志统计，持久化的 accessRevokedOperations 是已撤销步骤计数，两者不能混用。日志关联 job/step/operation/service，写调用日志附 remote_ms 及安全错误代码，不含快照、Token、签名地址或原始 MCP 错误。

回退部署前保存镜像及对应生成配置的版本。先暂停提交/领取，等待结果及每个副本 outbox 确认；存在未决写入或未确认新观测事件时继续使用兼容的控制面进行核对。旧镜像应恢复其接受的配置快照，最新配置中的新增字段不能直接挂载到不识别它们的旧版本；不能通过删除 remoteDurationMs、改 eventId 或改写原回执完成回退。通常保留加法迁移及账本，避免为应用回退删除恢复证据。配置状态、按项目扩大范围、回退演练和旧路径移除条件见[灰度与回退流程](rollout.md)。

## 停止与结果日志

```sh
# 普通维护保留容器和各副本运行卷
python3 scripts/manage.py compose stop integration-worker
python3 scripts/manage.py compose start integration-worker
```

SIGTERM 后停止领取和新写入，正在执行的调用仍续租并回传一次结果。Worker 默认排空 210 秒，Compose 停止宽限为 215 秒；新任务需等排空结束再更新副本。强制终止后，控制面保留写入意图并在失租后进入 unknown；不能通过删除日志或重新启动把它当作未执行任务。

`/app/runtime` 是每副本独立的匿名卷，`evidence.json` 如存在则只含原操作身份和安全结果，模式为 0600。容器 restart 及 Compose recreate 可继续使用对应卷；`compose down` 后再次 up 不会自动重新挂载旧匿名卷。拆除容器、缩容或清理卷之前先停止并导出仍有待回传证据的副本日志，记录容器与卷的对应关系；不能将多个副本的文件简单覆盖合并。

```sh
# 停止后查看副本编号；仅对确有 evidence.json 的副本执行后两行
python3 scripts/manage.py compose ps -a -q integration-worker
umask 077
mkdir -p .runtime/integration-evidence
docker inspect --format '{{json .Mounts}}' <副本容器编号>
docker cp <副本容器编号>:/app/runtime/evidence.json .runtime/integration-evidence/<副本容器编号>.json
```

恢复证据时保持 job/step/operation/event/领取代次原样，复制到停止中的对应副本卷，文件所有权须为容器 UID/GID 10001、模式 0600，再启动回传。数据库恢复环境需要新的运行代次，旧日志先归档核对，不能直接导入自动回放。恢复日志是减少人工核对的证据，控制面的写入意图才是防止重复执行的持久化依据。

联合数据库/S3 恢复同时要求新的专属 Worker 令牌并关闭执行、提交、领取三个开关；数据库中的恢复门控会继续阻止远端写入。通过控制面 `integration_maintenance` 的 restore-review/audit/isolate/release 完成清单核对、只读证明、保留隔离和全局放行。核对使用当前项目所有者自己的授权，放行不重放旧任务，也不自动开启配置；完整操作入口见[存储运维](../control-plane/storage-operations.md)。

正文图片可能不出现在禅道 Bug 的 files 列表中。Worker 使用 `get_files_fileID` 读取已确认编号的文件元信息，校验原 Bug 归属，再从已观察的正文提取原生读取路径；不推测路径或放宽文件归属。发布版 MCP 需要重新生成并挂载 `enable-bug-options.py` 提供的 schema。禅道 22.6 的实际验收发现 REST 请求复用编辑器 uid 会将前一个 Bug 的图片重新关联到后一个 Bug；上线前必须修复上游并验证连续创建后的文件归属，详见[部署指南](../control-plane/zentao-mcp-deployment.md)与[验收记录](acceptance-2026-10-07.md)。

控制面自动清理已知终态且不再参与当前关联的快照和步骤输入，成功/失败历史默认分别为 30/90 天；原请求、操作身份和结果回执继续保留。unknown、write_intent、当前关联及恢复隔离记录保护。期限和每次批量数由统一配置中的 `control_plane.integration_execution` 管理。

## 检查

在应用目录运行 pytest、Ruff 和 mypy。完整 HTTP 工作流测试需要先安装控制面的开发依赖，它启动隔离控制面数据库及 HTTP 进程，不访问统一配置中的运行服务。真实 MySQL 并发验收与真实禅道/S3 验收另行进行。

```sh
# 仓库根目录，显式运行独立容器的空领取/健康/停止验收
docker build -t mtx/integration-worker:split-validation apps/integration-worker
MTX_TEST_INTEGRATION_WORKER_RUNTIME=1 python3 -m unittest discover -s tests -p test_integration_worker_runtime.py -v
```

180 秒传输边界检查默认跳过；安装控制面开发依赖后，在本应用目录显式执行：

```sh
MTX_INTEGRATION_LONG_UPLOAD=1 uv run --extra dev python -m pytest tests/integration/test_long_upload.py -q
```

该检查启动独立控制面、Worker 和 HTTP MCP 夹具，上传超过实际 RPC 180 秒截止后要求 unknown、不重发及不执行正文；同时读取真实租约心跳并测量普通 Bug/项目接口的基线与上传期间延迟。输出 `long-upload-acceptance.json` 到本次 pytest 临时目录，包含延迟与心跳的聚合事实，不含凭据。它证明进程与传输边界，真实禅道/S3 长传输负载需要单独验证。
