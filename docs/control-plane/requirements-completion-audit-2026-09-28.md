# 四份需求文档的实现核查（2026-09-28）

## 核查范围与结论

需求来源：`/home/xiaoming/data/文档/test-agent/需求` 下的 Bug 管理、MCP 管理与 AIWork 集成、Skill 库与 AI Worker 按需拉取、平台统一 S3 文件存储四份文档。

核查对象为本次工作区的实际代码（包含已有未提交修改），不是仅检查 Git 已提交版本。逐项结合前后端、Worker、测试和本地数据库只读查询判断。未修改业务实现、未执行清理或迁移、未调用真实模型、未重新执行登录后的业务验收或对象备份恢复演练。需求文档中的勾选和历史测试数量不视为本次证据。

**四份文档不能整体标记为全部完成。** Bug 管理存在明确功能缺口；MCP 管理第一期已实现，但第二期按需求明确暂缓；Skill 本期主体已实现，真实任务验收仍需补齐；S3 已覆盖比原文更多的业务，但浏览器重试、历史文件保护及运维验收仍不完整。

| 文档 | 当前判断 | 主要剩余项 |
| --- | --- | --- |
| Bug 管理 | 主流程已实现，部分未完成 | 计划修复迭代筛选切换、三种快捷筛选、完整 Bug 编号搜索；部分行为与原文需重新确认 |
| MCP 管理与 AIWork 集成 | 第一期已实现；总体目标未完成 | 任务映射、执行人 token 传递、nanobot 配置注入与真实工具调用均属暂缓第二期 |
| Skill 库与 AI Worker 按需拉取 | 已确认一期主体已实现，待真实任务验收 | 模型实际使用技能的端到端验收、更新并发验证；缺失代码风险技能为已确认限制 |
| 平台统一 S3 文件存储 | 主体已实现，部分未完成 | 浏览器签名过期自动重试、历史引用安全回收、对象与数据库配套恢复、真实故障/部署网络验收 |

状态含义：“已实现”表示发现完整代码链路及对应自动化依据，不承诺真实生产环境已验收；“缺口”表示代码直接不满足原文；“待确认”表示与原文不同但可能存在后续产品决策；“待验收”表示本次没有足够运行证据。

## 1. Bug 管理需求

| 原文范围 | 判断 | 实现依据或差异 |
| --- | --- | --- |
| §1 测试菜单入口、统一列表、同一详情 | 已实现 | `AppSidebar`、`BugListPage`、`BugDetailPage`，执行入口跳转同一 `/bugs/{id}` |
| §2.1 默认列和可选列 | 已实现 | `bugColumns.tsx` 包含创建人、责任人、发现/计划修复迭代等；筛选弹层提供需求、创建时间、测试单、用例可选列 |
| §2.2 项目、状态、严重程度、责任人、发现迭代筛选 | 已实现 | 前端 query 参数及后端 `BugRepository.list_by_query` |
| §2.2 切换按计划修复迭代筛选 | **缺口** | 后端支持 `sprintFilter=planned_fix`，前端 `useBugList.ts:48` 固定为 `found`，没有切换入口，标签仅为“迭代” |
| §2.2 我负责的、待回归、未关闭快捷筛选 | **缺口** | `BugListToolbar.tsx` 仅有常规下拉筛选和清空；可以手动选择部分等价条件，但未提供原文要求的快捷操作 |
| §2.2 Bug 编号/标题搜索 | **部分实现，有复现问题** | 标题、纯数字编号可查；显示值 `BUG-1` 不会转换为编号，而被当作标题查询。隔离 HTTP 测试创建标题“登录失败”的 BUG-1，按 `BUG-1` 搜索得到 total=0 |
| §3 必填字段、需求选择、描述、附件 | 已实现 | `BugFormModal`、`useBugForm`、后端字段/归属/富文本校验；富文本粘贴图片和附件接统一 S3 |
| §3 所属项目可在允许范围内选择 | **与原文不同，待确认** | 表单显示“归属项目（只读）”，没有项目下拉。可以先切全局项目再打开表单，但不等价于原文表单内可选 |
| §3.2 编号、创建人、时间、待确定初态 | 已实现 | `BugService.create`；项目内递增编号，唯一键冲突重试 |
| §3.3/§6 从执行记录带入需求、测试单、用例 | 已实现 | `TestOrderWorkspacePage` 传入来源参数，`BugSubmitPage` 带入；后端再次验证执行条目/测试单属于项目 |
| §4 六状态、全部流转、拒绝三选一、说明必填 | 已实现 | `services/bug.py` 的 `TRANSITIONS` 和 `transition`，有完整状态机测试 |
| §4 转派、编辑、评论不改变状态 | 已实现 | 独立 transfer/update/comment 方法，创建人保持不变 |
| §4/§5 多轮历史、描述修改前后、处理说明 | 已实现，文件证据保护另有风险 | `bug_activities` 保存状态、转派、评论和字段变化；正文前后可通过 `BugActivityFeed` 查看 |
| §4.4 非状态操作“关联记录” | **部分实现** | 创建时可以关联；`BugUpdateRequest`/更新服务没有来源测试单、条目、用例的更新能力。如原文要求创建后补关联，尚未完成 |
| §5 左描述/历史、右基本信息、关联跳转 | 已实现 | `BugDetailPage`、`BugDetailSidebar` 和 `BugActivityFeed` |
| §6 执行失败不自动建 Bug；关闭 Bug 不改执行结论 | 已实现 | 用户主动提交；Bug 流转代码不写执行结论 |
| §7 原文未决事项 | 不作为缺口 | ADR 0004 已补充写权限、责任人范围、编号、未关闭不含拒绝等决定；通知方式不应凭空算作必做功能 |

关键代码：[列表状态](../../apps/studio/src/features/bugs/hooks/useBugList.ts)、[工具栏](../../apps/studio/src/features/bugs/components/BugListToolbar.tsx)、[编号查询](../../apps/control-plane/src/testing_agent/repositories/bug.py)、[Bug 服务](../../apps/control-plane/src/testing_agent/services/bug.py)、[创建表单](../../apps/studio/src/features/bugs/components/BugFormModal.tsx)、[ADR 0004](adr/0004-native-bug-resource.md)。

## 2. MCP 管理与 AIWork 集成需求

| 原文范围 | 判断 | 实现依据或边界 |
| --- | --- | --- |
| §2/§3 基础服务 MCP Tab、内置禅道模板 | 已实现 | MCP provider、`zentao` 模板、模板查询和目录界面；无自定义模板/stdio/全局启停 |
| §2.3 共享服务与个人 token 分离 | 已实现 | `SharedService`、个人授权和加密凭据；API 响应不回传 token，MCP 与原禅道账号连接独立 |
| §2.4 重命名、URL 不可编辑、删除和撤销 | 已实现 | 服务更新只改名称；个人撤销和删除服务分别处理；前端禁用已有 URL 输入 |
| §3.2 权限、URL 校验、单模板唯一性 | 已实现 | 服务层权限、完整 URL 验证、`20260926_0016` 唯一约束；相关测试覆盖 |
| §3.3 管理页真实登录态及远端连接 | 待验收/范围外 | 本次不执行登录态验收或真实禅道工具调用；第一期原文明确不含连接测试接口 |
| §4 按任务/阶段选择 MCP | **未实现，按原文暂缓** | 尚无任务到内置 MCP 的运行映射 |
| §4 执行人授权解析、向 Worker 安全传递 | **未实现，按原文暂缓** | 当前配置管理不会自动注入任务凭据链路 |
| §4 写入 nanobot `tools.mcpServers`、隔离、清理、异常策略 | **未实现，按原文暂缓** | Worker 与控制面运行源码未发现该运行时集成；服务文档也明确第一期不改派发链路 |
| §5 任务范围、缺配置策略等未决问题 | 待产品决定 | 未明确前不应把第二期擅自当作一期交付失败，也不能宣称总体集成已完成 |

依据：[MCP 项目说明](builtin-mcp.md)、[共享服务](../../apps/control-plane/src/testing_agent/services/shared_service.py)、[服务表单](../../apps/studio/src/features/base-services/components/SharedServiceDialogs.tsx)、[MCP 接口测试](../../apps/control-plane/tests/test_builtin_mcp_api.py)。

## 3. Skill 库与 AI Worker 按需拉取需求

| 原文范围 | 判断 | 实现依据或边界 |
| --- | --- | --- |
| §2.1 文件夹上传、相对路径、S3 存储 | 已实现 | `skills.api.ts` 读取 `webkitRelativePath`，逐文件直传并提交 manifest；后端校验根 SKILL.md、路径、数量、体积 |
| §2.2 默认技能对已有/新项目可见、只读、来源区分 | 已实现 | 全局默认 + 当前项目查询合并；默认记录全局共享；后端拒绝默认技能删除、默认同名上传 |
| §2.3 项目自定义技能管理与权限 | 已实现 | manage 权限、跨项目文件归属检查、按项目隔离 |
| §2.5 同名完整替换、不做业务版本 | 已实现 | `replace_manifest` 替换完整清单，旧文件进入清理，标识不变，无版本选取界面 |
| §4.1/4.2 指定目录同步默认技能 | 已实现 | CLI `testing_agent.cli.skills` + `sync_builtin_skills`；从实际源文件读取而非生成替代内容 |
| §4.4 同项目同名覆盖、不同项目隔离、禁止覆盖默认 | 已实现 | scope+name 唯一约束和同步/上传碰撞校验 |
| §4.5 自定义技能本期仅管理 | 符合明确范围 | Worker 只按任务映射使用默认技能；不应把未自动注入自定义技能列为遗漏 |
| §4.6 丢弃旧压缩包技能 | 已实现 | 迁移 0021 清旧清单，文件交给 S3 生命周期；新接口为文件夹清单，无 ZIP 上传兼容 |
| §5.3 按任务/阶段拉取、恢复目录、校验、任务隔离 | 已实现 | bootstrap 接入 SkillPreparer，dispatcher 执行前调用；文件大小/hash/路径校验、独立目录和失败中止 |
| §5.3 更新后使用当前内容、无过期缓存回退 | 已实现 | 每次执行重新获取清单并拉取；完整准备后替换当前任务 skills 目录 |
| 路径补充：可读 S3 路径、旧对象清理保护 | 已实现 | `skill_storage.py` 发布到 system/projects 下技能相对路径；cleanup 避免旧记录删掉当前共用 Key |
| 没有预置技能目录时真实模型执行成功 | **待端到端验收** | 单元与模拟链路不能替代模型真的发现并使用技能；本次未发起耗费模型额度的任务 |
| 默认技能缺 `code-risk-analysis` | **已确认限制仍存在** | 本次只读数据库查得 12 个系统技能，缺此项；代码风险任务会明确失败，与原文“不自动补造”一致 |
| 更新期间的并发下载 | 已知限制、待压力验收 | 原文件同 Key 多对象覆盖不是 S3 原子事务；旧清单下载可能 hash 不符并失败，未发现静默使用混合内容；项目文档已记录需重试 |

依据：[技能项目说明](skills.md)、[前端上传](../../apps/studio/src/features/ai-testing/api/skills.api.ts)、[技能服务](../../apps/control-plane/src/testing_agent/services/project_skill_space.py)、[默认同步](../../apps/control-plane/src/testing_agent/services/builtin_skills.py)、[发布与补偿](../../apps/control-plane/src/testing_agent/services/skill_storage.py)、[Worker 准备](../../apps/ai-worker/src/testing_agent_ai_worker/platform/skills.py)。

## 4. 平台统一 S3 文件存储需求

| 原文范围 | 判断 | 实现依据或边界 |
| --- | --- | --- |
| §1–§5 配置、私有存储、稳定文件 ID、签名与元信息 | 已实现 | object_storage、stored_files、配置生成；S3 长期凭据不传给浏览器/Worker |
| §5–§6 上传授权、直传、进度、核验、事务关联 | 已实现 | XHR 直传、SHA-256、对象存在/大小/格式检查、正式 Key 封存、幂等 complete、attach 状态及权限限制 |
| §6.2/§7 浏览器签名过期后自动重新申请并有限重试 | **缺口** | `shared/api/files.ts` 一次申请、一次上传/读取，失败提示人工重试，无过期识别/重试循环 |
| §5/§6/§7 Bug 附件、富文本图片稳定引用 | 已实现，原文状态过时 | Bug create/update 关联文件，RichTextEditor 粘贴直传、保存 data-file-id；Viewer 按 ID 重新获取链接 |
| §7 图片签名过期后的显示恢复 | **部分实现** | 重新挂载/引用集合变化时重新签发；Viewer 没有图片 onError 后重新申请机制，停留页面遇到失效链接不保证自动恢复 |
| §8 Worker 即时授权、直读、校验、过期重试 | 已实现，真实场景待验收 | 独立 HTTP 客户端，最多三次，按状态重签，大小/hash 校验；任务保存稳定入口 |
| §8 下载临时文件/内存 | 满足功能、存在容量限制 | AI Worker 流读取后在内存汇总，再交给下载器写盘；不是端到端流式落盘，不将其表述为已优化完成 |
| §9 临时文件清理、失败重试、锁协调 | 已实现，真实并发待验收 | pending/ready/deleting、行锁、定时任务、删除失败计数；多实例/实际故障恢复本次未验收 |
| §9 正式/历史引用保护、安全回收 | **缺口，存在冲突实现** | Bug 移除附件直接置 `deleting`；cleanup 仅查相同 object_key 的其他活跃文件记录，不查 `bug_activities` 中旧描述/附件引用。超过 expires_at 后可物理删除历史仍引用的对象，且置 deleting 后历史签名请求已被拒绝 |
| §9 正式对象保留策略、逐文件诊断 | **部分完成** | 普通 attached 文件保守保留，但附件删除有上述例外；无通用历史引用计数/保留期限，清理日志主要计数和异常类型 |
| §10 需求和 UI 源码包仅 S3、取消本地回退 | 已实现 | 稳定文件 ID、下载授权及 ZIP 校验、运行输入快照；本次只读数据库仍有 20 条需求和 1 条源码归档没有 S3 文件 ID |
| UI 截图/Trace 统一上传、稳定引用、取消公开静态服务 | 已实现 | API/UI Worker `control_plane/artifacts.py` + 控制面 Worker 文件授权链路，前端按引用读取 |
| 项目技能接入 | 已实现，原文需同步 | 已由 ZIP/TAR 和版本关联升级为文件夹/current manifest；原文早期 ZIP/TAR 描述不应当作最终要求 |
| Bug 独立 `bugs/` 对象目录 | 未单独接入但原文仅预留 | Bug 当前使用通用 `attachment` 用途/目录；不等价于 Bug 附件未实现，也不能把预留目录列成一期阻塞 |
| 报告 | 符合当前范围 | 结构化内容入库，按需内存导出，原文 `reports/` 仅预留 |
| §11/§12 数据库与对象联合备份恢复 | **未完成验收** | 找到数据库备份与部署建议，未找到对象备份和联合恢复演练的执行证据；本次未实施 |
| 真实页面 → Worker → 模型、过期/故障/远程网络 | **待验收** | 不以历史冒烟或本次单元测试代替完整真实业务链路 |

历史文件保护问题的具体路径：旧正文包含文件 A → 编辑正文后 `bug_activities` 保留旧 HTML → 从当前附件移除 A（允许，因为只检查当前正文是否引用 A）→ A 置 deleting → 历史图片鉴权被拒绝，之后清理器可能删对象。该结论来自服务代码路径，本次没有删除任何真实文件。

依据：[浏览器文件管线](../../apps/studio/src/shared/api/files.ts)、[富文本查看器](../../apps/studio/src/shared/components/RichTextEditor/RichTextViewer.tsx)、[文件服务](../../apps/control-plane/src/testing_agent/services/stored_file.py)、[Bug 更新](../../apps/control-plane/src/testing_agent/services/bug.py)、[历史展示](../../apps/studio/src/features/bugs/components/BugActivityFeed.tsx)、[Worker 下载](../../apps/ai-worker/src/testing_agent_ai_worker/platform/http_client.py)、[UI 产物上传](../../apps/api-ui-worker/src/test_worker/control_plane/artifacts.py)、[运维说明](file-storage.md)。

## 5. 本次验证结果

| 验证 | 本次结果 | 说明 |
| --- | --- | --- |
| 控制面 Bug、MCP、Skill、迁移、文件、需求文件、UI 源码归档 | **85 通过** | `pytest -q tests/test_bug_api.py tests/test_builtin_mcp_api.py tests/test_project_skill_space.py tests/test_skill_folder_migration.py tests/test_stored_files.py tests/test_requirement_files.py tests/test_ui_case_source_archive.py` |
| AI Worker 单元测试 | **215 通过** | `python -m unittest discover -s tests/unit -v`；含技能映射、更新清单、路径/哈希校验、签名过期重新申请等 |
| API/UI Worker 相关测试 | **10 通过** | control_plane_client/config 8 项，artifact_upload 2 项；不是全量 UI 浏览器执行测试 |
| 前端 Bug、基础服务、技能 API、文件 API、富文本 | **45 通过、1 失败** | 共 17 文件、46 测试；失败为 `BugDescriptionTemplates.test.tsx` 取消一个确认框再打开另一个时匹配到两个“替 换”按钮 |
| 前端失败文件单独复跑 | **2 通过** | 说明该失败本次不能稳定复现，应跟踪弹层关闭时序/测试查询稳定性；不据此宣称批量全绿 |
| 额外的需求契约复现：完整 BUG-n 搜索 | **1 失败，确认功能缺口** | 临时隔离 HTTP 测试实际得到 total=0，期望为 1。脚本位于忽略目录 `.runtime/requirements-audit/test_search_contract.py`，未修改正式业务代码 |
| 本地数据库只读检查 | 12 个默认技能；20 条需求及 1 条源码归档缺 S3 ID | 未输出或修改个人凭据、业务正文、文件内容；未删除任何数据 |

测试环境说明：控制面先使用示例配置，因示例集成加密密钥被安全校验拒绝，首轮出现环境失败并中止；随后在忽略目录生成隔离测试配置（随机测试密钥、S3 未启用），重跑得到上述 85 项通过。示例密钥导致的失败不计为功能缺陷。测试数据库由原有测试 fixture 隔离创建，不在运行数据库执行写入。S3 单元测试使用模拟存储。本次没有宣称所有子项目的全量测试、完整登录态 UI、真实 MCP 工具调用或真实模型任务通过。

本轮日志位于 `/tmp/requirements-audit-control-final.log`、`/tmp/requirements-audit-worker.log`、`/tmp/requirements-audit-studio.log`、`/tmp/requirements-audit-template-recheck.log`、`/tmp/requirements-audit-api-worker.log`、`/tmp/requirements-audit-artifact.log` 和 `/tmp/requirements-audit-search.log`，为临时验证记录，不作为长期归档或稳定链接。

## 6. 建议处理顺序

1. 先补历史文件引用保护，避免清理破坏 Bug 的历史证据；再验证“编辑旧正文→移除附件→清理→历史查看”完整流程。
2. 修复完整 `BUG-n` 搜索，补计划修复迭代筛选切换和三种快捷筛选。
3. 确认创建 Bug 时项目只读、创建后不能调整来源关联是否属于后续产品决定；若无后续决定，按原需求补齐。
4. 补浏览器上传/下载签名过期的有限重试，覆盖图片显示失败后的重新授权。
5. 完成真实任务、清理并发/故障、部署网络和对象/数据库联合恢复验收；历史缺文件需找回或重新上传/执行。
6. 单独明确 MCP 第二期的任务/阶段映射与缺少授权策略，再实施运行时集成。
7. 更新原始需求文档：S3 的“Bug 未接入”“技能 ZIP/TAR 版本关联”等状态已过时；不要继续沿用旧测试数量作为当前验收结论。
