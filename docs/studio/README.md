# 前端（studio）

React 单页应用，提供项目、迭代、需求、功能/API/UI 测试资产、AI 任务与执行报告的完整工作台。领域术语见 [CONTEXT](CONTEXT.md)，结构与代码规范见 [STRUCTURE](STRUCTURE.md)，界面布局与交互规范见 [UI-GUIDELINES](UI-GUIDELINES.md)。

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
| `features/` | 按业务划分：`auth`、`projects`、`requirements`、`test-cases`、`testing`、`ai-testing`、`api-automation`、`ui-automation`、`base-services`、`profile` |
| `services/api.ts` | 各 feature API 的聚合出口 |
| `shared/` | `api/request.ts` 请求封装、通用组件、图标、主题 store |
| `test/`、`utils/` | 测试辅助与工具函数 |

HTML 入口是 `index.html`，它加载 `/src/main.tsx`，再转发到 `src/app/main.tsx`。顶层路由只有三条：`/login`、`/register`，其余全部交给 `ProtectedRoute` 包裹的 `AppShell`。

任务和执行详情的代码按职责维护：

- 功能用例生成页面负责运行选择与操作编排；`ai-testing/utils/functionalOutput.ts` 负责产物解析，`caseNameTree.ts` 负责树编辑与布局计算，三个结果展示组件分别负责需求分析、候选用例和测试点树。
- 五类 AI 任务详情页的执行后缓存刷新、运行记录删除收敛在 `ai-testing/hooks/useTaskRunActions.ts`。各页保留不同的执行参数、授权查询、审核业务和草稿清理；删除失败不清空草稿，删除非当前记录不切换选中项。UI 与代码风险任务仍只刷新运行列表，其余三类任务同步刷新详情与项目任务列表。
- AI 测试样式按页面和组件职责维护，文件与引用约定见下表。
- API 集合页面的查询、用例编辑、规则编辑和运行轮询分别在 `api-automation/hooks/useApiCollectionData.ts`、`useApiCaseEditing.ts`、`useApiRuleEditing.ts`、`useApiExecution.ts`。组件目录维护用例编辑器、规则弹窗、导入弹窗及运行历史/报告；查询键和缓存失效由对应 hook 管理。
- UI 套件页面保留草稿与执行编排，步骤编辑器、导入弹窗、运行历史和报告位于 `ui-automation/components/`；单用例和套件报告共用步骤结果渲染。
- `shared/utils/` 集中下载、分页文案与值格式化。任务产物使用 `formatStructuredContent` 保留 JSON 字符串表示；一般展示使用 `prettyPrintValue`，两者空值和字符串行为不同。

### AI 测试样式归属

文件统一放在 `src/features/ai-testing/styles/`。页面或组件显式引入自身使用的样式，先引入 `index.css` 公共基础；`index.css` 不聚合导入其它文件。新拆出的组件样式各自不超过 600 行，保留原有选择器、媒体查询及样式取值。

| 文件 | 职责 / 使用入口 |
| --- | --- |
| `index.css` | 公共变量、页面表面、共用面板与编辑器适配 |
| `task-list-v2.css` | 任务列表、模块导航的布局与外观，由列表和概览页引入 |
| `task-detail-v2.css` | 详情骨架、运行记录与代码风险报告，由详情页引入 |
| `task-form.css` | 创建任务抽屉的字段、来源输入、上传与模型连接选择，由各 Drawer / 选择弹窗引入 |
| `task-review.css` | 审核和导入共用容器、备注、预览与冲突对比，由使用它们的详情页及冲突组件引入 |
| `candidate-review.css` | 功能、UI 候选结果审核弹窗，由对应详情页引入 |
| `generated-cases-review.css` | 候选用例分组、筛选、卡片与分页，由 `GeneratedCasesReviewView` 引入 |
| `requirement-analysis.css` | 需求分析章节、规则、流程、场景，由 `RequirementAnalysisView` 及使用其布局的详情页引入 |
| `case-name-tree.css` | 测试点树标签页、节点、连线与编辑状态，由 `CaseNamesResultView` 及使用其布局的详情页引入 |
| `api-config-result.css` | API 配置结果标签页、请求链、变量与规则，由 API 任务详情页引入 |
| `run-result.css` | 运行结果弹窗、Popover 与编辑器高度适配（包括功能阶段审核模式），由使用它们的详情页及结果组件引入 |
| `skill-library.css` | Skill 面板、卡片、空状态与响应式网格，由 `AiSkillLibraryPage` 引入 |

`functional-import-confirm.css` 继续维护原有的功能用例导入确认样式。原有配色与覆盖关系未在本次文件拆分中重设计。

### 公共表格与按钮

- `shared/styles/list-table.css` 是表头和数据行尺寸、底色、悬停背景的共用实现，颜色取自 `surface-tokens.css` 的 `--srf-list-*`。页面保留业务类名并声明 `tp-list-surface`，表格保留业务类名并声明 `tp-list-table`；使用表格的入口显式引入这两个样式文件。列内容、边框及圆角的现有优先级仍由 feature 维护。
- 按钮外观由 `app/styles/buttons.css` 的 `app-buttons` 层统一负责。页面保留尺寸、排布与边框结构，不再重复声明已经被该层覆盖的文字色、背景、阴影和字重。
- 筛选工具栏的尺寸与表面只在 `surface-tokens.css` 的 `.tp-surface .tp-list-toolbar` 定义。旧面板样式显式排除这个类，API / UI / 测试单页面只保留内部排布；已删除旧 UI 横幅、API 环境摘要、快速过滤空栏及 AI 页内导航的失效样式。
- UI 步骤编辑器和测试集抽屉的窄屏规则分别归 `ui-automation/styles/step-editor-layout.css`、`suite-drawer-layout.css`，由对应组件引入；不再借用 API 模块的 `detail.css`。

列表规格由 `app/styles/listSurfaceConsistency.test.ts` 验证，运行操作的缓存与草稿保护由 `ai-testing/hooks/useTaskRunActions.test.tsx` 验证。涉及按钮层优先级的变更需用浏览器核对，jsdom 尚不能模拟 CSS layer 的完整级联。

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
npm run verify        # type-check + lint + build
```

测试配置见 `vite.config.ts`：jsdom 环境，单项超时 30s，`maxWorkers: 4`（最多 4 个测试文件并行）。重型页面测试使用 `src/test/TestThemeProvider.tsx`——保留真实主题与组件，只关闭 jsdom 不执行的 CSS 动画，避免弹窗卡在进入动画的透明状态；并发过高会因 CPU 争用出现超时抖动，排查时用 `--maxWorkers=1` 串行复跑，以区分「超时」与「行为失败」。2026-09-24 全量验证为 62 个文件、396 项，耗时约 2 分钟；数量以后续测试输出为准。历史整改与验证过程见 git 提交 `72164d2`。

**列表页表面层的观感不在自动化覆盖内**（jsdom 不做布局）。UI 测试页重做时用一次性 Playwright 脚本对着 `npm run dev` 核对过：脚本用 `context.route('**/v1/**')` stub 掉 `/v1/user`、`/v1/projects`、`/v1/projects/:id/sprints`、`/v1/sprints/:id/requirements`、`/v1/requirements/:id/ui-test-suites`，然后在 `1680×1000` 下截整页。脚本没有落库——要复查时照这个思路现写即可；当前判据见 [界面规范](UI-GUIDELINES.md)：工具栏与表格卡片边缘对齐、控件不溢出；UI 顶部信息条已移除，不再按旧三卡片结构验收。

同一套脚本也能抓「多出来的容器」：把每个元素的 `backgroundColor` / `boxShadow` / `borderWidth` 采成一张表，**本该无面（无底色 / 无描边 / 无阴影）的元素却有面，就是外壳的玻璃规则压过了页面覆盖**——这类冲突在同权重时只靠样式表顺序决胜（判据与三处已知坑见 [STRUCTURE.md](STRUCTURE.md) 的「列表页表面层」）。

## 与后端的交互

- 开发服务器代理 `/v1` 与 `/__document_preview_proxy`（后者重写去掉前缀）到 `VITE_API_PROXY_TARGET`
- 容器内由 nginx 监听 80 端口并代理同样的两个前缀，`proxy_read_timeout` 与 `proxy_send_timeout` 为 120s，`client_max_body_size` 为 105m
- 容器健康检查访问 `location = /healthz`
- 用户态认证使用 `Authorization` 头携带 JWT；认证存储键 `testpilot_access_token` 为兼容改名前的已登录用户而保留；主题偏好使用 `mtx-theme-preference`（light / dark / system，默认 system）
