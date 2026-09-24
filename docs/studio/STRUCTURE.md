# 前端结构与代码规范（studio）

本文描述 MTX 前端（`apps/studio`）的**代码组织与结构规范**：分层与依赖方向、feature 边界、样式归属、目录契约，以及代码体积与去重要求。目的是让「位置放错」和「重复膨胀」这两类问题不再复现。

- 领域术语与业务概念 → [CONTEXT.md](CONTEXT.md)
- 界面布局与交互规范 → [UI-GUIDELINES.md](UI-GUIDELINES.md)
- 运行时、源码结构、启动与构建 → [README.md](README.md)
- 架构决策 → `docs/studio/adr/`

## 如何阅读

本文覆盖**代码组织与结构**。界面尺寸、导航、筛选与操作位置统一维护在 [UI-GUIDELINES.md](UI-GUIDELINES.md)。共享样式是实现来源，样式测试约束部分计算值；真实布局与尚未自动化的规格必须按界面规范人工验证。

每条规则标注强制状态：

| 标记 | 含义 |
| --- | --- |
| **待强制** | 规则已定，自动检查**尚未实现**；当前只能靠评审 |
| **存量豁免** | 规则只对**新**代码生效；既有违规记入基线不修，只许减不许增 |

> **当前状态：S8 的 CSS 裸色值检查已接入 `npm run verify`，其余自动检查仍待实现。** 仓库没有 CI，也没有 git hook，`npm run verify` 与 `npm test` 依赖人工执行。CSS 配色可通过 `npm run check:theme` 单独检查；其它规则的自动化见各条「检查」列。

每条规则都从实际违规反推得到，附「拦住的问题」与文件行号，便于核对。行号为 2026-09-22 审计时刻的值，会随改造漂移。

---

## 元规则

**规范必须和检查一一对应。只写在文档里的规范等于没有规范。**

这条元规则是这个仓库最需要记住的一条。现状可作反证：根 `AGENTS.md` 已交代「为改动运行对应子项目的检查」，`README.md` 也列出了 `verify` 与 `test` 命令，过去还逐条记录过已知债务——但债务仍然长回来了。原因是**规范和检查之间没有连接**：文档是给人读的，而人是会忘记的。

因此本文每条规则的「检查」列不是可选项。缺了那一列，这条规则就只是建议。

---

## 一、分层与依赖方向

前端分三层，依赖**只能向下**：

```
app/          应用装配：路由、布局外壳、provider、全局样式
  ↓
features/     业务功能：每个 feature 一个目录，自治
  ↓
shared/       通用能力：无业务语义的工具、组件、请求封装、主题 store
```

`src/utils/` 与 `src/services/` 视为 shared 层同级（`services/api.ts` 是各 feature api 的聚合出口，`utils/` 是跨 feature 的适配层）。

| # | 规则 | 拦住的问题 | 检查 |
| --- | --- | --- | --- |
| S1 | `shared/`、`src/utils/`、`src/services/` **不得** import `features/`。需要 feature 提供的东西时，改为参数注入或把实现下沉 | `shared/api/request.ts:1` import `features/auth/store/auth.store`；`src/utils/updatePayload.ts:17-19` import 3 个 feature 的表单类型 | ESLint `no-restricted-imports`（**待强制**） |
| S2 | `app/` 可以 import `features/` 与 `shared/`；`features/` 之间只允许经 `api/` 与 `types.ts` 通信 | 见第二节 S3 | ESLint（**待强制**） |

## 二、feature 边界

| # | 规则 | 拦住的问题 | 检查 |
| --- | --- | --- | --- |
| S3 | feature 之间**只允许** import 对方的 `api/` 与 `types.ts`。`components/`、`hooks/`、`utils/`、`styles/`、`config/`、`store/` 都是内部实现，不得跨 feature 引用 | `test-orders/components/TestOrderGraphViewer.tsx:7,8,14,18,24` 引用了 ai-testing 的图谱组件、hook、两个 utils，还 import 了它的 CSS；`test-orders/types.ts:1` 借用 ai-testing 类型 | ESLint（**待强制**）；按 feature 生成规则块，各自忽略自身目录 |
| S4 | **归属判定（一句话）：被 2 个以上 feature 使用的代码必须上提。** 无业务语义 → `shared/`；有业务语义 → 提到 `app/` 或独立领域模块 | 用例关系图谱 `ai-testing/utils/caseRelationsGraph.ts`（483 行）被 test-orders 引用却留在 ai-testing；`projects` 被 3 个 feature 依赖（api-automation 16 处、ui-automation 13 处、base-services 10 处），是事实上的平台层却从未上提 | 评审 + 定期依赖图核对（**待强制**） |
| S5 | `shared/` 准入两条：**无业务语义** + **全站唯一实现**。「全站唯一实现」必须列成显式清单，新增条目需评审 | 文件下载已统一到 `shared/utils/download.ts` 的 `saveBlob`；对象解析已统一到 `shared/utils/value.ts` 的 `toRecord` / `toRecordArray` | 清单见本节末（**待强制**） |

`shared/` 的「全站唯一实现」清单（新增需评审）：

- CodeMirror 封装 —— `shared/components/TextCodeEditor`、`shared/components/JsonEditor`、`shared/components/codeEditorTheme.ts`。全项目 `@uiw/react-codemirror` / `@codemirror/*` 的 import 只允许出现在这里
- 请求封装 —— `shared/api/request.ts`
- 文件下载 —— `shared/utils/download.ts`
- 值格式化与载荷构造 —— `shared/utils/value.ts`、`shared/utils/payload.ts`
- 操作按钮与权限门控 —— `shared/components/ActionButton`

## 三、样式归属与主题

| # | 规则 | 拦住的问题 | 检查 |
| --- | --- | --- | --- |
| S6 | CSS 位置唯一：`features/<f>/styles/`。**禁止**在 `components/`、`pages/` 下放 CSS；全局层只允许 `app/styles/`、`shared/styles/` | 审计时 25 个 CSS 散在 6 类位置：`src/` 根 2、`app/styles/` 6、`shared/styles/` 1、`features/*/styles/` 10、`features/*/components/` 3、`features/*/pages/` 3。其中 6 个放错位置：`ai-testing/components/` 下的 `RevisionSidePanel.css`、`FunctionalCaseRelationsViewer.css`、`FunctionalCaseRelationsGraph.css`，以及 `ai-testing/pages/RequirementAnalysisTaskDetailPage.css`、`projects/pages/SprintDetailPage.css`、`profile/pages/ProfilePage.css`；`profile`、`projects`、`requirements` 连 `styles/` 目录都没有 | 扫描脚本路径检查（**存量豁免**：上述 6 个文件） |
| S7 | 样式归属：feature 只写自家前缀。**全局层（`app/styles/`、`shared/styles/`）不得出现 feature 内部类名** | `app/styles/workbench.css` 引用 87 个 feature 内部类名、`layout.css` 12 个；`features/api-automation/styles/detail.css` 有 30 处 `.ui-*`（API 自动化给 UI 自动化写样式） | 扫描脚本前缀统计（**存量豁免**） |
| S8 | token 单一来源：token 定义集中在**已登记的 token 文件**里（清单见下）。feature **只能消费，不得定义全局 token** | `--tp-text` 被 `app/styles/workbench.css` 与 `features/api-automation/styles/detail.css` 两处定义；`shared/styles/page-frame.css` 消费了 8 处 token（`:64,118,272,349,547,961,979,1072`，其中 `--tp-border`×3、`--tp-border-soft`×5），而这两个 token 的定义同样散在 `workbench.css` 与 `detail.css` 两处——**shared 反向依赖 feature 定义的 token** | CSS 裸色值：`npm run check:theme`（**已实现**，接入 `verify`）；定义重名与依赖方向扫描仍待实现，存量定义保留 |
| S9 | 样式引入必须显式自持：每个入口自行 import 自己依赖的样式。**禁止依赖「别的页面恰好 import 了」而生效** | `functional-test-page` 被 4 个 feature 使用（test-cases、api-automation、test-orders、ui-automation 的页面），但唯一定义在 `features/testing/styles/index.css`，而这 4 个页面都不 import 它——只靠被 `TestingPage` 包着渲染才拿到样式 | 评审 + import 图核对（**待强制**） |
| S14 | 列表页表面层：用例库 / 测试单 / API 测试 / UI 测试四页共用 `shared/styles/surface-tokens.css`。页面根节点必须同时带页面类与 `tp-surface`，板面 section 带 `tp-board`；样式写在各自 `features/<f>/styles/*-v2.css`，颜色只能引用 `--srf-*` / `.tone-*` | 四页共用同一套卡片 + 胶囊 + 色盘，缺 `tp-surface` 时页面里所有 `var(--srf-*)` 解析成空值，表现为「样式莫名消失」；`testing/styles/index.css` 与 `app/styles/workbench.css` 都用 `!important` 抢过这些容器，覆盖规则必须写成 `.app-shell.app-shell-macos .testing-page .<页面类> ...` 再加 `!important`，删掉前缀或 `!important` 会静默失效。**同权重同样会失效**：`workbench.css` 的玻璃规则是 (0,6,0)，与 `.tp-board` 覆盖同分，只靠 import 顺序决胜 | 评审 + 扫描脚本（**待强制**） |

已登记的 token 文件（新增或改名需评审）：

| 文件 | 前缀 | 用途 |
| --- | --- | --- |
| `src/index.css` 的 `:root` 块 | `--app-*`、`--description-*` | 全局基础（背景、正文、链接、描述字体白名单） |
| `src/shared/styles/foundation-tokens.css` | `--app-*`（与 `index.css` 不重名） | 外壳、公共页面框架、旧工作台及 AI/API 工作流语义配色，由 `index.css` 在启动时引入 |
| `src/shared/styles/legacy-tokens.css` | `--legacy-*` | 旧工作台作用域 token 的浅色来源，局部变量保持原作用域 |
| `src/shared/styles/github-dark-tokens.css`、`github-dark-foundation.css` | `--gh-*` 及上述语义 token | GitHub Dark 色盘与暗色赋值，只定义变量，不覆盖业务组件规则 |
| `src/shared/styles/editor-tokens.css` | `--editor-*` | CodeMirror 的表面、选区、光标及 JSON/YAML 语法高亮，由 `index.css` 引入 |
| `src/shared/styles/chart-tokens.css` | `--chart-*`、`--graph-*` | 图表序列、坐标轴、提示框、关系图连线/缩略图及树图导出配色，由 `index.css` 引入 |
| `src/app/styles/workbench.css` 的 `:root` 块 | `--tp-*`、`--mac-*` | 工作台基础与 macOS 外壳 |
| `src/app/styles/buttons.css` | `--button-*` | 按钮调色板（全站唯一按钮皮肤） |
| `src/shared/styles/surface-tokens.css` | `--srf-*` | 列表页共用的表面与色盘 |

**裸色值（`#rrggbb`）只允许出现在上表已登记的 token 文件里。** 其它任何 CSS 文件出现裸色值都应当改为引用 token。注意此规则必须带 token 文件白名单，否则会把合法的 token 定义本身判为违规（例如 `surface-tokens.css` 中的颜色定义）。

基础层颜色整理：`layout.css`、`page-frame.css` 与 `workbench.css` 的普通声明消费 `foundation-tokens.css`；后者已有的 `--tp-*` / `--mac-*` 等定义保持原作用域。浅色取值、渐变位置、阴影几何和选择器权重保持不变。玻璃层 token 的数值后缀标识原有透明层，后续主题可以分别赋值，不应把它们当成全站透明度工具。终端背景与正文、强调色上的文字与卡片底色分开定义。新列表/详情页继续使用 `--srf-*`，不要迁回旧工作台配色。Ant Design 的算法输入和组件 token 仍集中在 `app/providers/ThemeProvider.tsx`，切换主题时需单独配置，不能把需要参与颜色运算的 seed token 直接替换为 CSS `var()`。

AI 的 `index.css`、`task-list-v2.css`、`task-detail-v2.css` 与 API 的 `detail.css` 同样从基础色盘取值。现有 `--ai-*`、`--detail-glass-*`、`--run-pipeline-*` 保留局部作用域，作为全局语义颜色的组合或别名；`--srf-*` 的消费优先级不变，原有备用颜色改为嵌套的基础 token 引用，以保留未挂载 `tp-surface` 时的渲染行为。终端滚动条、流水线状态、HTTP 方法颜色独立命名；暗色通过集中 token 赋值接入。

其余页面 CSS（基础服务、测试、登录、个人设置及 AI 审核等）也只消费颜色变量；局部变量继续保持原来的选择器和作用域。四个新版列表的阴影颜色通过 `--srf-shadow-color` 引用基础色盘。`scripts/check-theme-colors.mjs` 扫描所有源码 CSS 的声明，禁止在登记文件的自定义属性以外新增十六进制、颜色函数或具名颜色，包括 `var()` 的裸色备用值；忽略注释、字符串和变量名，允许 `transparent` / `currentColor`。CSS 检查不验证语义去重、变量可达性或浏览器视觉效果。

TS/TSX 的配色检查同样接入 `check:theme`：通过 TypeScript AST 扫描生产代码的字符串及模板片段，禁止未登记的十六进制和颜色函数，排除测试/测试夹具、注释和正则表达式；Ant Design 的 `gold`、`success` 等语义参数保留。固定颜色入口只有 `ThemeProvider.tsx`（组件库算法配置）、`collectionRunReport.ts`（独立 HTML 报告）和 `MtxLogo.tsx`（品牌 SVG）。编辑器、Recharts 与 React Flow 的 CSS/SVG 属性消费变量；CodeMirror 的 dark 扩展与 React Flow 的 colorMode 跟随主题 store 的 resolvedTheme，编辑器切换扩展时保留内容。树图导出在调用 `toBlob` 前从原节点读取具体的背景/边框 token 值，避免把未解析变量传给脱离页面的克隆节点。

**主题支持浅色、深色和跟随系统**（[ADR 0002](adr/0002-token-based-github-dark.md) 取代 ADR 0001 的仅浅色决定）。默认跟随系统；登录页和页头提供同一切换器，偏好保存到 `mtx-theme-preference`。HTML 启动脚本在首屏绘制前设置 `data-theme` 和 `color-scheme`；store 处理系统变化及跨标签页同步。暗色参考 GitHub Primer Dark，颜色变化集中在登记的 token 文件和 Ant Design 配置。新增业务样式消费语义 token，并核对两种主题，不得恢复按 feature 类名堆叠的暗色补丁层。独立 HTML 报告与品牌图形保留自身配色。

### 列表页表面层（用例库 / 测试单 / API 测试 / UI 测试）

这四页按各自的外部设计稿（Stitch 导出的静态 HTML，配套一份含色板 / 字阶 / 组件规格的 `DESIGN.md`）重做了表面层，
视觉语言是同一套：白色卡片 + 描边 + 胶囊筛选条 + 代码体编号 / 时间 + 色调色块。设计稿的取值与本仓库既有约定一致
（卡片 `#ffffff`、描边 `#e2e8f0`、主色 `#2563eb`、编号与时间用等宽、4px 网格），没有引入新的取值体系。

| 页面 | 页面样式文件 |
| --- | --- |
| 用例库 | `features/test-cases/styles/case-library-v2.css` |
| 测试单 | `features/test-orders/styles/test-orders-v2.css` |
| API 测试 | `features/api-automation/styles/list-v2.css` |
| UI 测试 | `features/ui-automation/styles/list-v2.css` |

`shared/styles/surface-tokens.css` 除 token 与九色盘外，还承载板面（`.tp-board`）与快速过滤条组件（`.tp-quickbar`、
`.tp-chip`、`.tp-selection`）——四页的这几个部件必须完全一致，所以放在共用层而不是各写一份。

设计稿与既有约定冲突时以既有约定为准：设计稿的表格规格是表头 32px / 行高 36–40px，与 §7.5 锁定的列表指纹冲突，
四页的表头与行高仍是 42 / 48px。设计稿把测试集名称画成蓝色链接，这一条也不行——`app/styles/listNameConsistency.test.ts`
断言「API 测试集 / UI 测试集 / 功能测试集 / 需求」的名称样式与 AI 任务名称逐项相等，改一页就会红。
设计稿中的旧布局以 [UI-GUIDELINES.md](UI-GUIDELINES.md) 为准：四页工具栏统一白色卡片；导航已移到侧栏，API 测试与测试单已去掉快速过滤整行。

**「多出来的容器」都出在同一处：覆盖了外壳玻璃面，但权重没压过它。** 三处踩过的坑，改这一层时逐条对：

- 板面 `.tp-board`：`workbench.css` 的玻璃规则写成
  `.app-shell.app-shell-macos :is(<页面类…>) :is(<面板类…>)`，两个 `:is()` 各 1 分，
  合计 **(0,6,0)**——与 `shared/styles/surface-tokens.css` 里那条 `.tp-board` 覆盖（(0,2,0)）相比权重更高，
  顺序一变板面就会重新拿到玻璃底 + 内高光 + 28px 阴影，表现为内容区凭空多出一层容器。
  修法是多带 `.app-shell-macos .testing-page` 前缀抬到 (0,7,0)，不再依赖 import 顺序。
- 工具栏由共享 `.tp-list-toolbar` 负责白底、描边与尺寸；旧 `.panel-header` / `.api-panel-header` 的容器规则通过 `:not(:where(.tp-list-toolbar))` 排除它。页面只补排布，不再复制尺寸与表面，公共工具栏规则不再需要 `!important`。
- 筛选标签 `.api-filter-field-label`：旧外壳给它铺了蓝底小胶囊，设计稿里是裸的弱化文字。
  在 `surface-tokens.css` 里按 `.tp-surface` 收掉，不动那条旧规则——它同时作用于测试单的「加入用例」弹窗，
  那个弹窗不在 `tp-surface` 里，不该跟着变。

判据可以量化：外层板面不增加底色 / 描边 / 阴影；筛选工具栏应有白底与描边、无额外阴影。DevTools 禁用对应规则
再回读 `getComputedStyle` 即可确认是哪一条赢的。

### 列表规则保留等权重前缀

原先的 `:root:not([data-theme='dark'])` 已改为 `:root:root`，使列表名称、表头和行样式同时适用于两种主题。两个写法的选择器权重相同；不能直接删掉前缀，否则会被其它 `!important` 规则反超。相关浅色行为由 `listSurfaceConsistency.test.ts` / `listNameConsistency.test.ts` 保护。

顺带记两处**浅色下早已存在**的名称样式分歧，此前被深色规则（统一写了 `line-height: 22px`）掩盖，
深色退役后由 `listNameConsistency.test.ts` 的注释记录、未纳入断言：AI 任务列表名称行高 22px，其余三页 20px
（`ai-testing/styles/index.css` 里同一选择器有 20px 与 22px 两条规则，后者胜出）；名称颜色在 jsdom 下不稳定
（两条 `!important` 规则相争时 jsdom 按出现顺序而非优先级裁决，浏览器按优先级，四页都是 `#3f6fc6`）。

**设计稿里没有对应数据或动作的元素一律不做**，避免为了像设计稿而编造字段：

| 设计稿元素 | 原因 |
| --- | --- |
| 没有数据来源的数量徽标 | 不编造计数；测试设计侧栏已有真实项目／迭代任务统计 |
| 用例库：执行状态列、「近期失败 / 待完善」筛选、「AI 智能生成用例」入口 | 用例没有执行态字段、没有对应数据、未接入路由 |
| 用例库 / 测试单：行内「执行」「查看测试报告」 | 功能用例没有执行动作；测试单三种状态都进同一个执行工作台，收成一个入口 |
| 测试单：勾选列、批量删除、导入导出按钮、名称后的类型徽标、分页 | 没有批量删除 / 导入导出接口，测试单没有类型字段，接口不分页 |
| API 测试：勾选列与批量删除、包含接口数、REST 徽标、「自动化冒烟 / 核心链路」筛选、环境就绪胶囊、「网关引擎运行正常」 | 没有批量删除接口；列表接口不返回用例数；测试集没有协议与分类字段；环境与引擎没有健康检查接口 |
| UI 测试：勾选列与批量删除、导出测试配置、集群健康胶囊、并发执行节点 | 没有批量删除与导出接口；节点没有健康 / 列表接口。列表顶部介绍信息条已移除；真实运行配置保留在行内徽标及配置入口 |

各页的测试依赖这些钩子，改动页面结构时要一并保留：`CaseLibraryPage.test.tsx` 用 `.api-case-sidebar`、
`.case-library-sidebar-foot`、`.case-library-main-actions`、「批量删除（N）」；`TestOrderPage.test.tsx` 用进度条的
`role="img"` 无障碍名；`ApiAutomationPage.test.tsx` 用 `.api-test-time-cell`、
`.api-test-table-card`、`aria-label="运行API测试集"`；`UiAutomationPage.test.tsx` 用 `.ui-suite-list-time-cell`、`.ui-suite-list-table-card`、「搜索UI测试集名称 / 描述」、「清空搜索」、
`aria-label="刷新测试集列表"`。

UI 测试页在 `page`/`components` 之间还多了一刀：筛选工具栏（`UiSuiteListToolbar`）、
运行配置徽标（`UiSuiteRunConfigCell`）、三个单元格（`UiSuiteListCells.tsx`）各自成组件，页面只做编排与作用域解析；
搜索词由页面持有（工具栏在页面上），实际过滤在 `UiTestSuiteSection`（它持有 suites 查询），刷新按钮的加载态由
section 经 `onRefreshingChange` 回传。`features/ui-automation/styles/index.css` 只留进入测试集详情后的编辑区与抽屉，
列表部分的规则随重做删除（1019 → 933 行，其中 `.ui-test-suite-card` 一族已无任何使用者，连带从
`workbench.css` 的 `:is()` 列表里摘掉；详情页重做时又摘掉一层旧结构规则，见下面「UI 测试集详情页」）。

### 编辑用例弹窗（`case-editor-v2.css`）

用例库点开用例的那套表单按同一份设计稿重做，样式集中在 `features/test-cases/styles/case-editor-v2.css`。
旧的一套 `.functional-case-*` 编辑器规则已从 `features/test-cases/styles/index.css` 删除（该文件 807 → 377 行），
没有留下死规则。

- **弹窗根节点必须带 `tp-surface`**：antd 把 Modal 传到 body 下，它不在 `.app-shell` 里，
  `workbench.css` 那些带 `.app-shell` 前缀的规则够不到它；弹窗的颜色完全靠 `.tp-surface` 挂上的 `--srf-*` token，
  去掉 `tp-surface` 会让弹窗的 token 解析成空值、样式整体失效。
- 结构：弹窗头部（图标 + 标题 + `TC-####` 序号徽标 + `UID:` + 副标题）、用例名称行（标签 + 创建/更新时间 + 输入框）、
  优先级 / 用例类型两张卡片、前置条件、操作步骤 / 预期结果两张着色卡片、底部左侧「删除用例」+ 右侧「取消 / 保存变更」。
- 区块头的色调竖条与着色头带由元素上的 `tone-*` 类提供 `--srf-tone-*`，不要在文件里写死颜色。
- **设计稿里的逐步骤序号圆圈与逐条 ✓ 是渲染态，这里没有实现**：正文仍是「每行一个步骤 / 一行对应一条预期」的两个文本域，
  因为 `FunctionCaseContentEditor.test.tsx` 断言了恰好 3 个 textbox，并明确禁止出现「添加步骤 / 上移 / 下移 / 删除步骤」按钮。
  要改成逐行编辑器，等于重做数据录入方式（并要改这条测试），属于独立的一件事。
- 该测试同时锁定了三个文本域的 `aria-label`（前置条件 / 操作步骤 / 预期结果）与配对行为，改表单时不要动。
  `CaseLibraryPage.test.tsx` 依赖的保存按钮文案是「保存变更」（不是「保存」）。

### API 测试集详情页（`detail-workbench-v2.css` / `detail-inspector-v2.css` / `detail-request-panels-v2.css`）

API 测试列表点测试集名称进来的页面按设计稿重做：顶栏（返回 / 测试集名 + 需求 + 迭代 / 当前环境 / 运行记录 /
运行测试集）+ 两栏（左栏用例列表卡片、右栏请求编辑与运行结果卡片）。样式按职责拆三个文件，都由
`ApiCollectionDetailPage` 引入，选择器互不重叠：`detail-workbench-v2.css` 是板面、顶栏与左栏（361 行），
`detail-inspector-v2.css` 是右栏的请求地址条与控制台（579 行），`detail-request-panels-v2.css` 是右栏
「请求头 / 请求体」两个页签的面板（`api-wb-hdr-*` / `api-wb-body-*`）。页面结构也按同一刀切下去：
`components/ApiCollectionToolbar.tsx`、`components/ApiCaseExplorer.tsx`、`components/ApiCaseRunConsole.tsx`
各自负责一段，请求头与请求体两个页签分别由 `components/ApiCaseHeadersPanel.tsx`、
`components/ApiCaseBodyPanel.tsx` 承担，`components/ApiCaseEditor.tsx` 只留请求地址条与页签编排；
三段配置（环境 / 模板插入 / 后置操作）共用的 props 形状集中在 `components/apiCaseEditorProps.ts`。

- **左栏与右栏的类名换成 `api-wb-*`，但页面根节点仍保留 `api-collection-detail-page`**：`.api-case-sidebar`、
  `.api-case-nav-item`、`.api-case-editor-shell` 这一族类名同时被 UI 测试详情页与用例库使用，它们的规则
  （`detail.css`、`ui-automation/styles/index.css`、`workbench.css` 的 `:is()` 列表）
  必须原地留着；只把 API 详情页自己不再使用、且全仓库再无引用的规则从 `detail.css` 删掉（4111 → 3110 行）。
- 板面这一层要自己压平：`app/styles/workbench.css` 给 `.app-shell.app-shell-macos .workbench-panel` 铺了玻璃底
  + 内高光 + 投影，列表页靠 `.tp-board` 那条带 `.testing-page` 前缀的规则压住，详情页不在 `.testing-page` 里，
  所以要自己写一条带页面类的高权重覆盖。其余颜色全部走 `--srf-*` / `.tone-*`。
- **`Form.useWatch` 对没挂载的 `Form.Item` 返回 `undefined`**：请求体与设置两个页签只有被打开时才挂载，
  所以首屏的「请求体类型 / 超时 / 启用状态」要回落到已加载的用例记录（`editingCase`），否则请求体页签的绿点、
  「超时 5000 ms」和「已禁用」都不会显示。用例列表与页签计数只依赖已挂载的字段，不受影响。
- 运行结果控制台是「横幅 + 页签条 + 滚动内容 + 底部断言条」四段：内容区内部滚动，其余三段固定，与设计稿一致。
  视图切换用文字页签替代了原来的 `Segmented`，计数直接标在页签上。
- **两个键值表格的「末尾空行」只能有一个来源**：请求头面板自带虚线新增行（回车添加，另有快捷注入与批量编辑 RAW），
  所以 `headers` 列表不再由页面补空行；Query 参数页签没有新增行，仍由 `ensureQueryTrailingRow` 保证末尾空行。
  两处都补会让表格里多出一行既有输入框、又什么都没填的空行。
- **请求体状态条的光标位置由编辑器回传**：`JsonEditor` 新增 `onCursorChange`（行 / 列，1 基）与 ref 上的
  `compressDocument()`；`toolbar={null}` 表示外壳不自带工具条，动作条由请求体面板画在编辑器之外。旧的
  `api-body-type-segmented` 与 `json-editor-toolbar-row/-side/-type/-link` 规则随旧实现从 `detail.css`
  删除（全仓库再无引用）。
- 覆盖全局按钮皮肤与输入框皮肤的规则必须按 S14 的写法带 `.app-shell.app-shell-macos` +
  `.api-collection-workbench-page` 前缀与 `!important`，否则与全局皮肤同权重、只靠 import 顺序决胜。
  `styles/detailRequestPanels.test.ts` 锁住这条。
- 状态条与徽标都是真实计算结果：合法性用与校验规则同一份判断，大小按 UTF-8 字节数，行 / 列来自编辑器光标；
  结论色走 `.tone-green` / `.tone-red` 色盘。

**设计稿里没实现的部分**：

| 设计稿元素 | 原因 |
| --- | --- |
| 请求头的「描述 / 备注」列 | 用例的 headers 只有键值，没有说明字段（与 Query 参数行的「说明」列同因） |
| 请求头工具条的「载入项目预设头」 | 没有项目级预设头的数据源，不加入只会空转的入口 |
| 请求体编辑器里的 `{{变量}}` 胶囊与悬停解析值 | 要在 CodeMirror 里加一层模板变量装饰与悬浮提示，属于编辑器能力而非面板样式；变量值到运行时才解析 |
| 请求体的 `form-data` / `binary` / `GraphQL` 类型 | 后端只支持 `none` / `json` / `form`（x-www-form-urlencoded）/ `raw` 四种，补类型要连带改 worker 的发送逻辑 |
| 用例列表底部「导出用例 (JSON)」与「自动排序: 开启」 | 没有导出接口，排序开关也没有对应字段（拖拽排序一直可用，开关状态没有数据可显示） |
| 控制台右上角「格式化 / 复制」 | 响应体已经是格式化后的 JSON；复制没有现成实现，不新增未要求的交互 |
| 用例名右侧的「标签」「预估耗时」 | 用例没有标签与耗时字段，换成了真实存在的请求方式、超时、后置操作数与启用状态 |
| Query 参数行的「说明」列 | 用例的 query 只有键值，没有说明字段 |
| 用例列表的勾选列与批量删除 | 没有批量删除接口 |

`ApiCollectionDetailPage.test.tsx` 依赖的钩子：`.api-wb-toolbar`（含 `运行记录 (N)` 与 `运行测试集` 两个按钮）、
`.api-wb-case-item` 与里面的 `.api-wb-case-method` / `.api-wb-case-item-path` / `.api-wb-case-draft`、
选中项的 `aria-current="true"`、`.api-wb-send`、`.api-wb-console`、`.api-wb-tab-dot`，
以及用例名称输入框的 `aria-label="用例名称"`；搜索框 placeholder 是「搜索用例名称 / 接口路径」。
改这一页时逐条保留。

`ApiCaseHeadersPanel.test.tsx` 依赖：快捷注入按钮的可访问名形如 `+Authorization`（`+` 是按钮文字的一部分）、
虚线新增行的两个 placeholder「添加新的请求头 (键)...」与「值 (支持 {{变量}} 语法)...」、行内按钮的
`aria-label="复制请求头"` / `aria-label="删除请求头"`、批量编辑弹窗的 `aria-label="请求头批量编辑内容"`。
`ApiCaseBodyPanel.test.tsx` 依赖类型胶囊的 `role="tab"`，以及状态条文案「无语法错误 / 存在语法错误 /
大小: N B / 格式: JSON / 编码: UTF-8」。

### UI 测试集详情页（`detail-workbench-v2.css` / `detail-pipeline-v2.css` / `detail-inspector-v2.css`）

UI 测试列表点测试集名称进来的页面按设计稿重做：顶栏（返回 / 标题 + 测试集 / 需求 / 迭代 / 就绪结论 / 上次运行 /
运行记录 / 调试运行 / 运行测试集 / 保存）+ 控制条（选用例 + 运行环境）+ 两栏（左：用例信息条与步骤编辑器；
右：执行回放 / 关键帧快照 / 执行控制台）。样式按职责拆三个文件，都由 `UiTestSuiteCasePage` 引入，选择器互不重叠：
`detail-workbench-v2.css` 是板面、顶栏、控制条与用例顺序弹层，`detail-pipeline-v2.css` 是用例信息条与步骤卡片皮肤，
`detail-inspector-v2.css` 是右栏三张卡片。页面结构同样按职责切：`UiSuiteDetailToolbar`、`UiCaseControlRibbon`、
`UiCaseOrderPopover`、`UiCaseMetaBar`、`UiRunInspector`（内含 `UiRunReplayStage` / `UiRunSnapshotStrip` /
`UiRunConsoleCard`）各自负责一段，页面只留编排、查询与变更。右栏的纯展示数据在 `utils/detailRunView.ts`。

- **板面必须显式压平**：这条路由不在 `.testing-page` 里（实测 `document.querySelector('.testing-page')` 为 null），
  所以 `workbench.css` 的 `.app-shell.app-shell-macos .workbench-panel`（(0,3,0) + `!important`，玻璃底 + 内高光 +
  10px/24px 投影）不会被 `surface-tokens.css` 里 `.tp-board` 那条 (0,2,0) 覆盖拦住，`shared` 那条带 `.testing-page` 的
  (0,6,0) 规则也匹配不到。详情页因此自己写了一条带 `.ui-suite-detail-page` 的 (0,6,0)。
  判据：板面应是 `background: rgba(0,0,0,0)`、`box-shadow: none`、`border-width: 0`
  （它本来是半透明白 + 投影，肉眼不容易发现）。
- **用例列表收进下拉，但要保留的能力有落脚点**：设计稿控制条上只有一个原生 select，而既有能力不能随列表一起消失——
  用例搜索、拖拽重排、逐条删除分别落在 select 的 `showSearch`、`.ui-wb-ribbon-case` 的「用例顺序」弹层
  （`UiCaseOrderPopover`，仍可拖拽）与信息条上的「删除用例」。弹层挂在 body 下，所以它的根节点带 `tp-surface`、
  样式作用域写成 `.ui-wb-order-overlay .ui-wb-order-*`（不是 `.ui-suite-detail-page`）。
- **设计稿控制条上的三个工作区页签（步骤编排 / 回放快照 / 执行控制台）已按用户要求去掉**：工作区只有一种排布
  （左步骤编排 + 右回放与控制台），三张卡片恒定显示，`UiStudioView` / `uiStudioViewOptions` / `ui-wb-cols--*` /
  `ui-wb-ribbon-view*` 一并删除。`detail-workbench-v2.css` 里那条 `.ui-suite-detail-page [hidden] { display: none !important }`
  留着，但服务对象换成了步骤卡片的展开/收起：`.ui-test-case-step-body` 在 index.css 里是 flex 容器，作者样式压得过
  UA 的 `[hidden]`（antd 的 reset 也带同效规则，这条让折叠不依赖三方 reset）。
- **工作区在一个屏内，两栏齐高**：`.ui-wb-cols` 是 `align-items: stretch` 的网格，行高取板上剩余高度（板面本身是
  有高度的滚动容器），两栏因此等高、整页不随内容变长。内容超出这一屏时由各面板内部滚动消化：左栏是步骤列表
  （`.ui-wb-pipeline > .ui-test-case-step-list`），右栏是执行控制台日志（`.ui-wb-console-log`）。
- **右栏三张卡片的高度分配**（踩过的坑写在这里，改这一层时逐条对）：回放按 16:9 定高、空间不够时先收它；
  关键帧单行定高；执行控制台吃掉剩余高度、日志是其中的弹性区。**卡片下限必须写在槽上
  （`.ui-wb-inspector-slot`），不能写在卡片上**——槽才是右栏的 flex 项，写在卡片上会被槽的 `min-height: 0`
  压过去，卡片被压到 0 而内容整片溢出（实测控制台卡片被压成 26px，日志与指标区浮在外面）。
  指标区是 `flex: 0 0 auto` 的页脚，任何高度下都留在卡片里——用户报的「底部指标区被压」就是右栏比一屏高、
  页脚被顶到视口外；三张卡片都到下限后仍放不下（矮屏）时右栏整体滚动，卡片保持完整。
- 首版写成 `align-items: start` 时左栏只有内容那么高，下面留一大片空白。
- **`.ui-test-case-form` 的旧规则已删**（`features/ui-automation/styles/index.css`）：它带着 `padding: 16px 24px 0`
  与 `height: 100%; overflow: hidden`，那是「表单本身是编辑器面板里的滚动容器」时代的产物。留着会让左栏两张卡片
  被内推 24px、比右栏窄，两栏的卡片边缘对不齐（实测左卡 x=124 / 右卡 x=779，删掉后左卡 x=100、栏间距正好 12px）。
  现在表单只是左栏的排布容器，规则写在 `detail-pipeline-v2.css`（拉伸 + 卡片间距 12px）。
- 控制条左侧那一组的子项（下拉 / 计数 / 前后切换 / 顺序 / 新建）加起来接近 560px，所以它的 `flex-basis` 也取 560px：
  空间不够时让右侧那组换行，而不是让左组子项溢出画到右边那组上面（实测过：`flex: 1 1 420px` 时右组的内容被
  「新建用例」整块盖住，`elementFromPoint` 命中的是按钮，而这类遮挡在 jsdom 的布局盲区里看不见）。
- 步骤行的 PASS / FAIL 徽标来自最近一次调试运行的步骤结果（按 `orderNo` 对齐，索引由 `indexUiRunStepResultsByOrder`
  建，重复序号保留第一条），文案由 `formatUiStepResultBadge` 统一给出；没有运行记录时不编造结论，未设置关键字的步骤显示
  「草稿」。行首的拖拽手柄只是把「整行可拖」画出来，不是新的交互。步骤行的字段显隐与折叠摘要由
  `utils/stepRowView.ts` 推导（`UiStepEditor` 只渲染），这份推导有 `stepRowView.test.ts` 单独钉住。
- 左栏根节点上的 `ui-suite-case-editor-panel` 必须保留，`detail-workbench-v2.css` 与
  `detail-pipeline-v2.css` 的选择器都挂在它上面。随之删除的是分栏拖拽（`UiTestPanelSplitter`、
  `utils/uiTestPanelResize.ts`）与 `detailView.ts` 里三个编辑器高度常量，
  以及 `ui-test-case-toolbar` / `ui-test-case-secondary-meta` / `ui-suite-case-empty-list` 等只属于旧结构的规则
  （`ui-automation/styles/index.css` 917 → 790 行，另从 `src/index.css`、`api-automation/styles/detail.css`
  摘掉同名引用）。

**设计稿里没实现的部分**：

| 设计稿元素 | 原因 |
| --- | --- |
| 自动化录屏回放（视频播放器、进度时间、倍速、下载） | 平台只产出逐步截图，没有录屏文件。同一块位置放的是「执行回放」：浏览器外壳显示运行时 URL，舞台显示当前步骤截图，滑轨按步骤打点，可点打点或前后按钮切换 |
| 关键帧快照的「Visual Diff: 0.00%」与「基线一致」 | 没有视觉基线比对，改为「N / M 步有截图」与截图策略，脚注写明没有录屏文件。缩略图角标 `#序号 0.3s` 保留，耗时是**真实**的：相对本次运行第一步开始时间的偏移（`formatUiElapsedTime`）。这一条是**单行横向滚动**（一屏 4 张，与设计稿一致）：截图多时它不能长高，否则会把下面的执行控制台顶出视口；当前帧由回放舞台（上/下一步、滑轨打点）切换时，`UiRunSnapshotStrip` 直接改 `scrollLeft` 把它滚进视野，不用 `scrollIntoView`，免得连带把页面纵向滚走 |
| 控制台右下角的 FCP / 网络请求数 / 内存占用 | 运行记录里没有这些指标，换成真实存在的运行耗时、通过步骤数、失败步骤数 |
| 控制台的 Filter | 按设计稿做主了，但范围就是日志里真实存在的 `info` / `wait` / `assert` / `error` 四种级别（外加「全部」）；汇总行不受过滤影响，过滤后看不到结论会让控制台读起来少一截 |
| 回放舞台死守 16:9 | 舞台按 16:9 定高（设计稿的主视觉），但上限是 `min(40vh, 480px)`：又矮又宽的窗口下它会先收一点，把空间让给日志，而不是把控制台整块挤出视野 |
| 顶栏的「单步调试 (F10)」 | 平台没有逐步单步执行模式，同位置保留对当前用例发起调试运行的「调试运行」 |
| 控制条上的「运行环境: Chrome 122 (Headless)」 | Playwright 版本在前端拿不到（见 UI 测试列表页那一节），改为测试集的执行模式、视口、慢放与步骤超时 |
| 步骤行的「插入前置公共模板」 | 没有公共模板接口；「批量启用/禁用」保留为「全部启用 / 全部禁用」 |
| 用例信息条上的「前置通过率: 100%」 | 用例没有前置通过与率的模型，第二行只留真实的步骤数 |
| 顶栏副标题里的「当前项目 / 当前迭代 / 测试阶段」 | 这三段面包屑是工作台外壳顶栏的内容，页面里不再重复；路径只写测试集 / 需求 / 迭代 |
| 路径末端的版本色块 `v1.0.0` | 测试集没有版本字段；路径只到迭代 |
| 序列化编号 `CASE-##` 之外的用例版本 | 用例没有版本字段 |

`UiTestSuiteCasePage.test.tsx` 依赖的钩子：`.ui-wb-toolbar`（含「运行记录 (N)」与「运行测试集」两个按钮）、
`.ui-wb-ribbon`（「选择用例」「N 个用例」、运行环境文案；`role="tab"` 的视图页签已删除，改这一页时不要加回来）、`.ui-wb-case-meta`（序号与
「包含 N 个步骤」）、`.ui-wb-pipeline`、`.ui-wb-order-panel` 与 `.ui-wb-order-item.selected`、
`.ui-wb-replay`（`.ui-wb-replay-overlay`、`AUT DONE`）、`.ui-wb-strip`（角标形如 `#1 0.0s`）、
`.ui-wb-console`（逐步骤日志与汇总行、`过滤` 按钮与级别菜单），
以及用例名称输入框的 `aria-label="用例名称"`、「前一个用例 / 后一个用例」两个 `aria-label`。非空用例列表时
「新建用例」按钮的 `aria-label` 是「新建 UI测试用例」（空态里那个按钮的可及名仍是「新建用例」），
`src/test/automationEditors.test.tsx` 按前者点击。改这一页时逐条保留。

### 测试单执行工作台（`workspace-v2.css` / `workspace-verdict-v2.css`）

测试单列表点名称进来的页面重做成三栏：执行用例清单 / 用例详情 / 执行判定与缺陷。样式文件按职责拆两个
（合起来会超过 C1 的 600 行上限），都由 `TestOrderWorkspacePage` 引入，选择器互不重叠、全部挂在 `.test-order-workspace-page` 下。
`features/test-orders/styles/index.css` 只保留加入用例弹窗与图谱弹框的规则（858 → 79 行），旧的工作台规则已删除。

**两个 `.workbench-panel` 的坑**（顶栏踩过，值得记）：

- `app/styles/workbench.css` 的 `.workbench-panel { display: flex; flex-direction: column }`：工作台顶栏是 `workbench-panel`，
  要显式写回 `flex-direction: row`，否则整条栏变竖排。
- 同处还有 `.workbench-panel { height: 100% }`（在 `features/testing/styles/index.css` 里）：顶栏这类不该撑满的条必须显式
  `height: auto`，否则它会把同一个 flex 容器里的兄弟节点全挤到底部。

**设计稿里没实现的部分**：

| 设计稿元素 | 原因 |
| --- | --- |
| 每个步骤的「通过 / 失败 / 阻塞」判定按钮 | 条目结论是整条一个（`TestOrderEntry.status`），没有逐步结果模型；`TestOrderWorkspacePage.test.tsx` 也断言了不应出现逐步判定按钮 |
| BUG 卡片（优先级 / 处理中 / 指派给 / 解绑） | 只存了 `zentaoBugId`，没有缺陷详情接口；做成了「禅道缺陷 #ID + 解绑」 |
| 底部「提交当前用例记录」 | 判定是即时保存的（保存状态就在同一栏底部显示），再加提交按钮会误导 |
| 耗时预估 | 条目没有这个字段 |

`TestOrderWorkspacePage.test.tsx` 依赖的钩子必须保留：判定按钮的 `aria-label="判定该用例为通过"` 及其禁用态、状态筛选胶囊的
无障碍名形如 `未执行 1`（标签与计数之间要有空格）、勾选框 `选择第 N 条执行条目` / `移除第 N 条执行条目` / `判定后自动前进`、
`上一条` / `下一条` 按钮、以及「加入用例」按钮**恰好两个**（顶栏与空态各一个）。

`priorityTone`（优先级 → 色盘色调）被用例库与工作台同时使用，按 S4 上提到 `shared/utils/priorityTone.ts`；`caseTone.ts` 只剩用例类型那部分。

## 四、目录契约

| # | 规则 | 拦住的问题 | 检查 |
| --- | --- | --- | --- |
| S11 | feature 目录固定为 `api/`、`components/`、`hooks/`、`pages/`、`styles/`、`utils/`，加一个 `types.ts`。新增目录名需走 ADR（`docs/studio/adr/`） | 实际另有 `store/`×2（auth、projects）、`config/`×2（api-automation、ui-automation）、`constants/`×1、`__fixtures__/`×1 | 扫描脚本白名单（**待强制**） |
| S12 | 组件目录与散文件的取舍：有子文件（样式、测试、index）的组件用目录，单文件组件用散文件。同类依赖不得散落 | `shared/components/` 中 `ActionButton/`、`JsonEditor/`、`MtxLogo/`、`TextCodeEditor/` 是目录，而 `codeEditorTheme.ts` 是散文件——它实际是 `JsonEditor`(`JsonEditor.tsx:18`) 与 `TextCodeEditor`(`TextCodeEditor.tsx:16`) 两个组件的共享依赖，却与四个组件目录并列成同级散文件 | 评审（**待强制**） |
| S13 | 死代码零容忍：无人引用的 CSS、失效的 lint 覆盖块、空目录，发现即删 | `features/projects/pages/SprintDetailPage.css` 7 行**从未被任何文件 import**，但类 `sprint-dashboard-test-empty` 确实在 `SprintDetailPage.tsx:314` 使用——样式完全不生效；`eslint.config.js:25-30` 针对已不存在的 `src/components/**`、`src/pages/**` 关闭规则，该放行从未生效。2026-09-23 按这条规则扫了一轮：删掉 82 条无人引用的规则、瘦身 42 条选择器列表，6 个文件共减约 1500 行（`testing/styles/index.css` 2579 → 1844、`test-cases/styles/index.css` 378 → 268、`ui-automation/styles/index.css` 934 → 755、`src/index.css` 159 → 92、`shared/styles/page-frame.css` 1444 → 1135、`test-orders/styles/workspace-v2.css` 579 → 508）。删完在四个列表页做了逐元素计算样式比对，零差异（判据见 README 的那一段） | 扫描脚本孤儿检查（**待强制**）；**扫描器不能自动决定删什么**：`segment-${key}`、`tone-${tone}` 这类拼接会被误判成死类（实测把 `.segment-passed`、`.tone-orange` 判死过），`.ant-*` / `.cm-*` / `.react-flow*` / `.recharts*` 是三方类名同样会被判死；必须逐个类名回到 TS 里确认零引用、且不是 `前缀-${...}` 的动态分支，再按显式白名单删 |

## 五、代码规范

| # | 规则 | 拦住的问题 | 检查 |
| --- | --- | --- | --- |
| C1 | 文件体积上限：新建 `.tsx` ≤ 400 行、非组件 `.ts` ≤ 300 行、`.css` ≤ 600 行。拆分的口径是**按职责**，不是按行数对半切 | 10 个 TS 超 1,000 行（最大 1,602）；10 个 CSS 超 800 行（最大 6,619，占全项目 25,404 行的 26%）；`ai-testing/types.ts` 657 行而其余特征 15–302 行 | ESLint `max-lines`（**存量豁免**：现有违规按当前行数冻结） |
| C2 | 页面组件只做**编排**：路由参数、数据查询、装配子组件。渲染细节、表单、弹窗、表格列定义一律下沉到 `components/` | `ai-testing` 的 5 个任务详情页合计 5,292 行，是同一套骨架的复制：轮询声明 10 处、`getRunSortTime` 定义 3 处、`resolveRunRecord` 定义 5 处、`selectedRunRecordId ?? runRecords[0]` 4 处 | 评审 + `max-lines`（**待强制**） |
| C3 | 单函数／单组件 ≤ 150 行；一个组件只做一件事 | 与 C2 同源 | ESLint `max-lines-per-function`（**待强制**） |
| C4 | API 模块：每 feature 一个 `api/`，≤ 300 行，超了按领域拆；组件**不得**直接调请求层 | `features/ai-testing/api/aiTesting.api.ts` 329 行混了 6 个不相关领域共 47 个方法（AI 技能库、API/功能/UI 用例生成、需求分析、代码风险） | ESLint `max-lines` + 评审（**待强制**） |
| C5 | **写工具函数前必须先搜 `shared/utils/`**；同语义函数只允许一处实现 | `normalizeText` 两份（`shared/utils/payload.ts:1`、`api-automation/utils/apiCaseEditor.ts:127`）；`orderNo ?? Number.MAX_SAFE_INTEGER` 出现 12 处、构成 8 个排序点（`apiCaseEditor.ts:269`、`UiTestSuiteCasePage.tsx:873,898`、`useApiExecution.ts:180`、`ApiCollectionDetailPage.tsx:802`、`uiTestCaseEditor.ts:74`、`renderUiRunSteps.tsx:69` 等）；`toRecord` / `toRecordArray` 的重复实现已清理，AI 结果展示、任务详情与测试单图谱直接引用 `shared/utils/value.ts` | 评审 + 定期重复扫描（**待强制**） |
| C6 | 复制阈值：同一段逻辑出现到**第三处**必须抽取。适用于页面骨架、弹窗、Drawer、表格皮肤 | 表格的共用尺寸和底色现已收敛至 `shared/styles/list-table.css`，AI 详情页的执行和运行记录删除收敛至 `hooks/useTaskRunActions.ts`；仍待处理：3 个导入冲突弹窗（84/72/175 行，前两个约 95% 相同）；5 个任务 Drawer 共 527 行，4 个 props 契约完全一致 | 列表样式与运行操作由相应测试覆盖；其余依赖评审（**待强制**） |
| C7 | 命名契约：导出名的前缀必须与适用范围一致。**跨 feature 使用的东西不得带某个 feature 的前缀** | `features/ai-testing/utils/taskStatus.tsx` 的 9 个导出里 5 个带 `ApiCase*` 前缀，但该模块同时被 functional、requirement、code-risk、ui 等任务页使用，还被**跨 feature** 的 `features/test-orders/components/TestOrderGraphViewer.tsx:15-18` 引用——前缀与适用范围不符 | 评审（**待强制**） |
| C8 | 类型归属：`features/<f>/types.ts` 每 feature 一个。通用类型放 `shared/` | 同 C1 | ESLint `max-lines`（**待强制**） |

## 六、新增模块检查清单

新建页面或模块时逐条自查（配合本文件第五节「代码规范」使用）：

1. 放对层了吗？业务代码进 `features/<f>/`，无业务语义的进 `shared/`（S4）
2. import 方向对吗？没有从 `shared/`、`utils/` 反向引用 feature（S1）
3. 引用别的 feature 了吗？只碰了对方的 `api/` 和 `types.ts`（S3）
4. CSS 放在 `features/<f>/styles/` 了吗？没有放进 `components/` 或 `pages/`（S6）
5. 类名是自己的 feature 前缀吗？没有污染全局层（S7）
6. 需要新 token 吗？定义了就该进唯一 token 文件（S8）
7. 样式是自己 import 的吗？没有靠别的页面顺带生效（S9）
8. 目录名在 `api/components/hooks/pages/styles/utils` 之内吗？（S11）
9. 新文件在 400/300/600 行以内吗？超了先拆（C1）
10. 页面是否只做编排，渲染细节已下沉？单函数 ≤ 150 行（C2、C3）
11. 要写的工具函数在 `shared/utils/` 里已经有了吗？（C5）
12. 有没有第三处重复需要抽取？（C6）

## 已知验证盲区

以下几项限制在 2026-09-20 的整改验证中记录，截至目前仍然成立。它们不是待修的债务，而是**当前检查覆盖不到的地方**，不要误以为已被覆盖：

- **没有真实部署环境的端到端验收。** 自动化覆盖的是 jsdom 下的单元与组件测试；浏览器端到端、以及真实部署后的验收均未做。
- **静态引用图不能证明所有动态业务路径可达。** 本文的孤儿检查与依赖方向检查都基于静态 import 分析，动态拼接的路径不在覆盖内。
- **构建体积没有预算约束。** 主包 gzip 约 970–980 kB、CSS 约 77 kB（随每次构建浮动），且全项目 0 处代码分割（无 `React.lazy` 或动态 `import()`），recharts、`@xyflow/react`、`docx-preview`、CodeMirror 全部进入主包。本文的规则里**没有**一条拦住它继续增长。

## 待办：把规则变成约束

按收益排序，前三项不需要修改任何现有代码：

1. **S1、S3 上 ESLint** —— 依赖方向人眼最难发现。`no-restricted-imports` + 按 feature 生成规则块；存量豁免只有 4 个文件（`shared/api/request.ts`、`src/utils/updatePayload.ts`、`test-orders/components/TestOrderGraphViewer.tsx`、`test-orders/types.ts`），用 `overrides` 显式列名
2. **C1、C3、C4、C8 上 ESLint `max-lines`** —— 现状违规按当前行数冻结在豁免名单里，新文件直接受 400/300/600 上限约束
3. **S6–S13 上扫描脚本** —— 位置、前缀、token、孤儿文件都是可机械判定的，一个零依赖脚本即可覆盖
4. **把检查挂到会自动跑的地方** —— 没有 CI 和 hook 的话，上面三条依然只是文档
