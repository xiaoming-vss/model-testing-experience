Method: dual-agent (A: /root/assessment_a · B: /root/assessment_b)

# Studio 前端质量与使用体验检查报告

检查日期：2026-10-08（Asia/Shanghai）。对象：`apps/studio` 当前工作区，包含检查前已经存在的未提交修改；基线提交 `96919da94f672bbc45ae2a8eb8513a20f7e8bd67`。本轮只检查，未修改业务代码、依赖或锁文件，未审查后端内部实现，未执行真实业务写入或付费任务。

## 结论

**桌面工作台的业务结构和公共组件基础较好，但目前不能给出“全面好用、可直接发布”的结论。** 类型、Lint、主题和构建通过，测试有 5 个失败；窄屏存在导航入口消失、测试单名称列零宽两个直接影响使用的问题。执行保存反馈、认证恢复、错误状态和键盘操作也有需要处理的缺陷。

本报告列出 **16 项已确认问题：P0 0 项、P1 4 项、P2 12 项**，其中 F16 是工程检查失败集合；另外列出 5 项体验改进建议及 8 类未验证风险。源码确认不等于真实后端端到端复现，以下每项均注明证据层级。

优先前五项：

1. **F01 / P1：恢复 ≤900px 的全站导航**，提供可聚焦的抽屉菜单或保留紧凑侧栏。
2. **F02 / P1：保证测试单名称列可见**，设置合理最小表宽与横向滚动，避免名称列被压为 0。
3. **F03 / P1：保存失败必须明确显示未保存**，不能继续使用旧的“已保存”主状态文案。
4. **F04 / P1：修正浅色登录文字和错误提示的对比度**，通过现有语义 token 调整。
5. **F16 / P2：处理 5 项测试失败**，先明确开发成员需求深链契约，再更新过时断言并重跑；不应直接放宽检查使其变绿。

## 方法、环境与证据可信度

- 使用 Impeccable `audit` 和 `critique`。A 独立进行设计与体验评估；B 独立运行 detector、技术审阅和浏览器检查。A 首轮评估完成后才接收 B 的扫描结果；主代理补充工作台、状态和不同宽度的验证。另一个代理运行现有工程检查。
- 按 `apps/studio/AGENTS.md`、`CONTEXT-MAP.md` 阅读 Studio 的 CONTEXT、DESIGN、STRUCTURE、UI-GUIDELINES，以及主题 ADR 0002、富文本 ADR 0003。以现有 Ant Design、靛蓝/琥珀浅色、GitHub Dark 和公共 token 为基准，不把视觉偏好、导航项超过四个或引用边线直接当作缺陷。
- 实际前端 `127.0.0.1:5173` 可打开，浏览器没有登录态，也未收到测试凭据。真实服务仅检查登录/注册展示、空表单校验和密码恢复占位反馈。
- 工作台使用**当前生产组件和生产路由 + 隔离示例数据**。临时环境拦截 fetch，不向真实后端透传，并阻止写入；只用于展示、交互和异常验证。需求详情使用已有 `.codex-requirement-tabs-check` 示例。它们不证明真实 API、认证、保存、生成或执行成功。
- 实测桌面 1280×720/800、窄屏 760×1000、手机宽度 390×844；另有初始宽桌面观察。只在代表页测试尺寸，不声称每页所有尺寸均通过。
- 检查过程中观察到外部已有工作的 HMR 更新和预览端口被替换。替换后的非审计页面观察未用于判定缺陷，核心工作台发现用独占端口 54387 复核。工程结果是该轮命令执行时的结果，不代表后续其他修改也已验证。证据清单记录关键文件在报告准备时的 SHA-256。
- 证据等级：**B** 浏览器实际观察；**S** 源码可确定；**T** 现有自动化检查；**M** 读取实际源码后的内存隔离复现。未做的检查明确写“未验证”，不按通过计算。

完整工程日志、扫描原始 JSON 与浏览器观察记录见 [证据目录](audit-evidence-2026-10-08/verification.json)。本轮没有注入页面 detector overlay：浏览器 evaluate 为只读，使用 DOM/AX、截图观察、源码及 CLI 扫描作为证据。

## 页面与检查项覆盖

下表的“测试”表示全量已有测试已运行并抽查相关断言，不等于新增了端到端测试。路径均相对 `apps/studio/src`。

| 页面/路由 | 浏览器覆盖 | 源码/测试核对 | 未验证部分 |
| --- | --- | --- | --- |
| `/login`、`/register` | 真实页面；主动作、空登录校验、忘记密码反馈、标签和浅色对比度 | AuthPage、auth store、ProtectedRoute；认证测试主要覆盖外观 | 真实登录/注册成功、账号约束、注册冲突、认证慢请求重复提交 |
| 全局 AppShell / Sidebar | 隔离生产外壳；主导航、范围、测试 Tab、只读动作；760/390 导航丢失 | AppSidebar/AppShell、角色 guard、项目菜单测试 | 真实多项目切换、会话权限变化、无项目账号 |
| `/projects?board=sprints` | 隔离迭代卡片、刷新/新建/编辑入口观察 | ProjectsPage、SprintBoard、SprintDrawer、测试 | 真实新建/编辑/删除、禅道绑定和同步 |
| `/projects?board=requirements` | 隔离空态、主操作和路由切换 | 需求列表、行操作、作用域、项目菜单测试 | 真实需求分页、后台筛选、导入同步 |
| `/projects/:projectId/sprints/:sprintId` | 未浏览器验证 | SprintDetailPage 与已有测试 | 指标/代码变更/报告的真实数据和交互 |
| `/requirements/:requirementId` 文档 | 当前生产组件；真实示例 DOCX/结构化长内容；760px 上下对照与键盘分隔线 | RequirementDetailPage、文档预览、权限边界、相关测试 | 真实下载授权失效、不同文件类型/超大文件、移动触摸 |
| 同页需求分析 | 四条隔离运行：待审核、失败、拒绝、已导入；错误弹窗/Escape、运行行 DOM | workspace hook、RunHistoryTable、轮询/对话框测试 | 真实分析、检查点推进、审核及导入；后台分页/状态持续变化 |
| 同页功能/API/UI 设计 | 页签和流程结构由源码核对 | 配置、运行依赖、幂等请求 ID、busy、对话框测试 | 四类生成的真实完成流程；API/UI 配置和源码上传未浏览器完整操作 |
| `/testing?tab=orders` | 隔离有数据、搜索无结果/清空、新建必填、只读禁用、长名称、读取失败；1280/760/390 | TestOrderPage、Drawer、列表测试 | 保存成功、真实服务端过滤/分页、执行工作台数据 |
| `/testing?tab=library` | 键盘 ArrowRight 进入；测试集/用例空态和禁用动作 | 列表与现有测试 | 树选择、导入、批量操作及真实多页数据 |
| `/testing?tab=api` | 空态、环境禁用、新建抽屉和字段；未提交有效表单 | API 页面/集合数据 hook、执行轮询测试 | API 真实执行、环境切换结果、断言/报告 |
| `/testing?tab=ui` | 空态、主入口、760px 换行/边界 | UI 页面、套件/步骤/运行测试 | UI 真实执行、回放、截图与日志完整链路 |
| `/testing?tab=bugs` | 空态、筛选弹层、附加列选择入口 | Bug columns、角色展示、相关测试 | 有数据的长标题/附件、状态更新、转派、评论 |
| `/bugs/new`、`/bugs/:bugId` | 未浏览器验证 | 页面/富文本及既有测试抽查 | 实际提交、上传、评论、状态流转、权限角色矩阵 |
| `/test-orders/:orderId` | 未浏览器验证 | 保存反馈、快捷键、权限及已有执行测试 | 真实执行保存、冲突、刷新恢复、批量判定、长列表性能 |
| `/test-orders/:orderId/graph` | 未浏览器验证 | 独立受保护路由及图谱相关实现 | 大图、键盘/触摸、导出 |
| `/ai-testing`、`/ai-testing/tasks` | 代码风险入口；隔离九条任务、状态栏及操作观察 | UnifiedAiTestingPage 与入口/范围测试 | 真正运行、后端统计与筛选一致性 |
| 五类任务详情、功能关系图 | 未浏览器逐页验证 | 共享历史/操作/轮询；五类详情测试已运行 | 每类产物、长报告、导入冲突、失败恢复端到端 |
| `/api-automation/collections/:collectionId` | 未浏览器验证 | 编辑/执行 hook、集合页测试 | 请求编辑、变量、报告、实际网络执行 |
| `/ui-automation/suites/:suiteId` | 未浏览器验证 | 套件详情、步骤/导入/运行测试 | 大套件、拖动排序、运行中刷新与执行结果 |
| `/base-services`（GitLab/LLM/MCP/Skill） | LLM 空态、分类切换、Skill 空态/入口 | BaseServicesPage、个人授权与共享服务逻辑 | 真实连接/鉴权、连接校验、Skill 上传和权限变更 |
| `/profile` | 未浏览器验证 | 路由与页面结构 | 个人信息/密码修改，不操作真实凭据 |
| 兼容入口 `/test-cases`、`/api-automation`、`/ui-automation`、旧 skills 路由 | 源码核对重定向 | AppShell 兼容路由；TestingPage 旧 functional 链接测试 | 所有旧深链接真实登录后的恢复 |

### 状态与交互覆盖

| 检查项 | 已完成 | 边界 |
| --- | --- | --- |
| 加载 | 检查 loading/isPending、运行 busy，观察列表切换过渡 | 未用慢网覆盖所有页面骨架/超时 |
| 空数据 | 用例库、API/UI、Bug、需求、服务/Skill 等隔离空态 | 未证明每一页空态都正确 |
| 失败 | 登录空值、模型失败信息；测试单 GET 失败；源码删除/保存错误 | 未故障注入真实后端 |
| 成功 | 示例完成运行、审核/拒绝/导入状态及对应按钮 | 未真实发起任务或确认写入 |
| 禁用/权限 | 只读测试单创建/编辑/删除禁用，有原因；角色源码/测试 | 未登录 owner/member/viewer/developer 逐角色验收 |
| 筛选/刷新 | 测试单搜索、清空恢复；Bug 筛选入口；缓存/轮询测试 | mock 不证明服务端分页和新数据刷新正确 |
| 分页 | 共享分页、总数、禁用上一/下一页观察；现有分页测试 | 未验证真实第二页数据与跨页选择 |
| 重复提交 | 检查 loading/busy、部分表单 guard 和生成 requestId | 缺少延迟请求下连点/Enter 的完整实测 |
| 键盘 | 测试 Tab ArrowRight、错误弹窗 Escape、文档分隔线；运行行 DOM | 非全屏幕阅读器/全流程键盘验收 |
| 适配/长文本 | 工作台 760/390；超长测试单名称；长需求上下对照 | 未测所有页200%缩放、触屏与不同浏览器 |

## 工程质量结果

| 命令 | 结果 | 证据 |
| --- | --- | --- |
| `npm run type-check` | 通过，退出 0 | [type.log](audit-evidence-2026-10-08/type.log) |
| `npm run lint` | 通过，退出 0 | [lint.log](audit-evidence-2026-10-08/lint.log) |
| `npm run check:theme` | 通过，80 CSS、288 TS/TSX | [theme.log](audit-evidence-2026-10-08/theme.log) |
| `npm test` | **失败**，120 文件中 4 失败；710 用例中 5 失败、705 通过；216.07s | [test.log](audit-evidence-2026-10-08/test.log) |
| `npm run build` | 通过；主 JS 4,024.49 kB、gzip 1,203.91 kB；CSS 556.40 kB、gzip 79.93 kB；有超过500kB警告 | [build.log](audit-evidence-2026-10-08/build.log) |

未运行 `lint:fix`，未安装依赖。构建产生正常的忽略产物，未提交产物。未修改编排配置，因此没有扩展到后端或编排测试。

## 已确认问题（按严重程度）

位置均相对 `apps/studio/src/`；行号为检查时定位，工作区其他并行修改可能使行号移动。关键文件指纹见 verification.json。

### F01 · P1 · 窄屏全站导航消失

- **影响**：窗口变窄后无法从测试切换到需求、Bug、代码风险或基础服务；用户必须记 URL 或重新放大窗口。
- **位置**：`shared/styles/page-frame.css:1040` 的 ≤900px 规则，`:1049` 将 `.app-sider` 设为 `display:none`；`app/layouts/AppSidebar.tsx:39`；AppShell 没有替代移动菜单。
- **证据 B+S**：760×1000 的 UI 测试页和390×844测试单页中主导航、服务导航均不出现在可访问树；DOM 显示两个 nav 所属 aside 的 display 为 none。顶部只有项目范围、新建项目、主题和个人菜单。
- **复现**：进入任意工作台，缩到760px，尝试使用界面进入 Bug/基础服务。
- **建议**：复用现有导航项和 `aria-current`，增加窄屏抽屉触发器、焦点管理与 Escape 关闭，或保留紧凑可用导航。对应 `$impeccable adapt`。

### F02 · P1 · 测试单名称列在窄屏压为零宽

- **影响**：记录最重要的身份信息不可见，无法确定正在查看/编辑/进入哪个测试单；横向滚动也不能恢复零宽列。
- **位置**：`features/test-orders/pages/TestOrderPage.tsx:108` 名称列宽24%，其余六列合计970px；`:399` 的 Table 没有匹配最小列宽的 `scroll.x`。
- **证据 B+S**：390px 时名称表头 rect.width=0，后续列宽为130/130/300/110/170/130；表格 scrollWidth=970、clientWidth=364、scrollLeft=0。760px 时名称列仍为0。普通名称及重复八次的长名称均看不见；根文档没有横向溢出并不代表表格可用。
- **复现**：显示多条测试单，将窗口缩为760或390px，观察列表第一列并读取表头宽度。
- **建议**：给名称列稳定最小宽度，令总表宽至少容纳所有列，通过表格内部横向滚动承载；可评估固定名称列。不要只测 document.scrollWidth。对应 `$impeccable adapt`。

### F03 · P1 · 保存失败后仍显示旧“已保存”状态

- **影响**：测试执行者可能误认为当前结果已经保存并继续下一条，降低执行证据可信度。
- **位置**：`features/test-orders/pages/TestOrderWorkspacePage.tsx:199` 成功后更新 savedAt；`:266` 文案只看 isPending 和 savedAt；`:638` 仅通过 danger 颜色表达 isError。
- **证据 S**：一次成功保存后，下一次失败不清除 savedAt，最终显示红色“已保存 [上次时间]”。已有 onError toast，**不是完全没有错误提示**，但持久状态与本次结果相矛盾。
- **复现条件**：同一工作台先成功保存，再让下一次保存失败；本轮未发送真实保存请求。
- **建议**：持久显示“保存失败，当前修改未保存”及重试，单独标注“上次成功保存时间”；切换条目时明确反馈属于哪条。对应 `$impeccable harden`。

### F04 · P1 · 浅色登录辅助文字和错误文字对比度不足

- **影响**：小字号说明、登录提示和错误信息对低视力用户不易辨认。
- **位置**：`shared/styles/foundation-tokens.css:531`、`:532`、`:543`；`features/auth/styles/auth.css:151`、`:230`、`:240`、`:276`。
- **证据 B+S**：独立浏览器取得12–14px文字值 rgba(24,32,45,.54)、rgba(24,32,45,.42)，12px错误 rgba(220,38,38,.82)，内容面 rgb(232,237,246)。按 alpha 合成计算约3.47:1、2.50:1、3.45:1，低于普通文字4.5:1。背景包含轻微渐变/透明层，因此这些是采样背景下的估算，不是全页像素认证。
- **建议**：调整辅助文字和错误语义 token 的不透明度/色值，再对实际合成背景复测；保留已确认配色方向。对应 `$impeccable colorize`。

### F05 · P2 · “保持登录”选择无效

- **影响**：用户取消勾选后仍得到持久登录行为，界面承诺与行为不符。
- **位置**：`features/auth/pages/AuthPage.tsx:96` 的原生 checkbox 无状态绑定；`features/auth/store/auth.store.ts:18` 无条件向 localStorage 写 token。
- **证据 S+B展示**：未登录浏览器可见控件；持久化逻辑不读取 checkbox。未真实登录复现。
- **建议**：实现明确的会话/持久化语义，或移除没有效果的选项；覆盖勾选/不勾选和重开页面。对应 `$impeccable harden`。

### F06 · P2 · 密码恢复是占位入口

- **影响**：忘记密码的用户进入死路，无法知道下一步可行操作。
- **位置**：`features/auth/pages/AuthPage.tsx:79`。
- **证据 B+S**：点击“忘记密码？”只显示“暂未开放”，没有恢复或联系指引。
- **建议**：展示真实可用的恢复途径；在功能未提供期间用明确说明代替看似可操作的恢复流程。对应 `$impeccable clarify`。

### F07 · P2 · 登录后精确链接丢失查询参数和 hash

- **影响**：原本访问 API/Bug/需求子页或精确执行条目的用户登录后进入默认视图，需要重新定位。
- **位置**：`app/router/guards/ProtectedRoute.tsx:7` 保存 location；`features/auth/pages/AuthPage.tsx:19` 只取 pathname，`:33` 导航。
- **证据 S**：`/testing?tab=bugs` 只能恢复成 `/testing`。未用真实账号执行登录。
- **建议**：完整恢复 pathname+search+hash，并限制站内目标；为 tab、筛选及 entryId 深链补行为测试。对应 `$impeccable harden`。

### F08 · P2 · 旧请求返回401会注销新会话

- **影响**：网络迟缓时，用户退出再登录后可能被旧请求错误再次登出。
- **位置**：`shared/api/request.ts:87` 捕获 token；`:109`、`:154` 收到401后无条件 logout。
- **证据 M+S**：工程代理读取真实 request.ts，使用现有 TypeScript 转译和内存 store/fetch stub：旧token发请求→切换新token→旧响应401→实际token=null，预期应保留新token。没有改源码或请求真实服务。
- **建议**：认证错误副作用只作用于发起请求时的会话，同时完善取消请求与回归用例。对应 `$impeccable harden`。

### F09 · P2 · 跨项目详情深链可能按错误项目角色重定向

- **影响**：用户有权访问项目B资源，却因当前/默认项目A为开发成员而被带到A的Bug列表。
- **位置**：`features/projects/hooks/useActiveProject.ts:26` 无当前范围时选择首项目；`app/router/guards/ProjectRouteGuard.tsx:17` 先按 activeProjectId 判权限。
- **证据 S**：需求详情有 canonical project 特判，但其他测试单、AI任务、API/UI详情在获取资源所属项目之前被外层 guard 拦截。条件为A是默认或当前项目且仅bug_read，B拥有read权限。未真实跨角色账号复现。
- **建议**：资源详情先解析其项目再做展示门控，统一深链策略；保留对真正无权资源的处理。不要简单放开所有页面。对应 `$impeccable harden`。

### F10 · P2 · 运行历史行选择缺键盘等价操作

- **影响**：仅键盘用户无法单独选择运行记录以切换高亮/材料快照上下文；产物/审核按钮本身仍可用，不等于所有运行操作不可访问。
- **位置**：`features/ai-testing/components/RunHistoryTable.tsx:151` 只为行提供 onClick；编号是span。
- **证据 B+S**：四条示例运行的tr都没有tabindex/role；按钮只有复制、产物、审核/错误/重试和删除，没有“选择运行”。运行选中值被 workspace用于选中详情和快照检查。
- **建议**：提供明确的选择运行按钮或遵循表格选择模式，包含可见focus和选中语义；避免只加全行tabindex却无标签。对应 `$impeccable harden`。

### F11 · P2 · 项目/迭代删除失败缺少持久反馈

- **影响**：失败后只见确认框不关闭或记录仍在，用户不知道原因以及是否应该重试。
- **位置**：`features/projects/pages/ProjectsPage.tsx:187`、`:211` 删除mutation只有onSuccess；项目删除确认 `ProjectActionModal`；`features/projects/components/SprintBoard.tsx:51`。
- **证据 S**：未消费删除mutation.error，无onError；迭代确认回调调用mutate不返回Promise。请求封装只抛错，QueryProvider无全局mutation提示。未调用真实删除。
- **建议**：使用可等待的mutateAsync，在确认区域显示原因并允许重试。现有 `RequirementRowActions.tsx:14` 的catch/提示/rethrow可作一致模式。对应 `$impeccable harden`。

### F12 · P2 · 文档对照窄屏分隔线数值改变但布局不变

- **影响**：用户看见可拖分隔线，却不能调整上下阅读空间；键盘方向和语义也与布局不符。
- **位置**：`features/testing/styles/index.css:1403` 在≤980px强制单列/等高双行；`features/requirements/components/RequirementDocumentPreviewModal.tsx:379` 仅算clientX，`:388`只支持左右，`:457`只改columns，`:470`仍为vertical。
- **证据 B+S**：760px，ArrowRight后aria-valuenow从50变52，grid rows仍323px 1px 323px，columns仍702px。不是仅静态推断。
- **建议**：窄屏采用纵向比例、上下键及horizontal separator语义，或明确取消此时的调整功能；触摸另测。对应 `$impeccable adapt`。

### F13 · P2 · 功能生成阻断提示不对应实际解除条件

- **影响**：新成员被要求“补充需求增强文本”，却没有当前页入口，不知道要先完成需求分析与采用产物。
- **位置**：`features/ai-testing/components/RequirementDesignWorkspace.tsx:42`；`features/ai-testing/hooks/useRequirementDesignWorkspace.ts:96` 实际判断adoptedUnderstanding。
- **证据 S**：功能Tab没有API/UI才有的“设置”动作；文案没有明确分析→审核→导入/采用链路。本次fixture已有采用结果，未把它当作缺少采用状态的浏览器复现。
- **建议**：按真实未满足条件提示，并提供前往需求分析的动作；沿用CONTEXT术语，区分人工检查点、审核与正式导入。对应 `$impeccable clarify`。

### F14 · P2 · 迭代等筛选框没有可访问名称

- **影响**：屏幕阅读器用户只听到无名组合框，难以区分全局迭代、局部范围等控件。
- **位置**：`app/layouts/AppShell.tsx:112`；`features/test-orders/pages/TestOrderPage.tsx` 的迭代Select。Bug高级筛选也有同类无名状态/严重程度/责任人控件。
- **证据 B+S**：DOM/AX中“当前项目”有aria-label，但当前迭代和测试单局部迭代没有label/labelledby，旁边span不构成程序关联；Bug确认情况/解决方案有名称，可作对照。
- **建议**：给Select关联可见label或准确aria-label，避免只加placeholder。对应 `$impeccable harden`。

### F15 · P2 · 读取失败仍展示“没有数据”及创建引导

- **影响**：用户可能把暂时获取失败误认为原来没有测试单，错误创建重复记录或怀疑数据丢失。
- **位置**：`features/test-orders/pages/TestOrderPage.tsx:339`错误Alert与`:360`空态分支相互独立。
- **证据 B+S**：隔离GET抛错后，同页同时显示“网络暂不可用”“当前迭代下还没有测试单”和“新建测试单”CTA。
- **建议**：首次读取失败优先显示失败+重试；有旧数据时保留并标注过期；只在成功且为空时显示创建引导。对应 `$impeccable harden`。

### F16 · P2 · 现有测试有5项失败，质量门禁未全绿

- **影响**：当前测试结果不能作为可发布依据；其中一项权限导航契约需要产品/实现一致处理，其他失败削弱持续集成的信号质量。
- **证据 T**：详见test.log，具体分类如下，不把测试名称直接当功能漏洞。

| 失败文件/用例 | 已核实含义 | 建议 |
| --- | --- | --- |
| `app/layouts/AppShell.developer.test.tsx`：开发成员直接访问 `/requirements/r` | 当前requirement路由豁免外层guard，与旧“回Bug且不请求其他资源”断言冲突。真实403时的用户最终落点未登录验证，**不能据此宣称后端越权** | 明确跨项目深链与开发角色访问需求的契约，再调整实现及测试 |
| `AppShell.projectMenu.test.tsx`：只读设置 / 旧项目参数，两项 | 都先等“暂无迭代”，现空态/默认面板已变化；源码仍有manage门控 | 更新等待条件至真实可观察状态，再保留权限断言 |
| `app/styles/paginationConsistency.test.ts` | requirements-list.css、sprint-board.css的footer flex布局命中宽泛禁止规则 | 区分公共分页外观与合法外层布局；不要删除一致性检查 |
| `features/ai-testing/api/aiTesting.storage.test.ts:18` | 期待3参数，实际上传函数多第4个undefined；不是已证明上传失败 | 同步调用契约断言并保留上传行为校验 |

## 体验改进建议（不计入确认缺陷）

| 编号 | 建议与影响 | 位置/依据 | 方向 |
| --- | --- | --- | --- |
| U01 | Bug默认列信息密度较高，处理人员需横向比较归属、责任人与时间；可按常用决策减少默认列、保留附加列控制 | `features/bugs/components/bugColumns.tsx:17`；已有筛选/显示弹层是良好基础 | `$impeccable distill`，不是机械限制列数 |
| U02 | 基础服务Tab与测试Tab键盘和历史行为不一致；前者replace历史，缺箭头/Home/End模式 | `features/base-services/pages/BaseServicesPage.tsx:41`、`:52`；测试Tab已有完整实现 | 先明确返回预期，再复用一致Tab交互 |
| U03 | 登录品牌区“项目总览 / AI测试”与新导航名略滞后，新人需额外映射 | `features/auth/pages/AuthPage.tsx:53` | `$impeccable clarify`；不需要重做配色或品牌 |
| U04 | 错误详情可保留诊断文本，但主要恢复路径应在上下文中表达 | `RequirementDesignWorkspace.tsx:49` raw pre；实际内容因任务而异 | 给任务级说明/重试条件，保留展开技术细节 |
| U05 | 主包gzip约1.2MB，全部业务路由静态导入；轻入口也承担编辑器/图谱依赖 | `app/layouts/AppShell.tsx:2`、build.log；ADR0003记录过无分包取舍 | `$impeccable optimize`：先测冷启动/路由成本，再按路由拆包；不直接宣称LCP不达标 |

## 未验证风险与后续验收范围

1. **真实权限与深链**：未用四类项目角色、跨项目资源、权限撤回和403实际验证。开发成员需求详情属于已出现测试分歧，需同时验证可见内容和跳转落点。
2. **长任务端到端**：没有启动模型、API/UI执行、禅道同步，也没有审核、导入、重试、付费调用。现有轮询/终态刷新测试通过不能替代断网恢复、刷新重连及真实排队任务验证。
3. **重复提交**：多个Form只有按钮loading，onFinish没有pending guard，键盘Enter/快速提交是否会产生重复请求未延迟实测；需求Drawer已有loading guard，需求生成有requestId与busy。不要笼统判断全站无防重。
4. **执行快捷键串扰**：`TestOrderWorkspacePage.tsx:238` 的window监听只排除INPUT/TEXTAREA，未全面检查modal、contenteditable、modifier、defaultPrevented；需在分配弹窗/下拉打开时测试1–4和方向键。未实测，不作为已确认错误判定。
5. **未知路由/渲染失败恢复**：AppShell内无`*`兜底，未发现全局ErrorBoundary；异常路径可能留下空壳或白屏，尚未浏览器故障注入。
6. **性能与大数据**：未测LCP/INP、内存、1000条列表、大图谱、长日志、超大DOCX；体积警告是事实，实际卡顿未证实。
7. **无障碍与设备**：未做NVDA/VoiceOver、200%缩放、触摸手势、真实手机、多浏览器完整验收。已测尺寸只覆盖代表页；不宣称全站WCAG合规。
8. **真实文件与外部服务**：S3下载授权、上传中断、GitLab/LLM/MCP授权、图片粘贴、外部绑定均未实测；隔离DOCX展示成功不意味着生产下载链路通过。

## Impeccable audit / critique 综合评估

### 实现完整性与产品特异性

**产品体系基本一致，完整性验收未通过。** 项目/迭代/需求范围、人工检查点、审核和正式资产导入形成明确测试业务模型；公共列表、主题、权限按钮和分页有较好复用。主要短板是操作承诺、错误反馈、窄屏和键盘能力不完全一致，而不是缺少装饰或配色不够“大胆”。

detector发现不是缺陷清单：本轮21条warning，经核验12条broken-image全部为测试HTML或匹配图片标签的正则误报；8条side-tab多数是引用、状态或图节点语义，未证明用户影响；1条进度条width transition真实存在，但已有reduced-motion规则，未证实性能故障。**不将21条warning计为21项缺陷。** 原始输出见[detector.json](audit-evidence-2026-10-08/detector.json)。

| Audit维度 | 0–4分 | 主要依据 |
| --- | ---: | --- |
| 可访问性 | 2 | 对比度、无名Select、运行行键盘选择 |
| 性能 | 2 | 大初始包；运行性能未测，评分置信度较低 |
| 主题 | 3 | token/双主题完善，静态主题检查通过；登录对比度仍不足 |
| 响应式 | 1 | 代表页无根溢出，但导航丢失、名称零宽、分隔线无效 |
| 实现完整性 | 2 | 错误状态、认证控件和反馈存在可核实偏差 |
| **总分** | **10/20** | **Acceptable，需要显著改进；非合规认证** |

| Nielsen启发式 | 0–4分 | 主要依据 |
| --- | ---: | --- |
| 系统状态可见性 | 3 | 运行阶段清楚；保存/失败空态矛盾 |
| 贴近真实业务 | 3 | 领域术语清楚，生成阻断提示偏离真实步骤 |
| 用户控制与自由 | 1 | 窄屏无导航，精确登录链接丢参数 |
| 一致性与标准 | 3 | 公共组件较好，Tab行为仍有差异 |
| 错误预防 | 2 | 权限/确认已有，保持登录选项无效 |
| 识别而非回忆 | 3 | 文字导航/范围清楚，部分阻断需记忆前序步骤 |
| 灵活与高效 | 2 | 有批量/快捷键，运行行选择不完整 |
| 美观与简约 | 3 | 适合测试工作的层级与主题，不以个人偏好扣分 |
| 错误诊断与恢复 | 2 | 多处有重试，删除/保存/密码恢复反馈不足 |
| 帮助与文档 | 2 | 有快捷键帮助/联系信息，流程帮助零散 |
| **总分** | **24/40** | **Acceptable** |

A的独立首轮评分为25/40；主代理补充窄屏导航证据后，将“用户控制与自由”从2调整为1。B的首轮audit为11/20；补充导航和名称列问题后，响应式从2调整为1。评分只用于本轮优先级沟通，未验证范围不自动按优秀计分。

认知负荷总体中等：业务分组和渐进展开是优点；较宽Bug表、功能生成的错误解除提示、登录后重新定位增加负担。五个需求Tab和既有导航是明确业务对象，不因“超过四项”直接要求重构。

### 三类用户视角

- **新成员 Jordan**：能看到清楚主入口，但功能生成禁用提示未指向可完成的前置步骤，忘记密码没有可行出口。
- **键盘用户 Sam**：测试Tab方向键与弹窗Escape可用；运行行不能单独选中、多个筛选框无名称；浅色小字更难读。
- **熟练执行者 Alex**：批量判定、自动前进和快捷键有价值；名称列消失、保存失败仍“已保存”、深链登录丢目标直接影响效率与信心。

### 应保留的优点

1. 审核、导入和人工检查点分开，需求工作区提示材料快照变化，业务语义明确。
2. 测试/需求Tab已有aria关联、选中态、方向键/Home/End模式；只读动作有可识别禁用原因。
3. 统一主题token、列表表面、分页、权限按钮；check:theme通过，扫描中的引用边线具有真实用途。
4. 测试单搜索无结果提供清空恢复，新建空表单能给出必填提示；需求错误弹窗可用Escape退出。

## 建议处理顺序

先处理前五项，再修复F07–F09认证/跨项目恢复、F10–F15键盘与失败状态；每批补对应行为测试和真实浏览器复核。推荐命令映射：`$impeccable adapt`（导航/列表/对照）→ `$impeccable harden`（保存/认证/权限/错误/键盘）→ `$impeccable colorize`（登录文字token）→ `$impeccable clarify`（生成/恢复指引）→ 按测量结果运行 `$impeccable optimize` → 最后 `$impeccable polish`。修复后重跑audit和本报告涉及的回归路径。

本轮到报告为止，不执行这些修复。

Questions skipped: 用户明确限定本轮只检查并输出报告，不进入修复范围或设计方向选择。
