# S3 联合备份、恢复与部署验收

统一入口与配置见 [文件存储](file-storage.md)。2026-10-03 新增联合备份 CLI，并完成独立 MySQL / RustFS 恢复演练。此工具适用于当前应用的 MySQL 表和私有 S3 对象，不备份 MySQL 账号、授权、存储服务配置或主机环境。

## 备份方式与保留

采用一次维护窗口生成一份不可覆盖的完整逻辑快照：全部业务表的建表语句和数据、应用前缀下的对象，以及可用文件记录实际引用的对象。每份快照独立存放，包含对象类型/下载文件名等元信息、表行数、文件 ID、业务引用和 SHA-256 清单。工具逐个校验 attached / archived / ready 引用的对象；对象丢失或内容不一致时失败，不发布有效 manifest。目录已存在时拒绝覆盖。

第一期采用完整快照保留方式，不依赖供应商是否支持版本化。建议每日维护窗口备份，且在迁移数据库、修改桶/前缀或扩大回收范围前额外备份；至少保留最近 7 个每日快照、4 个每周快照、3 个每月快照。工具不自动删除快照，不对正式对象设置统一过期规则。最终备份周期、异机位置和运行账号需随目标环境落地；本次未创建定时任务或声称已完成异机备份。备份与恢复工具、保留方式及隔离演练已经提供。

备份包含业务数据，目录权限为 0700、文件 0600。复制整份已验证的目录到独立于应用主机和源桶的受控存储，完成复制后再次 verify；不能把源 RustFS 所在磁盘上的副本作为唯一灾备。数据库中加密的集成配置依赖原 integration key，其恢复材料通过独立的密钥保管流程保存，不能仅保留业务快照。JWT / Worker 令牌明文和部署配置不写入 manifest，也不在命令行传递。集成恢复校验只保存专属 Worker 令牌的 SHA-256 指纹及源运行代次，用于拒绝复用旧配置。

## 创建与验证

在仓库根目录根据忽略的 `config/platform.toml` 运行 `python3 scripts/manage.py configure --mode local`。然后在 `apps/control-plane` 执行以下命令，替换目录时间戳：

```bash
.venv/bin/python -m testing_agent.cli.storage_backup backup ../../.runtime/backups/s3-20261003T210000 --config config/local.toml --maintenance
.venv/bin/python -m testing_agent.cli.storage_backup verify ../../.runtime/backups/s3-20261003T210000
```

执行前停止接收写请求，停止所有控制面实例、Worker、技能发布和其他写入同一数据库/前缀的程序，等待在途上传签名有效期结束。`--maintenance` 表示操作者已完成这些动作，CLI 本身不会停止服务。工具额外对应用表持有 MySQL READ 锁；维护窗口仍是对象与数据库一致性的前提，尤其是技能同 Key 覆盖。备份账号需要目标数据库 SELECT / SHOW CREATE / LOCK TABLES，以及应用对象前缀的 List / Get 权限。

只有全部表和对象复制成功后才生成 `manifest.json`。verify 检查全部文件路径、SHA-256、对象大小和文件引用。未完成目录、损坏文件或不一致引用不可恢复。读取失败会退出非零；保留失败目录用于排查，另用新目录重试。

## 恢复到隔离目标

1. 准备独立的空 MySQL 数据库和空私有桶。桶名、数据库名必须与快照源不同。目标存储凭证只授权目标桶，不覆盖在线源环境。
2. 在独立恢复检出中配置其忽略的 `config/platform.toml`，再通过 `scripts/manage.py configure --mode local` 生成恢复用控制面配置。保持应用及 Worker 停止，保留原 integration key 的解密能力，并使用隔离的 JWT / Worker 令牌。设置新的 `shared.integration_worker_token` 和 `shared.integration_runtime_generation`，将 `control_plane.integration_execution` 的 `enabled`、`accept_submissions`、`claim_enabled` 全部设为 false；恢复工具会拒绝旧令牌、旧代次及打开的开关。运行与快照匹配的应用代码；含集成任务的当前备份需要已交付的维护迁移 `20261007_0031`。
3. 在该检出的 `apps/control-plane` 中恢复受信任的备份目录：

```bash
.venv/bin/python -m testing_agent.cli.storage_backup restore /srv/mtx-backups/s3-20261003T210000 --config config/local.toml --maintenance
```

工具先验证整份快照，拒绝原桶、原数据库及非空目标；复制对象后再次 GET 校验大小和 SHA-256，重建表与数据，核对恢复行数，将 `stored_files.bucket` 改为目标桶。文件 ID、对象 Key、正文 data-file-id 和业务引用保持原值。所有非终态或含未决写入的集成任务进入 quarantined，原步骤与回执保留；新的运行代次和令牌指纹写入持久化恢复门控。数据库恢复不会回滚禅道，误开配置也不能重放这些任务。DDL / 数据只能从受控、可信的备份恢复；文件哈希检测损坏，不提供备份来源认证。

4. 用隔离账号验证需求原件、Bug 当前/历史图片、源码快照、技能清单和运行产物的稳定文件入口；核对 Alembic 版本、业务引用和文件哈希。恢复后在离线目标执行 `alembic upgrade head`，核对放行记录需要迁移 `20261007_0032`。联合备份不包含桶的运行配置；按恢复前端的实际 Origin 配置目标桶 CORS（GET/HEAD/POST），验证浏览器读取及上传，不能用无 Origin 的 GET 成功替代。执行下面的只读命令查看集成隔离任务和当前关联；任务按返回的 nextAfterId 翻页，关联按 nextMappingOffset 翻页，两份清单都需要核对。

```bash
.venv/bin/python -m testing_agent.cli.integration_maintenance restore-review --config config/local.toml --limit 100
.venv/bin/python -m testing_agent.cli.integration_maintenance restore-review --config config/local.toml --after-id <上一页的nextAfterId> --limit 100
.venv/bin/python -m testing_agent.cli.integration_maintenance restore-review --config config/local.toml --mapping-offset <上一页的nextMappingOffset> --limit 100
```
5. 部分恢复失败时目标继续离线；不能直接对非空目标重跑。保留失败现场，重新准备另一组空数据库和桶。只有验证通过后才安排切换与停机窗口，保留原环境作为回退。

## 集成核对与放行

停止源环境及目标环境的所有写入者，等待在途外部调用结束。三个集成开关保持关闭，使用恢复时的新令牌与运行代次；以下命令的 `--maintenance` 是对这些条件的明确声明，不会代替停止服务。所有命令指定 restore-review 返回的 restoreId，避免操作错误的恢复环境。

对每个当前关联及隔离任务所在 Bug 执行只读核对。操作者必须是当前项目所有者，并使用自己对目标 MCP 的个人授权。远端编号由人工核实，不按标题或文件名自动猜测；已有映射必须一致。未知附件需要提供 JSON 文件，格式为 `{"本地文件ID": 远端正整数文件ID}`，通过 `--file-map /srv/mtx-recovery/files.json` 传入。凭据不出现在命令参数或文件映射中。

```bash
.venv/bin/python -m testing_agent.cli.integration_maintenance restore-audit --config config/local.toml --maintenance --restore-id <restoreId> --bug-id <bugId> --actor-user-id <当前项目所有者ID> --remote-bug-id <禅道Bug编号>
```

核对验证实例、产品及层级、字段结果、正文基线，以及每个附件的归属、大小和 SHA-256。远端读取期间不持有数据库锁；落库前重新检查当前权限、凭据版本和本地快照，变化时整笔回滚。确认原正文时保留原操作的内容字节及摘要；等价 HTML 不改写历史回执。通过核对的旧任务转为 canceled，原操作身份和回执继续保留；核对本身不创建 Bug、不上传文件、不覆盖正文，也不继续执行旧任务。

无法确认的范围可以明确保留隔离。按 Bug 隔离会阻止该 Bug 的新写入及关联删除/切换；按旧 job 隔离保留该任务的恢复标记，也会阻止所在 Bug 的新写入。隔离不会把 unknown 解释为失败或无外部效果。

```bash
.venv/bin/python -m testing_agent.cli.integration_maintenance restore-isolate --config config/local.toml --maintenance --restore-id <restoreId> --bug-id <bugId>
# 若只确认保留某项历史任务的隔离，使用 --job-id，不能同时指定 --bug-id。
.venv/bin/python -m testing_agent.cli.integration_maintenance restore-release --config config/local.toml --maintenance --restore-id <restoreId>
```

放行要求所有当前 Bug/附件关联及恢复任务都已核对或明确保留隔离。核对记录默认有效 3600 秒，可通过统一配置的 `restore_review_max_age_seconds` 调整（1..86400）；权限、授权或映射变化后需要重新核对。保留隔离的范围在全局放行后仍受保护，可在后续维护窗口重新只读核对。放行只解除数据库中的全局门控，三个配置开关仍保持关闭。确认部署验收通过后再通过统一配置逐项目开启，新操作必须由用户重新提交；恢复环境的旧同步写入口持续拒绝写入，旧任务不会自动重放。

迁移降级不能删除已有核对证据；应用回退应保留加法迁移和恢复记录。不要通过 SQL 清除恢复标记或复用旧 Worker 令牌绕过门控。

## 可重复演练与故障测试

以下测试读取忽略的本机配置，明确 opt-in 后才连接真实 MySQL / RustFS；测试自行创建随机命名的数据库和桶，只清理本次成功创建的目标，不清理在线业务前缀。在仓库根目录执行：

```bash
CONTROL_PLANE_STORAGE_LIVE=1 apps/control-plane/.venv/bin/pytest apps/control-plane/tests/test_storage_live.py -q
```

2026-10-03 六项通过：真实签名 POST / GET、私有读和过期重签、权限撤销及旧票据有效期边界、对象缺失与哈希失败、删除失败重试和多清理实例、完成/关联行锁与保存回滚、并发任务领取和过期租约失败、联合备份恢复及损坏快照拒绝。恢复演练覆盖 41 张应用表，保留需求原件与 Bug 历史引用，文件 ID / 大小 / SHA-256 均一致。

2026-10-07 增补：当前真实 MySQL/RustFS 回归 9 项通过。独立禅道、发布版 MCP 和独立 Worker 的演练中，备份的 queued 任务在源环境之后实际创建了禅道 Bug，恢复旧快照后保持 quarantined；旧令牌 401，新领取与两种写入口 409，远端 Bug 数量未增加。详细范围见[真实隔离验收](../integration-worker/acceptance-2026-10-07.md)。

真实 HTTP 断流测试位于 `apps/ai-worker/tests/integration/test_signed_download_live.py`：仅使用专用 `s3-p1-*` 验收会话和该会话的 `ui-proof.json`，受控代理转发真实平台授权与 RustFS 对象，首次断流可恢复，连续断流三次后停止。不会修改主机网络或模拟成功文件内容。显式设置 `AI_WORKER_STORAGE_LIVE=1` 与 `S3_LIVE_SESSION_FILE` 才运行；会话文件为私有测试材料，不提交仓库。

## 远端/容器部署门槛

实际域名、服务器、TLS 和存储运行账号尚未提供，本机结果不能替代该环境验收。配置仍以 `config/platform.example.toml` 和该环境忽略的 `config/platform.toml` 为准，通过 manage.py 生成运行配置。

- 浏览器、控制面和两类 Worker 必须能访问同一个签名 Endpoint；容器内 `localhost` 指容器本身。不能生成签名后替换主机名。
- 非 localhost 前端采用可信 HTTPS，验证 Web Crypto；S3 HTTPS 证书需被浏览器与容器信任。
- CORS 只允许实际前端 Origin，验证 OPTIONS 与真实签名 POST / GET，保留 Content-Disposition。不能只用无 Origin 的 curl 作为浏览器验收。
- 桶保持私有。运行账号只允许目标桶应用前缀的 GetObject / PutObject / DeleteObject 和受 prefix 限制的 ListBucket；CopyObject 需要源 Get、目标 Put。桶管理和 CORS 修改使用独立运维账号。验证允许范围内操作成功、前缀外操作和匿名读取失败，不把管理账号的测试通过当作最小权限通过。
- 测试与生产使用不同数据库、桶、令牌和存储账号。先在目标网络执行页面和 Worker 验收、故障测试及隔离恢复，记录证据后再正式切换。

暂未变更远端配置、存储账号或在线部署。
