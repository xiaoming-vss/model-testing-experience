# Skill 文件夹管理与默认技能

基础服务中的 Skill 库合并展示全局默认技能与当前项目自定义技能。默认技能通过全局查询自动对已有／新项目可见，不为项目复制文件；项目所有者仅能维护自定义技能。

## 初始化与覆盖更新

在控制面目录使用其既有配置（`config/local.toml` 或 `APP_CONF`）：

```sh
uv run alembic upgrade head
uv run python -m testing_agent.cli.skills /home/xiaoming/下载/skills/default-skill
```

其他环境将源文件夹复制到可访问目录，传入对应绝对路径即可；源技能文件不写入代码仓库，脚本不读取 Worker 私有目录。首批源有 12 个技能，缺少 `code-risk-analysis` 时其任务明确报错。后续维护源目录后重新执行脚本：同名技能整体替换，不递增版本，不提供回滚。删除源目录中的文件后再次同步，该文件不再出现在技能清单中；删除整个源技能文件夹不会自动删除系统技能。

迁移 `20260927_0021` 按已确认需求丢弃旧压缩包技能记录，将其关联文件交给 S3 清理流程，不做压缩包数据迁移；迁移不可逆恢复旧数据。默认技能是 `project_id=NULL`、`scope_key=system` 的资源，自定义技能使用项目 ID 作为 scope。唯一约束为 scope + 文件夹名。

## 上传和下载

1. 前端选择单个文件夹，要求根目录有 `SKILL.md`。标识取文件夹名（1–128 字符，以字母或数字开头，后续允许字母、数字、点、横线、下划线）。
2. 每个文件通过统一上传接口以 `purpose=project_skill` 直传 S3；此用途要求项目管理权限，允许脚本、无扩展名及空文件，不再限制 ZIP/TAR。
3. 文件全部完成校验后，`POST /v1/projects/{projectId}/skills` 提交 `{name, files: [{path, fileId}]}`。path 相对技能根目录，不包含外层文件夹名。
4. 后端校验项目、上传人、用途、文件名、路径及完整清单后一次性发布。最多 2000 个文件，总大小不超过统一 S3 单文件上限；拒绝路径穿越、重复路径及文件／目录冲突。
5. 同项目同名自定义技能覆盖当前文件集合；禁止与系统默认技能同名。默认技能在后端也禁止删除。
6. `GET /v1/projects/{projectId}/skills/{skillId}/download` 验证读权限后临时组装 ZIP 下载；压缩仅用于导出，不保留 ZIP 原件。列表无版本字段，包含来源、文件数、大小及更新时间。

旧文件在切换后标记为 deleting，等待签名有效期结束后由统一清理器回收。失败上传仍由临时文件生命周期回收，数据库只保留当前清单；已发布文件按原始目录保存：`<prefix>/skills/system/<技能名>/<相对路径>` 或 `<prefix>/skills/projects/<项目ID>/<技能名>/<相对路径>`。文件 ID 仅用于数据库关联；上传中的文件和失败补偿临时副本位于 `<prefix>/_temporary/skills/`，由清理器回收。覆盖后清理器跳过仍被当前文件引用的同名对象，避免误删新内容。

已有 ID 路径执行 `uv run python -m testing_agent.cli.skills --migrate-paths` 迁移，保留技能及文件 ID，重复执行安全；旧对象在签名有效期后回收。S3 多文件覆盖不是原子操作，更新期间正在下载的 Worker 可能遇到哈希不符并中止准备；新任务重试后拉取当前内容。复制或提交失败会尝试恢复覆盖前内容，不提供业务版本或历史回滚。

## Worker

`GET /internal/ai-worker/tasks/{taskId}/skills/{name}?workerId=...` 返回当前默认技能文件清单；其 `/files/{fileId}` 子路由返回单文件 S3 票据。两者均要求 Worker Token、任务所属 Worker、有效租约及执行者有效授权；只提供系统默认技能。签名响应 no-store，不向 S3 传 Worker Token。

任务／阶段映射保持 Worker 原有技能名称。每次执行先完整拉取到临时目录并验证内容，再提供给执行器；任务之间目录隔离。默认技能缺失、网络或校验失败均中止准备，不静默使用过期技能。自定义技能本期仅管理，不改变任务选择。

## 本地初始化验证（2026-09-27）

本地 MySQL 已升级到 `20260927_0021`（含前置 Bug 迁移 `0020`）。迁移前旧技能记录为 0；MySQL 在移除旧唯一索引前建立独立项目索引，保持外键有效。指定源目录的 12 个默认技能、62 个文件已同步到真实 S3，并逐文件签名下载比对源内容；两个现有项目均可读取 12 个默认技能。无在途 AI 任务时已重启 Worker，新进程正常轮询。未调用真实模型生成任务；自动化浏览器未登录，尚未完成登录后的视觉验收。


2026-09-27 路径迁移已在本地完成：13 个 Skill、67 个文件（含项目自定义 `testing-case`），新对象路径、文件大小和 SHA-256 逐项校验通过。旧 ID 对象进入签名有效期后的清理流程。

## 两阶段需求分析技能更新（2026-10-06）

按用户要求，从 `/home/xiaoming/下载/skills/default-skill-003` 更新五个系统默认技能：`extract-docx-enhanced-text`、`prd-feature-understanding-skill`、`analyze-functional-requirements`、`generate-solution-test-points`、`generate-solution-test-cases`。使用既有 `sync_builtin_skills` 发布服务，保留其它默认技能与项目自定义技能。共 33 个文件，已逐文件下载真实 S3 内容并比对源文件、清单、大小及 SHA-256，全部一致。

推送与重启前确认 AI 队列无 pending/running 任务。AI Worker 已重启加载新两阶段执行代码并恢复正常轮询；没有调用真实模型，待用户发起新需求分析运行验收。随后用户确认旧流程全部删除：旧中间阶段已从默认库移除，两个现用技能删除五份 legacy 参考文件后重新同步（共 11 个文件）并逐项校验；22 条旧运行及其关联记录已删除。原 AI Worker 已停止领取并等待当前新运行完成；新 AI Worker 已加载清理后的代码并正常轮询。

## 问题闭环更新（2026-10-07）

两个需求分析默认技能更新为：明确答复先写入对应事实或需求理解正文，更新来源及确认状态，再删除已解决问题与相关引用；部分回答只保留剩余缺口，全部解决时 questions=[]。不输出 resolved 问题，不另建问答历史。平台和 Worker 的新输出契约同步收窄；已有已回答产物允许作为 AI 继续优化的输入。

已从 default-skill-003 的两个源目录通过既有发布服务覆盖默认库，共11个文件，真实 S3 下载内容、大小及 SHA-256 逐项一致。AI 队列为空时已重启本地 AI Worker，新进程正常轮询。未替用户提交真实需求审核或调用模型修订业务产物。


## 2026-10-08 Word 与富文本提取技能

从 `/home/xiaoming/下载/skills/default-skill-004` 通过既有 `sync_builtin_skills` 发布服务更新 `extract-docx-enhanced-text`、新增 `extract-richtext-enhanced-text`，其余默认及自定义技能不变。共 10 个文件，已读取真实 S3 对象逐项比对源内容、大小及 SHA-256，全部一致。Word 技能不再接收 TXT 主文档；Worker 按 Word/DOCX 与 richtext 选择第一阶段技能，后续分析逻辑及输出契约一致。详见[两阶段需求分析](../ai-worker/requirement-analysis-two-stage-design.md#2026-10-08-富文本输入接入)。

同步时 AI 队列无 pending/claimed/running 任务，已重启本地 AI Worker 并确认恢复轮询；控制面自动重载后在线 OpenAPI 已注册图片下载接口。未提交真实模型分析或代替用户审核业务产物。
