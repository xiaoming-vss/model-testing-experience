# 前端（studio）

[UI 用例三阶段原文审核](../control-plane/ui-three-stage-generation.md)

React 单页应用，提供项目、迭代、需求、功能/API/UI/性能测试资产、AI 任务与执行报告的完整工作台。整体设计说明见 [DESIGN](DESIGN.md)，领域术语见 [CONTEXT](CONTEXT.md)，结构与代码规范见 [STRUCTURE](STRUCTURE.md)，界面布局与交互规范见 [UI-GUIDELINES](UI-GUIDELINES.md)。

需求分析第一阶段的来源与事实核对见 [材料对照视图](requirement-material-comparison.md)，第二阶段的模块、流程和规则核对见 [需求理解对照视图](requirement-understanding-comparison.md)。禅道同步的异步提交、轮询与恢复交互见 [集成任务交互](zentao-sync-jobs.md)。

[需求详情测试设计工作区](requirement-design-workspace.md)

性能测试用例、运行记录与基础服务中的性能监控接入见[性能测试](performance-testing.md)。

基础服务中的禅道/GitLab 服务地址默认要求 HTTPS。自部署 HTTP 实例需在服务配置中勾选“允许明文 HTTP”；自签名或内网 CA 的 HTTPS 可勾选“跳过 HTTPS 证书校验”。两项都会在控制面记录 WARNING，不改变凭据加密方式。

完整用例阶段的模块子 Agent 进度及兼容规则见[按模块并发生成完整用例](../ai-worker/module-case-generation.md)；测试点阶段复用该面板，区分分组初稿、全局审查和增量复核，见[测试点生成进度](../ai-worker/traceable-test-points.md#测试点生成进度)。

## 运行时与依赖

- Node 22.23.1（`.nvmrc`），包管理使用 npm（`package-lock.json`），包名 `@mtx/studio`
- React 19、TypeScript 6、Vite 8、React Router 7、Ant Design 6
- 数据与状态：TanStack Query 5、Zustand 5
- 其他：CodeMirror（JSON/YAML 编辑）、recharts（图表）、docx-preview、html-to-image
- 测试：Vitest 4 + jsdom + Testing Library

## 源码结构

`apps/studio/src/`：

| 路径 | 作用 |
| --- | --- |
| `main.tsx` | 唯一作用为 `import '@/app/main'` |
| `app/main.tsx` | 真正的应用装配入口 |
| `app/router/routes.tsx` | 顶层路由 |
| `app/layouts/AppShell.tsx` | 登录后的整体框架，业务页面在内部二次分发 |
| `app/providers/` | Query 与主题 Provider |
| `app/styles/` | 主题与设计断言测试 |
| `features/` | 按业务划分：`auth`、`projects`、`requirements`、`test-cases`、`interface-library`、`testing`、`ai-testing`、`api-automation`、`ui-automation`、`performance`、`base-services`、`profile` |
| `domain/runs/` | API/UI/AI 共用的运行轮询策略与最终报告刷新；仅依赖 shared 和通用库 |
| `services/api.ts` | 各 feature API 的聚合出口 |
| `shared/` | `api/request.ts` 请求封装、通用组件、图标、主题 store |
| `test/`、`utils/` | 测试辅助与工具函数 |

HTML 入口是 `index.html`，它加载 `/src/main.tsx`，再转发到 `src/app/main.tsx`。顶层路由只有三条：`/login`、`/register`，其余全部交给 `ProtectedRoute` 包裹的 `AppShell`。

任务和执行详情的代码按职责维护：

- 功能用例生成页面负责运行选择与操作编排；`ai-testing/utils/functionalOutput.ts` 负责产物解析，`caseNameTree.ts` 负责树编辑与布局计算，三个结果展示组件分别负责需求分析、候选用例和测试点树。
- 五类 AI 任务详情页的执行后缓存刷新、运行记录删除收敛在 `ai-testing/hooks/useTaskRunActions.ts`。各页保留不同的执行参数、授权查询、审核业务和草稿清理；删除失败不清空草稿，删除非当前记录不切换选中项。UI 与代码风险任务仍只刷新运行列表，其余三类任务同步刷新详情与项目任务列表。
- 运行详情按状态刷新，历史与报告减少重复请求，详见 [运行页面刷新策略](run-polling.md)。AI 详情与历史的缓存同步由 `ai-testing/hooks/useTaskRunHistorySync.ts` 维护。
- 代码风险、测试报告和测试单图谱按执行 ID 展示并逐条删除已结束历史，运行中禁用删除；正式测试资产不受影响。AI Worker 队列协议中的 `runId` 是该次派发尝试 ID，页面请求和执行详情使用执行 ID，两者不得在前端混用。
- AI 测试样式按页面和组件职责维护，文件与引用约定见下表。
- API 集合页面的查询、用例编辑、规则编辑和运行轮询分别在 `api-automation/hooks/useApiCollectionData.ts`、`useApiCaseEditing.ts`、`useApiRuleEditing.ts`、`useApiExecution.ts`。组件目录维护用例编辑器、规则弹窗、导入弹窗及运行历史/报告；查询键和缓存失效由对应 hook 管理。
- UI 套件页面保留草稿与执行编排，步骤编辑器、导入弹窗、运行历史和报告位于 `ui-automation/components/`；单用例和套件报告共用步骤结果渲染。
- 性能测试复用同一 EnvironmentDrawer 管理 `kind=perf` 的环境；测试集列表、工作台、EntityCard、串行运行记录和监控接入面板沿用测试工作区与基础服务的公共骨架，详见[性能测试](performance-testing.md)。
- UI 自动化复用 `features/projects/components/EnvironmentDrawer` 管理 `kind=ui` 的环境：列表工具栏、详情顶栏和调试运行都从项目 UI 环境中选择，缺变量时弹窗内联补齐后重新提交。步骤编辑器的「插入变量」弹窗复用 API 自动化的动态值选择交互，列出当前 UI 环境变量、`baseUrl` 和 UI 内置函数；XPath 定位自动插入 `{{名字|xpath}}`。步骤编辑器也可配置后置提取（`saveTo`），执行控制台汇总实际引用与写回。协议见 [UI 环境变量与后置提取](../control-plane/ui-environment-variables.md)。
- `shared/utils/` 集中下载、分页文案与值格式化。任务产物使用 `formatStructuredContent` 保留 JSON 字符串表示；一般展示使用 `prettyPrintValue`，两者空值和字符串行为不同。

### AI 测试样式归属

文件统一放在 `src/features/ai-testing/styles/`。需求详情页根节点挂生成链/画布/产物/阶段可视化的 `.scope`，Skill 库页面与各弹窗根挂任务详情 Module 的 `.scope`；组件不直接引入全局 CSS，页面层 token 保留在 `ai-task-detail.module.css` 的 `.ai-testing-page` 上。

> 2026-11-17 起，新增或改版样式按 [STRUCTURE.md 的 S16](STRUCTURE.md#新代码样式策略2026-11-17) 与 [ADR 0004](adr/0004-tailwind-v4-new-code-styles.md) 执行；存量 CSS 已冻结，后续只允许删除或收缩。

| 文件 | 职责 / 使用入口 |
| --- | --- |
| `ai-task-detail.module.css` | AI 页面 token/表面、CodeMirror 折叠、任务卡与运行表、需求生成工作区、UI 生成与模型连接弹窗 |
| `generation-chain.module.css` | 生成链弹窗、版本标题、审核页脚、继续优化侧栏与关系图谱/查看器 |
| `generation-canvas.module.css` | 生成画布、阶段卡片、阅读态与阶段检查器 |
| `artifact-cases.module.css` | 用例名称树、用例浏览器、生成用例审核字段与仓库画像 |
| `ui-stage-visual.module.css` | UI 三阶段可视化的深色覆盖、CodeMirror 兜底与产物模式切换；浅色布局/排版在 `components/uiStageVisual/uiStageVisualClasses.ts` |

需求评审、测试点、测试范围分析和材料整理使用 `shared/components/ArtifactView` + Tailwind；公共原语的复杂皮肤只在 `shared/styles/run-view.module.css`，与滚动容器耦合的宿主适配在 `features/ai-testing/styles/` 下的 `*.module.css`；页面不新增同构布局 CSS。

### 测试单样式归属

文件统一放在 `src/features/test-orders/styles/`。`features/test-orders` 下没有非 Module CSS。工作台页面根挂 `test-order-workspace` 的 `.root`，图谱执行面板与加入用例 Modal 复用同一作用域；可视化面板、步骤条、关系图与批量按钮使用 `components/visualization/visualizationClasses.ts` 的 utility 与容器查询变体。旧类名保留为 `:global()` 测试与兼容钩子；剩余一个 Module 只保留高度链、AntD 深层结构与执行条。

| 文件 | 职责 / 使用入口 |
| --- | --- |
| `test-order-workspace.module.css` | 工作台页面高度链、AntD 表格/工具栏深层结构、详情翻页、加入用例弹窗与底部执行条/判定控件；列表、骨架、图谱壳、判定区与可视化布局由组件 utility 负责 |

### 测试用例样式归属

- `case-library.module.css` 承载用例库侧栏渐变、选中态、等宽徽标与优先级色块皮肤；两栏骨架、导航与筛选布局由 `CaseLibraryPage` utility 负责。用例编辑弹窗与导入禅道弹窗共用同一个 `.root`。
- `features/test-cases` 下没有非 Module CSS。

### 需求详情、个人设置与基础服务样式归属

- 需求详情页的页面高度链、面包屑、主/侧栏骨架与窄屏堆叠由 `RequirementDetailPage` / `RequirementDetailHeader` 的 utility 负责；`requirements/styles/requirement-detail.module.css` 只保留链接表面、侧栏动画、画布与文档容器深层结构，根节点挂 `.root`。
- 登录页、个人设置页与独立修改密码页共用 `shared/styles/account.module.css`，该 Module 只保留登录页渐变/纹理/玻璃壳、个人设置根背景/头像与 AntD 深层结构；布局、间距和排版由三页的 Tailwind utility 负责。跨 feature 的共享已收敛到 `shared/`，不再需要 `ChangePasswordPage` 对 feature Module 的跨 feature 导入豁免。
- 禅道 MCP 卡片不再有独立 Module；标题、状态、实例省略与间距均由 `ZentaoMcpServiceCard.tsx` 的 utility 表达。
- `antd/dist/reset.css` 在 `src/index.css` 中以 `layer(reset)` 导入，位于 `@layer antd` 之后、`utilities` 之前；既保留 reset 对组件库默认字重的旧优先级，也让新页面的 utility 能覆盖 reset。`src/index.css` 不再重复声明控件 `font-family`，避免未分层规则压过 `font-mono`。
- `src/features` 下没有非 Module CSS；非 Module CSS 只剩 `app/styles`、`shared/styles`、`shared/components/RichTextEditor` 与入口 `index.css`。
- TestingPage 的标签外壳与 pane 布局、项目设置抽屉的 body padding 与设置行布局均由组件 utility 负责。
- 共享 `tp-list-toolbar` 的搜索框宽度已迁到页面 `w-72` utility；工具栏表面、最小高度与 `.api-filter-field`/`.api-filter-group`/`.api-filter-field-label` 原语位于 `@layer components`，utility 可在页面按需覆盖。UI 列表搜索框用 `min-w-64 max-narrow:w-full max-narrow:min-w-0` 表达原 256px 下限。

### 公共表格与按钮

- `shared/styles/list-table.css` 是表头和数据行尺寸、底色、悬停背景的共用实现，颜色取自 `surface-tokens.css` 的 `--srf-list-*`。页面保留业务类名并声明 `tp-list-surface`，表格保留业务类名并声明 `tp-list-table`；使用表格的入口显式引入这两个样式文件。列内容、边框及圆角的现有优先级仍由 feature 维护。
- 按钮外观由 `app/styles/buttons.css` 的 `app-buttons` 层统一负责。`app-buttons` 已加入 `tailwind.css` 的层顺序（位于 `components` 与 `utilities` 之间）；页面保留尺寸、排布与边框结构，不再重复声明已经被该层覆盖的文字色、背景、阴影和字重。
- 筛选工具栏的尺寸与表面只在 `surface-tokens.css` 的 `.tp-surface .tp-list-toolbar` 定义，并放在 `@layer components`。旧面板样式显式排除这个类，API / UI / 测试单页面只保留内部排布。
- 全局层样式入口是 `app/styles/theme.css`，按顺序导入 `layout.css`、`shell.css`、`shell-header.css`、`antd-overrides.css`、`action-buttons.css`、`theme.css`；结构门禁会拦截 `src/App.css` 重新出现。
- 接口库列表、软件仓库树与共用的方法签在 `interface-library.module.css`；详情、编辑器深层 AntD 规则与 OpenAPI 导入标签间距在 `interface-detail.module.css`。页面根与 Modal/Drawer 根挂两个 `.scope`；布局、树节点、仓库表格、编辑器面板、导入步骤与结果由组件 utility 负责。
- UI 测试集详情的顶栏、板面、React Flow 深层皮肤归 `ui-detail-shell.module.css`，右栏卡片原语归 `shared/components/RunCard.tsx`，步骤编辑器与测试集抽屉的 Ant Design 深层结构归 `ui-suite.module.css`；页面根挂 `ui-detail-shell` 与 `ui-suite` 两个 Module 的作用域。
- Sprint 详情页与 Projects 概览共用 `sprint-overview.module.css`，只保留卡片/健康带表面、图表色块、状态色映射与报告 Markdown 在 `sprint-overview.module.css`；页面网格、工具栏、指标与断点由 `SprintDetailPage` / `ProjectsPage` utility 负责，报告 Modal/Drawer 通过 `rootClassName` 或 `className` 挂作用域。需求/迭代卡片排版由 `ProjectsPage`、`RequirementCards`、`SprintBoard` utility 负责。

列表规格由 `app/styles/listSurfaceConsistency.test.ts` 验证，运行操作的缓存与草稿保护由 `ai-testing/hooks/useTaskRunActions.test.tsx` 验证。涉及按钮层优先级的变更需用浏览器核对；jsdom 不能模拟 CSS layer 的完整级联，`listPanelConsistency` / `listSurfaceConsistency` 在注入共享 CSS 前用 `src/test/unwrapCssLayer.ts` 解包 `components` layer。

### 共享数据工具

- `shared/utils/value.ts` 的 `toRecord` / `toRecordArray` 统一处理候选结果和图谱数据的对象边界：排除 null、数组和基本类型；数组解析保留有效对象及原顺序。
- JSON 编辑器、API 运行结果、HTML 报告和测试点树图片下载复用 `shared/utils/download.ts` 的 `saveBlob`，各入口只负责内容、文件名及成功提示。

## 配置

无 TOML 配置，`scripts/manage.py` 不为前端生成 TOML。涉及两层变量：

- 构建期（Vite）：`VITE_API_PROXY_TARGET` 指定开发服务器代理目标，本地模式由 `manage.py configure --mode local` 写入 `.env.local`；`VITE_API_BASE_URL` 指定后端基地址，默认空（同源）。
- 运行期（容器）：`API_UPSTREAM` 由 nginx 模板用于 `proxy_pass`，Compose 中设为 `http://control-plane:9000`。

## 命令

在 `apps/studio/` 下执行：

```sh
npm ci                # 安装依赖
npm run dev           # 开发服务器，默认 127.0.0.1:5173
npm run type-check    # tsc -b --pretty false
npm run lint          # eslint .
npm run test          # vitest run
npm run build         # tsc -b && vite build
npm run check:theme   # 登记色源与任意色值检查
npm run check:css     # !important / 长前缀 / 未定义变量预算
npm run check:css:structure  # CSS 文件、导入、规则体与重复体结构门禁
npm run check:boundaries  # feature 跨模块 import 基线检查
npm run verify        # type-check + lint + check:theme + check:css + check:css:structure + check:boundaries + build
```

`npm run verify` 不包含 `npm test`；迁移和发布前仍需单独执行全量测试。

测试配置见 `vite.config.ts`：jsdom 环境，单项超时 30s，`maxWorkers: 4`（最多 4 个测试文件并行）。重型页面测试使用 `src/test/TestThemeProvider.tsx`——保留真实主题与组件，只关闭 jsdom 不执行的 CSS 动画，避免弹窗卡在进入动画的透明状态；并发过高会因 CPU 争用出现超时抖动，排查时用 `--maxWorkers=1` 串行复跑，以区分「超时」与「行为失败」。测试数量以后续输出为准。

**列表页表面层的观感不在自动化覆盖内**（jsdom 不做布局）。需要核对时，用一次性 Playwright 脚本对 `npm run dev` 截图，并用 `context.route('**/v1/**')` stub 掉业务请求；也可采集元素的 `backgroundColor` / `boxShadow` / `borderWidth`，本该无面的元素却有面，通常是外壳玻璃规则压过了页面覆盖。当前判据见 [界面规范](UI-GUIDELINES.md)：工具栏与表格卡片边缘对齐、控件不溢出。

## 与后端的交互

迭代入口只读取迭代列表；需求入口通过项目级需求列表按当前迭代筛选、后端分页，选择“全部迭代”时省略 `sprintId`。列表的禅道绑定摘要直接使用响应中的 `zentaoBinding`，不按卡片或表格行逐条请求 `/bindings`。单条绑定在打开管理弹窗时查询；创建、重新绑定或解绑后使对应项目的迭代列表或需求分页缓存失效。

- 开发服务器代理 `/v1` 与 `/__document_preview_proxy`（后者重写去掉前缀）到 `VITE_API_PROXY_TARGET`
- 容器内由 nginx 监听 80 端口并代理同样的两个前缀，`proxy_read_timeout` 与 `proxy_send_timeout` 为 120s，`client_max_body_size` 为 105m
- 容器健康检查访问 `location = /healthz`
- 用户态认证使用 `Authorization` 头携带 JWT；认证存储键 `testpilot_access_token` 为兼容改名前的已登录用户而保留；主题偏好使用 `mtx-theme-preference`（light / dark / system，默认 system）

- [内置 MCP 配置](builtin-mcp.md)
- [Bug 手动推送到禅道](../control-plane/bug-zentao-push.md)
- [Bug 管理需求核对与页面整理](bug-management-review.md)

- [文件直传与预览](file-storage.md)

- [Skill 文件夹与默认技能维护](../control-plane/skills.md)

需求在线图文编辑见[需求富文本编辑](requirement-rich-text.md)。

### 功能用例推送核对

用例库的禅道弹窗由 `features/test-cases/components/CasePushModal.tsx` 维护：先预览，
再逐条选择新建或绑定。同一提交失败重试复用原编号和参数，刷新后重新读取持久化未决记录。
核对表单在同一个弹窗内展开；确认未写入仅对服务端确认的当前项目所有者开放，并要求理由和
显式勾选。数据库恢复后的额外核对由后端按用例状态声明。接口和审计规则见
[功能用例推送与未决写入核对](../control-plane/zentao-mcp-case-push.md)。
- 编辑 API 测试集时可调整同一项目内的所属迭代和需求；保存会刷新原需求和目标需求的生成链导入目标。运行历史显示的需求和迭代跟随测试集当前归属。

API/UI 运行的实时更新、断线及临时调试结果见 [实时执行](../control-plane/realtime-test-execution.md)。

功能测试点阶段展示可追溯测试点、关联材料、覆盖缺口及独立审查状态；可切换树图，手工编辑名称后审查状态重置为自审。契约见 [AI Worker 文档](../ai-worker/traceable-test-points.md)。

- [单用例图解界面与验证](case-visualization.md)。
