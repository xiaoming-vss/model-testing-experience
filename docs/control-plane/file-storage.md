# 统一 S3 文件存储

平台采用私有桶：前端通过短期签名 POST 直传，Worker 在下载时申请短期 GET URL 后直接读取。控制面保管凭证、核验对象、管理项目权限和文件关联。已接入需求文档、UI 源码包、项目上传技能包及 UI 截图/Trace。Bug 附件可复用通用上传能力。报告目前在内存中按需导出，未依赖本地文件持久化。

## 配置和部署

在本地忽略的 `config/platform.toml` 中配置 `[control_plane.storage.s3]`，字段见 `config/platform.example.toml`。默认 `enabled = false`，未启用时需求文件和源码包上传不可用，前端提示管理员配置 S3。启用后需要支持 Signature V4、POST policy、CopyObject、GetObject、HeadObject 和 DeleteObject 的服务；后端账号只授权指定桶的应用前缀。

- `endpoint`：浏览器、控制面和 Worker 都可达的地址。签名生成后不能替换域名。
- `region`、`bucket`、`access_key`、`secret_key`：目标存储配置，不把密钥复制到前端或 Worker。
- `prefix = "mtx"`、`addressing_style = "path"`：对象前缀及寻址方式。
- `signature_seconds = 900`：上传和下载授权默认 15 分钟，允许 60–3600 秒。
- `temporary_hours = 24`：临时文件保留时间，至少 2 小时，必须长于签名有效期。
- `max_bytes = 104857600`：默认单文件 100 MiB，上限可配置到 1 GiB；第一期不提供分片上传。

前端 SHA-256 使用 Web Crypto，非 localhost 部署需使用 HTTPS。浏览器文件哈希和 Worker 返回字节的下载器会占用与文件大小相关的内存；大文件接入前应评估限制并扩展流式或分片方案。

私有桶需要配置 CORS，例如（替换为真实前端源，不含路径）：

```json
[
  {
    "AllowedOrigins": ["https://mtx.example.com"],
    "AllowedMethods": ["POST", "GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["Content-Disposition", "ETag"],
    "MaxAgeSeconds": 600
  }
]
```

CORS 的来源必须与浏览器地址栏的协议、主机和端口完全一致。当前 Vite 本地开发默认使用 `5173`，而平台部署配置中的 `studio_port` 通常是 `8081`；不能只根据部署端口配置 CORS。开发环境使用 `localhost` 或 `127.0.0.1` 时，需要分别允许实际使用的来源，例如 `http://localhost:5173` 和 `http://127.0.0.1:5173`。

RustFS 联调必须同时检查 OPTIONS 预检和真实签名 POST 响应。只使用无 Origin 的 HTTP 上传成功，并不能证明浏览器可以上传。本仓库保留了一个明确用于调试的真实存储检查脚本，在仓库根目录执行：

```bash
apps/control-plane/.venv/bin/python .scratch/debug/s3_upload_cors.py http://localhost:5173
```

该脚本读取本地平台配置，检查允许来源的响应头，上传一个随机命名的四字节测试对象并在结束时清理，不输出密钥或签名。2026-09-27 在 RustFS 上复现遗漏 `5173` 来源时预检 403；补齐来源后预检 200、上传 204，均返回匹配的 Access-Control-Allow-Origin。

不启用公共读写。CORS 不授予业务权限。所有实例使用同一存储配置；修改已有桶或前缀前先制定迁移方案，不能仅改配置让历史记录失效。

生成运行配置后，在控制面环境升级数据库至 Alembic head，再部署控制面、Worker 和前端。此次新增 `stored_files` 表、`requirements.document_file_id` 和 `ai_generate_task_source_archives.file_id`，不会自动迁移业务文件。部署前备份数据库与本地文件。

## 接口与生命周期

- `GET /v1/files/capabilities`：登录用户获取启用状态与大小限制。
- `POST /v1/files/uploads`：提交 `projectId`、`filename`、`size`、十六进制 `sha256` 和 `purpose`（`requirement`、`attachment` 、`ui_source_archive`、`project_skill` 或 `ui_artifact`），返回 `fileId`、签名 POST 的 `upload.url` / `upload.fields` 及有效期。
- 浏览器按返回字段构造 FormData，最后加入 `file`，直接 POST 到存储；不携带平台 Authorization。
- `POST /v1/files/{fileId}/complete`：仅上传者且仍有项目写权限时可完成；核验大小、SHA-256 和基本文件内容格式，重复调用幂等。
- `GET /v1/files/{fileId}`：读取可访问文件的元信息及核验完成时间，不返回对象 Key 或凭证。
- `GET /v1/files/{fileId}/download`：按当前项目权限及有效业务归属授权；未关联文件仅上传者可读。返回临时 URL、大小、哈希、文件名。业务正文只存 fileId。
- 需求创建与更新 JSON 支持 `documentFileId`，在同一数据库事务里将已核验文件关联到需求。关联限制到当前项目和上传者，不对外暴露任意资源绑定接口。

状态为 `pending`（等待上传核验）、`ready`（可关联）、`attached`（正式关联）、`archived`（保留的 Bug 历史证据）、`deleting`（清理中）。上传授权只允许写 staging 对象；完成时服务端复制到独立对象，再读取核验，避免有效期内重复上传改变已确认文件。该核验会产生一次控制面的对象读取流量，不是上传数据中转。

扩展名白名单见 `services/stored_file.py`；DOCX 需具备 Word ZIP 条目，图片/PDF/ZIP/MP4 检查基本头部，文本拒绝二进制 NUL。这不等同于杀毒或完整内容安全扫描。正式对象按 `前缀/项目ID/业务目录/文件ID/原始文件名` 保存，保留扩展名；对象设置对应的 Content-Type 和附件下载 Content-Disposition（含 UTF-8 原始文件名）。临时对象仍叫 `upload`。富文本接入时通过 Blob 或受控图片组件展示。

控制面每 5 分钟处理至多 100 条过期临时记录，并回收已过期的正式记录 staging 对象；删除失败保留状态供重试。完成、关联和清理通过行锁协调。正式关联对象和替换后的历史对象保守保留，不自动物理删除，避免历史引用失效；后续增加业务保留策略后再精确回收。

## 用户下载和 Worker 下载

原需求下载地址保持稳定。用户请求添加 `Accept: application/json` 时返回 S3 JSON 下载票据，否则重定向至短期签名链接。Worker 入口固定返回 JSON 票据。需求文件不再接受本地二进制回退；没有 `documentFileId` 的历史需求返回 409 并提示重新上传。


Worker 使用原任务需求下载入口，通过原有任务执行者授权后获取对应文件票据。签名不保存进任务，不把 Worker Token 发送到对象存储。下载完成验证大小、SHA-256；网络失败或 403 等临时错误最多尝试三次，每次重新申请票据；404 和内容校验失败直接报告。

前端上传/下载遇到签名过期、网络中断或临时服务故障时最多三次尝试，重新申请票据；上传完成通知的响应丢失也可恢复。平台 401/403、永久存储 AccessDenied、404 不自动重试。富文本图片与截图先鉴权下载，再以 Blob URL 展示，页面停留不依赖签名有效期；失败可手动重新加载，卸载时释放 Blob URL。旧临时对象由清理器回收。签名 URL 不记录日志，后端签名响应使用 no-store。已签发 URL 在有效期内仍可访问，权限撤销不能立即撤销旧签名。

## 历史数据与清理命令

2026-09-27 决定仅保留 S3 需求文件链路，移除本地 multipart 上传、磁盘写入/读取回退和 `migrate` 命令。数据库旧 `document_storage_path` 列仅保留历史信息，不参与运行时文件读取；不删除历史需求记录和磁盘文件。需求增强文本仍保存在数据库，与原文件分开。

没有 S3 原文件的历史需求需要重新上传。切换时本地数据库有 20 条此类需求，其中 19 份源文件在当前机器无法找到，另 1 份文件哈希与历史记录不一致，未自动绑定。升级时需同步更新前端和 Worker；UI 源码 ZIP 也已切换到 S3；Worker 任务临时工作目录用于下载、解压和执行，继续保留。

在控制面目录执行临时 S3 对象清理：

```bash
uv run python -m testing_agent.cli.storage cleanup
```

## 验证与运维

自动化使用 Moto 验证对象复制、校验与生命周期，SQLite 验证业务权限和关联；这些不能替代目标供应商兼容性、生产数据库并发锁及浏览器 CORS 联调。

部署验收：上传需求、预览、下载、创建需求分析任务、Worker 获取票据并读取；覆盖超限、越权、未上传即完成、签名过期和失败重试。目标桶应配置备份/版本保留策略，并将数据库备份与对象备份按恢复时间点协调。不要只备份数据库，也不要对整个应用前缀设置统一短期过期策略。

排障优先检查：Endpoint 可达性、系统时间、Region / 寻址方式、CORS、IAM 的 POST/复制/读取/删除权限，以及数据库迁移版本。日志只记录文件或任务 ID 和错误类型，不输出凭证或签名 URL。

## 修复旧对象文件名

早期正式对象以 `content` 命名，在 RustFS 控制台下载时可能失去 `.docx` 扩展名。新上传文件已保留原始名称。旧文件可以在控制面目录执行：

```bash
uv run python -m testing_agent.cli.storage repair-names
uv run python -m testing_agent.cli.storage repair-names --apply
```

默认只列出候选；apply 复制已核验的旧对象到含原文件名的新 Key，核对原大小与 SHA-256 后更新文件记录，文件 ID 和业务关联保持不变。旧 `content` 对象保留，兼容已签发链接，命令可重复执行。控制台下载时选择带扩展名的新对象；旧对象不自动删除。


## UI 源码包

前端先以 `purpose=ui_source_archive` 申请统一上传授权，直传 ZIP 后调用 complete，再通过 `PUT /v1/ui-case-generate-tasks/{taskId}/source-archive` 提交 JSON `{"fileId":"..."}`。该接口不再接受 multipart 文件，控制面不保存源码包到持久本地目录。文件用途、项目权限和上传人必须匹配，绑定与源码包引用在同一事务提交，失败时旧引用保留。

源码包上限为全局限制与 100 MiB 的较小值，只允许 ZIP。complete 对已封存对象执行完整 ZIP 核验，拒绝路径越界、绝对路径、符号链接、重复条目和 CRC 损坏，限制条目数 50,000、解压大小 1 GiB。验证使用临时流，不作为业务文件持久存储。

发起运行时把 `sourceArchiveFileId` 固定到运行快照。Worker 访问原 source-archive 入口时，控制面先校验运行归属与执行权限，再为快照对应文件签发票据。Worker 直接从 S3 拉取、检查大小/哈希后解压到任务临时目录。替换源码包只影响后续运行；旧对象保留，避免正在执行的任务失去输入。

升级至数据库版本 `20260927_0018`，前端、控制面和 Worker 同步升级。本机现有 1 个历史本地源码包需要重新上传；没有 S3 文件 ID 的旧运行应重新发起，控制面明确报错，不回退本地文件。旧路径列和磁盘文件保留但不再用于上传、下载或删除。

2026-09-27 在 RustFS 完成签名 ZIP POST（204）、封存和 ZIP 核验、Worker 下载器通过真实 S3 GET 校验并解压的冒烟验证，测试对象已删除。平台票据响应在该冒烟中模拟；完整真实 AI 生成任务验收仍未完成。


## 平台业务文件全面接入（2026-09-27）

| 文件类别 | 存储与访问方式 |
| --- | --- |
| 需求原文件、UI 源码包 | 前端签名直传、业务记录保存 fileId、Worker 按任务取票据直读 S3 |
| 技能文件夹 | 各文件直传 S3，原子替换当前文件清单；系统默认技能全局共享且项目只读，详见 [Skill 管理](skills.md) |
| UI 步骤截图、Trace ZIP | Worker 使用所属执行的授权申请签名直传，校验后关联 Worker 任务；结果仅保存稳定文件引用；Trace 引用已纳入运行记录持久化 |
| 导入 YAML/JSON、报告 PDF 等按需导出 | 输入解析后存数据库，输出在内存中生成；当前没有本地持久文件，未增加无业务需求的归档副本 |
| 配置、日志、缓存、任务工作目录 | 属于运行环境或临时数据，继续本地使用；不作为业务文件持久存储 |

控制面已无业务文件 FileResponse 和本地读写回退。数据库旧路径列及历史磁盘文件保留，但不参与下载或资源删除。Worker 的 9010 静态截图服务及 Compose 端口映射已移除；前端截图、Trace 从鉴权后的 S3 票据读取，不再访问 Worker 公开 URL。

UI 文件授权路由挂在 `/internal/ui-worker/tasks/{taskId}/files` 下。申请和完成均校验当前 Worker ID、有效租约、任务执行人及项目权限；完成只允许关联本任务上传记录；上报结果时再次检查文件引用属于本执行，拒绝其他任务文件或本地/任意外部 URL。上传失败保留临时文件并报告失败，平台接受最终结果后删除已上传的临时文件。

数据库版本 `20260927_0019` 已在本地应用；增加项目技能 fileId 和 UI 运行 trace_path（保存稳定 fileId 路由）。2026-09-27 已通过真实控制面 Worker 鉴权 → RustFS 直传 → 核验 → 结果回传 → 截图/Trace 引用落库冒烟，测试记录和对象已清理；未执行真实浏览器测试场景。

历史恢复：已把 19 张关联截图和 5 份 Trace（24 个对象）迁入 RustFS 并更新数据库引用。迁移前的记录备份在 `.runtime/backups/before-artifacts-s3-20260927-135252.json`。剩余 140 条截图引用找不到本机源文件，1 个旧源码 ZIP 缺失；此前 20 条需求仍未绑定 S3（19 份缺失、1 份哈希不符），需从原环境恢复或重新上传/执行。没有历史项目上传技能包。未关联的本地旧产物未擅自归入项目或删除；磁盘原件未删除。


## 项目内按业务类型组织对象（2026-09-27）

**状态：已实现新上传路径；历史 S3 对象保持原路径，未批量迁移。**

对象 Key 统一采用 `<配置前缀>/<项目ID>/<业务目录>/<文件ID>/<原始文件名>`，默认前缀为 `mtx`，桶为部署配置中的桶（当前为 `xiaoming`）。不增加日期目录，上传时间和业务对象关联保存在数据库中。

| 业务目录 | 用途 | 接入状态 |
| --- | --- | --- |
| `requirements` | 需求原文件 | 已实现，`purpose=requirement` |
| `attachments` | 通用附件、富文本图片 | 存储分类已实现，`purpose=attachment`；具体编辑器接入另行验收 |
| `bugs` | Bug 图片和附件 | 预留，随 Bug 文件功能接入 |
| `reports` | 持久化测试报告 | 预留，当前报告在内存中导出 |
| `source-archives` | UI 源码包 | 已实现，`purpose=ui_source_archive` |
| `skills` | 项目技能文件 | 已实现，`purpose=project_skill` |
| `ui-artifacts` | UI 执行截图、Trace、录像 | 已实现，`purpose=ui_artifact` |

示例：`mtx/<项目ID>/requirements/<文件ID>/登录功能需求.docx`。目录由后端根据用途分配，前端和 Worker 不传自定义对象路径；文件 ID 避免同名覆盖。上传暂存对象位于同一文件 ID 下的 `upload`，完成核验后封存为原始文件名，暂存对象按现有清理策略回收。S3 目录是对象前缀，预留分类不创建空目录对象。

读取、签名下载、删除和清理继续使用数据库保存的实际 Key，不根据新目录重新拼接历史文件路径。旧目录对象继续可用，本次不移动、不删除历史对象；如后续迁移，须复制并校验大小和 SHA-256 后更新数据库引用，保留旧对象以兼容尚未过期的签名链接。已有名称修复命令仅修复文件名，保持其原目录。


## Bug 历史证据保护（2026-10-03）

从当前 Bug 附件移除的文件置为 `archived`，保留 Bug 关联、历史授权和正式对象；当前附件列表不再显示。项目成员可恢复同一 Bug 的历史正文引用，无需重新上传。临时清理兼容旧 `deleting` Bug 记录，只要对应 Bug 存在就保守归档；已归档对象不回收，只在临时期限届满后清理 staging。通用正式回收策略仍属于后续治理，不以删除历史证据节省容量。

清理器在实际删除前再次锁定文件行，其他实例已领取或删除的行跳过；复用技能 Key 时保护活跃记录。删除失败保留 `deleting` 供后续重试，日志记录 fileId、操作及错误类型。真实 MySQL 行锁、并发清理和故障恢复见[联合备份与验收](storage-operations.md)。

## 业务删除与文件访问（2026-10-04）

通用文件元信息、用户下载及 Worker 签发票据共用 `services/stored_file_access.py` 的关联校验。正式或归档文件不能仅凭 `attached` / `archived` 状态获得访问；关联资源必须存在且项目归属匹配。用户入口仍先检查当前成员角色：Bug 使用 `bug_read`，其他项目文件使用 `read`；未关联文件仍仅上传者可读。Worker 原有任务、执行者和租约鉴权继续执行。

| 文件类别 | 有效关联规则 |
| --- | --- |
| 需求原文件 | 需求及所属迭代存在，迭代项目与文件一致。需求替换后的旧文件保守保留访问；需求或迭代被删除后停止签发 |
| Bug 图片与附件 | Bug 存在且项目一致。归档图片保持历史可读；Bug 引用的旧迭代或需求删除不影响 Bug 证据 |
| UI 源码包 | 所属 UI 生成任务存在且项目一致。替换前源码包保持历史可读；任务删除后停止签发 |
| 项目/系统技能 | 技能存在、项目归属匹配，文件 ID 仍在当前发布清单中；不提供已移除文件的历史读取 |
| UI 截图/Trace | UI 队列任务及对应调试/套件运行存在，沿套件 → 需求 → 迭代验证所属项目；调试运行还核验用例及套件归属 |

资源缺失、归属不一致、用途不匹配及未知关联类型返回 404，拒绝发生在签名生成之前；元信息入口采用同一规则。拒绝访问不会物理删除对象，也不改变正式文件的保守保留策略。已签发的 URL 保持原有效期，不承诺业务删除后即时失效。

新增 `tests/test_stored_file_access.py` 覆盖业务删除、失效关联、项目不一致、历史保留、角色变化及真实需求删除 API；`tests/test_storage_live.py` 在隔离 MySQL/RustFS 中验证需求与 Bug 删除后，另一个数据库会话不能重新申请授权，同时已有短期签名仍按原有效期工作。

2026-10-04 验证：新增 28 项关联/权限回归用例；文件、需求、Bug、技能、源码包、Worker 和 UI 运行相关回归共 160 项通过，1 项原有 MySQL 锁测试因未配置专用 `CONTROL_PLANE_TEST_DATABASE_URL` 跳过。另行显式运行隔离 MySQL/RustFS 的 8 项测试全部通过（含 2 项新增删除授权用例）。Ruff 检查通过；既有临时验收账号的 2 张 Bug 历史图片及 3 个 UI 截图/Trace 授权均为 200。扩展回归中补齐旧 UI 运行测试夹具的 `trace_path` 数据库默认值，没有修改 UI 运行业务逻辑。

## 联合备份与本机验收

新增 `python -m testing_agent.cli.storage_backup backup|verify|restore`，在维护窗口协调 MySQL 表与 S3 对象快照，拒绝覆盖在线源或非空恢复目标。具体步骤、保留方式与部署门槛见[运维说明](storage-operations.md)；本次实际业务与剩余门槛见[验收记录](s3-p1-acceptance-2026-10-03.md)。

## 需求 HTML 正文

`requirement` 用途新增 HTML，完成上传校验后清理正文并以清理后的字节更新大小与哈希，再标记 ready。需求图文正文及图片关联约定见[需求富文本正文](requirement-rich-text.md)；AI 分析适配暂缓。
