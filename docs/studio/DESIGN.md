# 前端设计规范（studio）

本文描述 MTX 前端（`apps/studio`）的**界面设计规范**：外壳与页面骨架、色彩与排版 token、组件契约、主题实现机制，以及由测试锁定的样式不变量。

- 领域术语与业务概念 → [CONTEXT.md](CONTEXT.md)
- 运行时、源码结构、启动与构建 → [README.md](README.md)
- 架构决策 → `docs/studio/adr/`

## 如何阅读

文中每条结论都标注了它的可信度来源：

| 标记 | 含义 |
| --- | --- |
| **规范** | 已有测试或注释背书，改动会失败或被明确劝阻 |
| **现状** | 代码目前如此，但未被测试锁定，可以改 |
| **债务** | 当前不一致、重复或已失效的死代码，建议收敛 |

本文只描述**界面与样式**层面的约定。数据流、路由与请求语义在需要解释布局时附带说明，但不作为权威来源。

---

## 1. 设计基调

从代码与注释中可归纳出六条贯穿全站的取向：

1. **固定外壳 + 玻璃拟态内容层。** 外壳（侧栏、页头、画布）使用固定画布色与半透明表面，配 `backdrop-filter: saturate(180%) blur(22–24px)`；内容区不做装饰性动效。浅色为 macOS 白玻璃，深色为 GitHub dark 玻璃。**现状**
2. **按钮只有一套皮肤。** 扁平、无渐变、无彩色阴影、无位移，圆角 8px、字重 500，全部由 `app/styles/buttons.css` 的 `@layer app-buttons` 强制，覆盖一切页面级重绘意图。**规范**
3. **列表只有一套皮肤。** 表头 42px、四角 8px、`clip-path: inset(0 round 8px)`；行高 48px、内距 `8px 16px`。四个互不相干的模块必须算出完全相同的值。**规范**
4. **深浅主题对等。** 任何新增页面/模块都必须同时给出 `:root[data-theme='dark']` 对照；只有浅色的模块被视为未完成。**规范**
5. **中文界面 + 可达性契约。** 界面文案、空态、页脚、提示一律中文；所有按钮有中文可访问名，图标按钮必须提供 `aria-label` 或 `title`。**规范**
6. **长文本与 UI 字体分离。** 需求描述、用例简述等成段业务文本使用衬线字体族，与无衬线 UI 栈区分。**现状**

---

## 2. 技术底座

| 关注点 | 选型 |
| --- | --- |
| 框架 | React 19 + TypeScript 6 + Vite 8 |
| 组件库 | Ant Design 6（`antd` + `@ant-design/icons`） |
| 路由 | React Router 7（`BrowserRouter`） |
| 服务端状态 | TanStack Query 5 |
| 客户端状态 | Zustand 5（仅 3 个 store） |
| 编辑器 | CodeMirror（`@uiw/react-codemirror`，JSON/YAML） |
| 图形 | `@xyflow/react`（用例关系图）、`recharts`（趋势图） |
| 其他 | `docx-preview`（文档预览）、`html-to-image` |
| 测试 | Vitest 4 + jsdom + Testing Library；`fileParallelism: false` |
| 样式方案 | 原生 CSS，无 CSS Modules / CSS-in-JS；类名前缀按 feature 划分 |
| 路径别名 | `@/*` → `src/*`（`vite.config.ts` 与 `tsconfig.app.json` 同步维护） |

---

## 3. 布局骨架

### 3.1 三级路由

导航不是一层路由树，而是三层叠加：

| 层 | 位置 | 形态 |
| --- | --- | --- |
| L1 | `src/app/router/routes.tsx` | 三条：`/login`、`/register`、`/*`（`ProtectedRoute` 包裹 `AppShell`） |
| L2 | `src/app/layouts/AppShell.tsx` 内部的 `<Routes>` | 业务页面全部在此二次分发；`src/app/router/routes.tsx` 不含业务页面 |
| L3 | 页面内 `useSearchParams` 的 `?tab=` | `TestingPage`（`library`/`orders`/`api`/`ui`）、`AiTestingOverviewPage`（`tasks`/`skills`）、`BaseServicesPage`（`llm`/`zentao`/`gitlab`） |

L2 还负责把实际路径折回侧栏高亮键：`/test-cases`、`/test-orders`、`/api-automation`、`/ui-automation` 全部高亮 `/testing`。**现状**

三处 `?tab=` 都保留旧别名重定向：`/test-cases → /testing?tab=library`、`/api-automation → /testing?tab=api`、`/ui-automation → /testing?tab=ui`。**规范**（已登录用户的旧链接必须继续可用）

L3 之下还有一层**非 URL** 的局部切换：`ProjectsPage` 的 `Segmented`（迭代 / 需求）、`UnifiedAiTestingPage` 的 `Segmented`（五类任务）。这类切换不写 URL，刷新后回到默认档。**现状**

### 3.2 外壳尺寸

```
Layout.app-shell.app-shell-macos
├─ Sider.app-sider            固定 76px
│  └─ .brand-row              64px（MtxLogo 36 + “MTX”）
│     └─ Menu                 inline，4 项，图标在上文字在下，单项高 72px × 宽 64px
└─ Layout
   ├─ Header.app-header.compact-header   48px
   └─ Content.app-content → 页面
```

| 元素 | 值 | 来源 |
| --- | --- | --- |
| 侧栏宽 | 76px（`width`/`min-width`/`max-width`/`flex` 四者都是 `76px !important`） | `app/styles/workbench.css:643` |
| 品牌区高 | 64px | `workbench.css:625` |
| 页头高 | 48px（`.compact-header`） | `workbench.css:158` |
| 侧栏菜单项 | 高 72px × 宽 64px，圆角 10px，字号 12px/行高 18px，图标 20px，选中色 `#6d5dfc`（浅）/ 薄荷（深），选中底色 transparent | `workbench.css:658` |
| 页面高 | `height: calc(100vh - 56px)`，`html/body/#root` 为 `height:100%; overflow:hidden` | `workbench.css:466, 484` |
| 页面最小高 | `calc(100vh - 48px)` | `workbench.css:171` |

外壳与画布是全屏固定、内部滚动（`.workbench-page` 为纵向 flex，面板内部 `overflow: auto`）。**规范**：新增页面必须继承这套「外层不滚、内容区自滚」的模型，不要在页面根节点加 `overflow` 或整页 `padding`。

### 3.3 侧栏

四项、单层、无子菜单，全部中文标签：

| key | 图标 | 标签 |
| --- | --- | --- |
| `/projects` | `projects` | 项目总览 |
| `/testing` | `testing` | 测试 |
| `/ai-testing` | `testDesign` | 测试设计 |
| `/base-services` | `services` | 基础服务 |

图标来自 `AppIcon`（彩色 SVG，`size={20}`），不是 antd 图标。**现状**

### 3.4 页头

页头承担全局上下文，页面自身不重复渲染项目/迭代选择器：

- 左：`当前项目 / <Select>`、`当前迭代 / <Select>`（均 `variant="borderless"`，迭代默认哨兵值 `all` 显示为「全部迭代」）
- 中：测试阶段反馈说明 + `mailto:` 链接（`role="note"`）
- 右：`新建项目`（`ActionButton type="primary" operation="create"`）、主题切换圆形按钮（`MoonOutlined`/`SunOutlined`，32×32）、用户下拉（个人设置 / 退出登录）
- 在 `/profile` 下隐藏项目选择区与新建按钮（`showWorkbenchHeader`）

**规范**：项目与迭代的当前值只能来自 `useActiveProject` / `useActiveSprint`。页面内的筛选是同一对「迭代 → 需求」联动，切换迭代必须重置需求选择与分页。

### 3.5 列表页骨架

```
.workbench-page.<feature>-page
└─ .workbench-project-toolbar            最小高 48px，margin 12px 24px 0，padding 8px 14px，圆角 6px
   ├─ 标题（h4.ant-typography，15px）
   ├─ .workbench-board-switcher（Segmented，胶囊，item 最小宽 88px）
   └─ 操作区
└─ .workbench-tabs                       flex:1，padding 12px 24px 16px，gap 12px
   └─ section.workbench-panel.workbench-board-panel
      ├─ .panel-header                   最小高 48px，padding 8px 14px
      │  ├─ 标题 + 筛选组（迭代/需求/优先级…）
      │  └─ 主操作（ActionButton）
      ├─ .table-body-scroll              flex:1; overflow:auto
      │  └─ 表格 / 卡片网格
      └─ .table-footer                   最小高 58px，左「共 N 条」右分页
```

**规范**：`.workbench-panel` 是通用表面原语，列表页与详情页都基于它；页脚文案统一走 `footerRange()`（`shared/utils/pagination.ts`），不要手写分页文案。

### 3.6 详情页骨架（双栏）

集合类详情（API 集合、UI 套件）与执行工作台统一为「侧栏列表 + 主面板」：

```
.page-frame
└─ .api-collection-detail-layout（或 .ui-suite-case-layout）
   ├─ aside.workbench-panel.<feature>-sidebar
   │  ├─ .panel-header                    返回按钮（ArrowLeftOutlined + 中文 aria-label）+ 标题 + 计数
   │  ├─ .<feature>-sidebar-toolbar       搜索框 + 导入
   │  └─ .<feature>-sidebar-scroll        条目列表（.selected / .dragging 状态类）
   └─ main / section.workbench-panel      编辑器或执行面板
```

**规范**：返回按钮一律为文字按钮 + `ArrowLeftOutlined`，且必须有明确中文 `aria-label`（如「返回 UI测试集列表」），不要写「返回」。

### 3.7 AI 任务详情骨架

五类 AI 任务详情共用第三种骨架：

```
.ai-task-detail-layout
├─ Card.ai-task-detail-summary-card
│  ├─ .ai-task-detail-inline-meta          label/value 内联项
│  └─ .ai-task-detail-inline-actions       运行 / 编辑 / 删除
└─ .ai-task-detail-split
   ├─ aside.ai-task-detail-nav-panel        任务信息、导航（分区标题：输入 / 输出）
   └─ section.ai-task-detail-main-panel     主区（head + body）
```

### 3.8 响应式

- **只有 `max-width` 媒体查询，没有 `min-width`，没有容器查询，没有 `prefers-color-scheme`**（主题永远显式）。**规范**
- 主断点 `900px`：外壳改为文档流滚动（`height:auto; overflow:visible`），工具条改纵向，页面内距降到 16px，`project-select` 收窄到 200px。**规范**
- 宽屏阶梯 `1880 / 1560 / 1280 / 980 / 680`：仅用于卡片网格列数（`minmax(176px, auto)` 系列）。**现状**

---

## 4. 色彩

### 4.1 全局基础 token（`src/index.css`）

| Token | 浅色 | 深色 |
| --- | --- | --- |
| `--app-bg` | `#f4f6fa` | `#171b26` |
| `--app-text` | `#172033` | `#e6edf7` |
| `--app-link` | `#1677ff` | `#7cc3a3` |
| `--description-text` | `#596579` | `#b5c0d2` |
| `--description-text-muted` | `#738096` | `#8d98ad` |
| `--description-bg` | `rgba(89, 101, 121, .045)` | `rgba(255, 255, 255, .035)` |
| `--description-border` | `rgba(148, 163, 184, .18)` | `rgba(148, 163, 184, .16)` |
| `--description-font` | 衬线族（见 §5） | 不变 |

深色的 `--app-link` 从蓝变薄荷绿，这是深色主题事实上的强调色，也对应 antd 的 `colorPrimary`。**现状**

### 4.2 按钮调色板（唯一皮肤）

`app/styles/buttons.css` 定义 21 个 `--button-*` token 的浅/深两套值：

| Token | 浅色 | 深色 |
| --- | --- | --- |
| `--button-text` / `-bg` / `-border` | `#526176` / `#ffffff` / `#dce3ec` | `#c4cfdf` / `#252d3b` / `#3a4659` |
| `--button-hover-bg` / `-hover-border` | `#f3f6fa` / `#bdcadb` | `#303b4c` / `#566982` |
| `--button-active-bg` | `#e9eef5` | `#39485d` |
| `--button-primary-text` / `-bg` / `-border` | `#24578f` / `#e3edf9` / `#b5cbe5` | `#abcdf7` / `#25364d` / `#3a5576` |
| `--button-primary-hover-bg` / `-hover-border` | `#e1edfc` / `#a9c5e9` | `#2e4461` / `#577aa6` |
| `--button-primary-active-bg` | `#d5e5f9` | `#385477` |
| `--button-danger-text` / `-bg` / `-border` | `#b54550` / `#fff2f3` / `#efcdd2` | `#f0a8b0` / `#3d2933` / `#66424d` |
| `--button-danger-hover-bg` / `-active-bg` | `#fde6e9` / `#f9d9de` | `#50323e` / `#61404c` |
| `--button-disabled-text` / `-bg` / `-border` | `#98a2b3` / `#f4f6f8` / `#e4e8ee` | `#788498` / `#232a36` / `#333d4d` |
| `--button-focus` | `#8bb2e5` | `#729cce` |

规则（全部写在 `@layer app-buttons` 内，且全部带 `!important`）：

- 基准 `.ant-btn`：颜色/底色/边框取自 6 个 `--button-current-*` 间接层；`box-shadow`、`text-shadow`、`transform` 一律 `none`；`font-weight: 500`。
- 圆角：非 `circle`/`round` 的按钮统一 8px。
- `primary` → 浅蓝底 + 深蓝字的**低饱和主按钮**（不是实心品牌蓝）；`dangerous` 与 `.action-btn-delete` → 红色系；`text`/`link`/`ghost` → 透明底；`link` 用 primary 文字色。
- `:focus-visible` → `outline: 2px solid var(--button-focus); outline-offset: 2px`。
- `:disabled` → 禁用三色 + `cursor: not-allowed`；`text`/`link` 禁用时保持透明底。

**规范（机制推导，建议浏览器实测复核）**：该层之所以能"压过一切"，是因为 CSS 层叠规定*分层内的 `!important` 优先于任何未分层的 `!important`*（正常声明则相反）。因此 `workbench.css`、`base-services/styles/index.css`、`testing/styles/index.css`、`api-automation/styles/detail.css` 中那些给主按钮设 `linear-gradient(...)`、`border-radius: 10px`、彩色 `box-shadow` 的规则**实际不生效**——包括 `layout.css:197` 的 `#006ef2`、`api-automation/styles/overview.css` 的 `--tp-action-*` 五色 action 体系（新建绿/读取蓝/编辑琥珀/删除红/保存青）。

由此得出两条需要记住的实际效果：

- 主按钮在浅色下是**浅蓝底 `#e3edf9` + 深蓝字 `#24578f`**，深色下是 `#25364d` + `#abcdf7`。
- 操作按钮之间**不用颜色区分语义**，只靠图标 + 文字；唯一带语义色的是删除（红）。

详见 §12 债务项。

### 4.3 antd 运行时 token（`app/providers/ThemeProvider.tsx`）

| | 浅色 | 深色 |
| --- | --- | --- |
| `colorPrimary` / `colorInfo` | `#1677ff` | `#7cc3a3` |
| `colorSuccess` | — | `#7cc3a3` |
| `colorWarning` / `colorError` | — | `#f5c26b` / `#ff6b81` |
| `colorBgBase` / `-Container` / `-Elevated` | — | `#191d27` / `#202531` / `#262c39` |
| `colorText` / `colorTextSecondary` | — | `#e6edf7` / `#96a0b5` |
| `colorBorder` / `colorSplit` | — | `#2f3544` / `#2a3040` |
| `borderRadius` | 10 | 10 |
| `Layout.headerBg` / `siderBg` / `bodyBg` | `#ffffff` / `#f2f3ff` / `#faf9ff` | `#1d2230` / `#171c28` / `#171b26` |
| `Menu.itemSelectedColor` / `itemHoverColor` | `#6d5dfc` | `#7cc3a3` |
| `Menu.itemSelectedBg` | transparent | transparent |
| `Button.borderRadius` / 三种 shadow / `fontWeight` | 8 / `none` / 500 | 同 |

深色下 `Layout.*` 三色会被 `dark-polish.css` 的固定画布覆盖，基本失效。**债务**

### 4.4 外壳玻璃 token

**浅色**（`workbench.css`，作用域 `.app-shell.app-shell-macos` 与 `.app-shell.app-shell-base-services`）：

| Token | 值 |
| --- | --- |
| `--mac-glass-page` | `#f5f7fa` |
| `--mac-glass-sidebar` / `-header` | `rgba(246, 248, 251, .78)` |
| `--mac-glass-panel` / `-panel-strong` | `rgba(255, 255, 255, .68)` / `.82` |
| `--mac-glass-card` | `rgba(255, 255, 255, .72)` |
| `--mac-glass-border` / `-border-soft` | `rgba(15, 23, 42, .065)` / `.045` |
| `--mac-glass-text` / `-muted` / `-subtle` | `#172033` / `rgba(23,32,51,.52)` / `.38` |
| `--mac-glass-blue` / `-green` | `#0a84ff` / `#3f995b` |

**深色**：两套并存且数值不一致——

- `--mac-dark-*`（`workbench.css:2613`）：canvas `#0d1117`、panel `rgba(22,27,34,.78)`、card `.72`、border `rgba(48,54,61,.86)`、text `#f0f6fc`、muted `#8b949e`、blue `#58a6ff`、blue-strong `#388bfd`、danger `#ff7b72`、success `#3fb950`
- `--github-dark-*`（`app/styles/dark-polish.css:2`）：同一画布与文字色，但 panel `.86`、card `.78`、border `.9`

另有一组 `--mac-action-*`（蓝 `#0a84ff` / `#1677ff`、危险 `#ff3b30`）服务于模块页按钮，但受 §4.2 影响**不生效**。**债务**

### 4.5 页面级 token 家族

约定：**新 token 不新增全局变量，而是在所属 feature 文件里声明 `<feature>-*` 页面作用域家族，并在同一文件给出 `:root[data-theme='dark']` 对照。** **规范**

现存家族：`--ai-*`（27 个）、`--base-*`（16 个）、`--testing-*`（7 个）、`--api-test-*`、`--profile-*`、`--detail-glass-*`、`--project-overview-*`、`--tp-*`（跨文件分片，见 §12）。

### 4.6 语义标签（深色）

16 个 antd 预设色在深色下各有专属前景/背景对，且别名必须同值。**规范**（`darkSemanticTags.test.ts` 逐条断言）

| 预设 | 前景 | 背景 |
| --- | --- | --- |
| `default` | `rgb(179,192,209)` | `rgba(148,163,184,.14)` |
| `gold` / `warning` | `rgb(229,178,80)` | `rgba(217,164,65,.18)` |
| `cyan` | `rgb(109,213,200)` | `rgba(20,184,166,.16)` |
| `purple` | `rgb(182,154,247)` | `rgba(139,92,246,.18)` |
| `green` / `processing` / `success` | `rgb(91,192,132)` | `rgba(63,185,116,.18)` |
| `error` | `rgb(239,122,122)` | `rgba(239,92,92,.16)` |
| `red` | `rgb(242,127,137)` | `rgba(244,63,94,.18)` |
| `volcano` | `rgb(242,155,112)` | `rgba(249,115,22,.18)` |
| `orange` | `rgb(240,164,93)` | `rgba(245,139,47,.18)` |
| `lime` | `rgb(168,216,104)` | `rgba(132,204,22,.18)` |
| `blue` | `rgb(120,174,242)` | `rgba(74,144,226,.18)` |
| `geekblue` | `rgb(154,174,255)` | `rgba(99,102,241,.18)` |
| `magenta` | `rgb(240,140,188)` | `rgba(236,72,153,.18)` |

`warning≡gold`、`processing≡success≡green` 是有意别名，不要"修正"。

---

## 5. 排版

### 5.1 字体族

| 用途 | 字族 | 位置 |
| --- | --- | --- |
| 基准 UI | `Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` | `index.css` `:root` |
| 工作台页面 UI | `-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", "PingFang SC", "Microsoft YaHei UI", sans-serif` | workbench / testing / ai-testing（常带 `!important`） |
| **成段业务文本（衬线）** | `"LXGW WenKai Screen", "Noto Serif SC", "Source Han Serif SC", "Songti SC", "Microsoft YaHei", ui-serif, Georgia, serif` | `--description-font` |
| 代码（三套并存） | `Consolas, "Cascadia Mono", "Courier New"` / `"SFMono-Regular", Consolas, …` / `ui-monospace, SFMono-Regular, …` | 各 feature CSS |
| 登录页 | `'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif` | `auth.css` |

### 5.2 字号阶

实际使用的有效阶：**12 / 13 / 14 / 15 / 16 / 18 / 20 / 24 / 28**（12px 是主力，行内表格与元信息）。语义归属：

| 字号 | 用途 | 配套行高 |
| --- | --- | --- |
| 12px | 表格表头与正文单元格、标签、元信息 | 18px |
| 13px | 列表名称、页脚计数、描述正文、`.ant-typography-secondary` | 20–22px |
| 14px | 描述 `textarea`、项目选择区 | — |
| 15px | 工具条标题、面板表头 | 22px |
| 16px | 标签页 | — |
| 18px | `panel-header` 标题 | — |
| 20px | 项目选择器当前值（`font-weight: 700`） | — |
| 24px | 页头标题、设置页标题（`font-weight: 700`） | 32px |
| 28px | 基础服务/测试设计页面 hero | — |

### 5.3 衬线描述字体契约

`--description-font` 配 13px / 行高 1.72 / `letter-spacing: 0.01em` / `overflow-wrap: anywhere`。生效方式是一份**显式白名单**：`index.css` 里 18 个类选择器（`.project-description-text`、`.sprint-card-description`、`.ai-task-card-description`、`.functional-case-brief`、`.ui-test-case-step-subtitle` 等）加 5 个 `textarea` 属性选择器（`#description`、`$=_description`、`*=_description_`、`#summary`、`$=_summary`）。**现状**

注意：白名单要在三处重复书写（正文规则、placeholder 规则、深色覆盖），新增描述类名需同步修改。**债务**

---

## 6. 几何

### 6.1 圆角三档

| 档位 | 值 | 用法 |
| --- | --- | --- |
| 胶囊 | `999px` | 标签、筛选条（`.requirement-filter-bar`）、`Segmented`、状态点 |
| 现代扁平 | `8px` | 按钮、分页项、列表表头四角（含 `clip-path`）、`--tp-card-radius` |
| antd 默认 | `10px` | 输入框、抽屉、弹窗、卡片（来自 `ConfigProvider.borderRadius`） |
| 工具条 | `6px` | `.workbench-project-toolbar` |
| 遗留 | `2px` / `4px` | `layout.css` 旧规则（`.app-search`、`.workbench-panel`、`.project-actions .ant-btn-primary` 等），多数已被 6/8/10px 取代 |

### 6.2 间距

4px 网格，主力 `8 / 12 / 16`；`10px` 出现频率很高（约 80 处），是网格外的半步，属于既有事实。页面级内距 **24px**，面板内部 **14–16px**。**现状**

### 6.3 固定尺寸

| 元素 | 值 |
| --- | --- |
| 侧栏 / 品牌区 / 页头 | 76px / 64px / 48px |
| 工具条最小高 | 48px |
| 面板表头最小高 | 48px |
| 表格页脚最小高 | 58px |
| 表头行 / 正文行 | 42px / 48px |
| 页面高 | `calc(100vh - 56px)` |
| 项目选择器最小宽 | 260px（≤900px 时 200px） |
| 圆形图标按钮 | 32×32 |
| 设置卡片最大宽 | 560px |

---

## 7. 组件规范

### 7.1 ActionButton（所有操作按钮的唯一入口）

`shared/components/ActionButton`，`Omit<ButtonProps, 'icon'> & { operation: ActionName; iconOnly?: boolean }`。

- **不传图标**：图标与默认中文文案由 `shared/icons/actions.ts` 的 `actionRegistry` 决定（`create 新建`、`run 运行`、`edit 编辑`、`delete 删除`、`save 保存`、`refresh 刷新`、`download 下载`、`upload 上传`）。要新增操作就往注册表里加，而不是在调用点传 `icon`。**规范**
- **视觉语义**：没有 `variant`；视觉来自 antd `type`，加上 `danger` 默认由操作推导——`delete` 自动为危险色，调用方无需声明。**规范**
- **可访问名优先级**：`aria-label` > `title` > 字符串 `children` > 注册表文案。传节点型 `children` 时若不传 `aria-label`，按钮将没有可访问名。**规范**
- **`iconOnly`**：不渲染文字，原生 `title` 被移除，整体包在 `Tooltip` 里（回退到可访问名）。必须配 `aria-label` 或 `title`。**规范**
- 稳定类名钩子：`action-btn-create` / `-run` / `-update` / `-delete` / `-save` / `-read` / `-graph`。

### 7.2 ProjectActionButton（权限门控）

`features/projects/components/ProjectActionButton`，`action="read" | "write" | "execute" | "manage"`。无权限时渲染**禁用按钮 + `Tooltip` 说明 + 灰度 + `cursor: not-allowed`**，且外层包裹元素显式 `stopPropagation`，避免点击冒泡触发所在卡片或 `Popconfirm`。**规范**

提示文案：`manage` 缺失 → 「仅项目所有者可以操作」；其他 → 「当前角色无此操作权限」。角色标签：`owner 所有者`、`member 普通成员`、`viewer 只读成员`。

### 7.3 图标

两套并存，职责不同：

1. **彩色 SVG（`AppIcon`）**：品牌与功能示意。`shared/icons/registry.ts` 注册 17 项，每项 `{ src, label }`，`label` 是中文回退名；资源在 `shared/icons/assets/`，用 Vite `?url` 导入。`AppIcon` 渲染为 `<img>`，因此**无法继承 `currentColor`**，全部是硬编码多色。新增图标 = 放文件 + 加 `?url` 导入 + 加注册项，`AppIconName` 会做编译期校验。
2. **单色字形（antd 图标）**：界面操作与状态（`PlusOutlined`、`EditOutlined`、`ArrowLeftOutlined` 等），经 `actionRegistry` 收敛。

许可：`shared/icons/licenses/fluent-icons-LICENSE.txt`（MIT，Microsoft）覆盖 Fluent 系 SVG；`gitlab.png` 与 `zentao.ico` 是第三方品牌标识，不在此许可内。**规范**

### 7.4 代码编辑器

| | `JsonEditor` | `TextCodeEditor` |
| --- | --- | --- |
| 定位 | 可编辑 JSON，带工具栏 | 只读为主的内容预览，JSON/YAML |
| 工具栏 | 复制 + 下载（可被 `toolbar`/`toolbarContainer` 替换或注入宿主工具栏） | 无 |
| 特性 | 语法检查、Tab 缩进、失焦自动格式化、`readOnly`、折叠 | `language: 'plain' \| 'json' \| 'yaml' \| 'auto'`（`auto` 按首字符猜 JSON）、非 plain 默认开折叠槽 |
| 命令式接口 | `focus()` / `insertText()` / `formatDocument()` | — |

**规范**：
- 格式化只在合法 JSON 上发生；非法输入原样保留并加 `invalid` 类，绝不吞掉用户输入。`readOnly` 下格式化与失焦处理均为 no-op。
- 主题只能来自 `shared/components/codeEditorTheme.ts`（浅/深两套 + JSON/YAML 两套 highlight），按 `useThemeStore` 的 mode 选择。**禁止在 feature 内自造 CodeMirror 配色**；其中的色值已被 `TextCodeEditor.test.tsx` 断言，改调色板必须同时改测试。

### 7.5 列表表格皮肤

三个模块必须算出完全相同的值（`listSurfaceConsistency.test.ts` 做深度相等断言），实现位置：`features/testing/styles/index.css:2464`（基准）、`app/styles/workbench.css:2106`（需求列表）、`features/ai-testing/styles/index.css:5599`（任务列表）。

| 部位 | 浅色 | 深色 |
| --- | --- | --- |
| 表头高度 / 内距 | 42px / `0 16px` | 同 |
| 表头文字 | `#7b8494` | `rgba(203,213,225,.62)` |
| 表头底色 | `#f7f9fc` | `#1d2432` |
| 表头下边框 | `1px solid #e8ecf2` | `1px solid rgba(148,163,184,.14)` |
| 表头圆角 | 四角 8px + `clip-path: inset(0 round 8px)` | 同 |
| 行高 / 内距 | 48px / `8px 16px` | 同 |
| 行文字 / 底色 | `#697386` / `#fff` | `rgba(226,232,240,.7)` / `#171d29` |
| 行下边框 | `1px solid #edf0f5` | `1px solid rgba(148,163,184,.12)` |
| 悬停行底色 | `#f5f8ff` | `rgba(56,139,253,.12)` |

**`clip-path: inset(0 round 8px)` 是承重声明**（测试会读到它），不是装饰性写法。新增列表模块必须复制整套皮肤并在两种主题下都对齐。

列表名称（可点击链接）深色规格，同样被 `listNameConsistency.test.ts` 跨四个模块断言：`#78aef2`、`cursor: pointer`、`font-size: 13px`、`font-weight: 500`、`line-height: 22px`、`text-underline-offset: 3px`、无下划线；悬停 `#9bc4f5` + `text-decoration: underline`。

### 7.6 状态与标签

- 状态一律用 antd `Tag`，颜色取自 §4.6 的语义预设（深色下不要用 `color` 属性自定义色，会绕过语义表）。
- 迭代状态用图标表达（`.sprint-icon.running`/`.done`）。

### 7.7 空态与加载态

**没有使用 antd `Skeleton`。**统一约定：**用 `Empty` 表达加载中，文案必须是「X加载中...」**。**规范**

| 场景 | 形态 |
| --- | --- |
| 加载中 | `<Empty description="任务加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />`（任务/迭代/用例/测试单/运行记录/Skill 库…） |
| 真为空 | 区分「未配置」与「无数据」：`请先选择项目`、`当前项目下暂无迭代`、`暂无需求`、`当前类型下暂无任务`、`当前还没有运行记录` |
| 空态带 CTA | 主操作放进 `Empty` 的 children：`新建项目`、`创建第一条任务`、`上传第一个 Skill`、`加入用例`、`新建用例` |
| 整页空 | `.workbench-empty` |
| 例外 | 仅 `SprintDetailPage`、`RequirementAnalysisTaskDetailPage` 等少数面板用 `Spin` |

### 7.8 错误态

- 查询级错误：内联 `Alert`，固定形状 `{query.error ? <Alert showIcon type="error" title={getErrorMessage(query.error)} /> : null}`。
- 资源级阻断：`ProjectAccessScope` 包裹，加载中显示 `Spin aria-label="加载项目权限"`，失败显示 `Alert`，`read` 被拒显示 `type="warning"` 的「无法访问此项目」，描述说明项目可能已删除或成员权限已变更。**规范**

### 7.9 全局反馈

非 React 代码（请求层、hook、编辑器回调）通过 `shared/utils/feedback.ts` 的 `message` 门面提示，由 `ThemeProvider` 里的 `FeedbackProvider` 用 `AntdApp.useApp()` 绑定；未绑定就使用会抛错。**不要**在这些位置直接调 antd 的静态 `message`。**规范**

---

## 8. 状态与数据

### 8.1 Zustand 与 TanStack Query 的分工

只有三个 Zustand store：

| Store | 持有 | 持久化 |
| --- | --- | --- |
| `shared/store/theme.store.ts` | `mode` + `setMode`/`toggleMode` | 是，`localStorage['testpilot_theme_mode']`（手写，非 `persist` 中间件） |
| `features/auth/store/auth.store.ts` | `token`、`user`、`setToken`/`setUser`/`logout` | 只持久化 `token`（`localStorage['testpilot_access_token']`）；`user` 故意不持久化，由 `['user']` 查询提供 |
| `features/projects/store/workbench.store.ts` | 当前项目/迭代、项目弹窗开关 | 否，纯内存。`setActiveProjectId` 会级联清空迭代选择 |

两个 `testpilot_*` 存储键为兼容改名前的已登录用户而保留，不要"整理"。**规范**

**分工规则**：Zustand 只放同步的客户端/UI 状态（令牌、主题、当前选择、弹窗），写入来自事件处理器，允许在非 React 代码里同步读取；所有服务端数据都在 Query 里——包括"看起来该放 store"的当前用户与项目权限。**规范**

`features/test-cases/store/` 是空目录，不是 store。**债务**

### 8.2 查询键与失效

- 形状为 `[资源名, ...作用域 id]`，详情用单数、列表用复数：`['apiCollection', id]`、`['apiCases', id]`、`['apiCollectionRuns', id]`、`['sprints', activeProjectId]`、`['projectAccess', id]`、`['requirementsPool', activeProjectId, sprintIds.join(',')]`、`['user']`；provider 家族允许模板串键：`` [`${provider}Connections`, projectId] ``。
- 失效用同前缀批量：`invalidateQueries({ queryKey: ['apiCases', collectionId] })`；需要彻底丢弃时 `removeQueries({ queryKey: ['apiCase', caseId], exact: true })`。
- **查询键与缓存失效由对应 feature hook 管理**，组件不直接操作 `queryClient`。
- `QueryClient` 默认 `retry: 1`、`refetchOnWindowFocus: false`；令牌变化时 `cancelQueries()` + `clear()` 并清空当前项目（"换账号不能继承另一个用户的连接与查询结果"）。
- 轮询是单点状态驱动，不用定时器：`refetchInterval: (query) => 运行中 ? 1500 : false`（集合级 3000ms）；用 `enabled` 做条件，不用条件式 hook。

### 8.3 请求层与错误语义（`shared/api/request.ts`）

- 基址 `import.meta.env.VITE_API_BASE_URL ?? ''`（空即同源）；开发期由 Vite 代理 `/v1` 与 `/__document_preview_proxy`，容器内由 nginx 代理同一前缀。
- 认证：`Authorization: Bearer <token>`，从 `useAuthStore.getState()` 同步读取；有 body 且非 `FormData` 时才加 `Content-Type: application/json`。
- 响应信封 `{ code, message, data }`；`!response.ok || payload.code !== 0` 即失败，抛 `ApiError(message, code, status, data)`。**非 JSON 响应体会被兜底成合法信封**，因此错误提示不会丢。
- `code === 1001 || status === 401` → `logout()`（本层不导航，由路由守卫响应 store 变化）。
- `403` → 派发 `project-permission-denied` 事件（单项目详情读取路径除外），`QueryProvider` 监听后失效 `['projectAccess']` 与 `['projects']`。
- 列表响应归一：`{ items, total }` 变成"同时带 `.items`/`.total` 的数组"，其中 `.items` 是**副本**——自引用会让 React Query 的结构共享比较无限递归。**规范**（`request.test.ts` 断言 `response.items !== response`）
- 下载走 `requestBlob`，带认证不带 `Content-Type`，同样的 401/403 语义，文件名从 `Content-Disposition` 解析（支持 RFC 5987）。
- **没有任何超时与 `AbortSignal`**；取消依靠 Query 的 `enabled` 与卸载，长任务靠服务端 + 轮询。**现状**

### 8.4 值格式化契约

两个函数行为不同，不能互换。**规范**（`value.test.ts` 断言 `prettyPrintValue('"text"') === 'text'`、`formatStructuredContent('"text"') === '"text"'`）

| | `formatStructuredContent` | `prettyPrintValue` |
| --- | --- | --- |
| 定位 | **任务产物**，用户可能要编辑/回写 | 一般只读展示 |
| 字符串输入 | `JSON.parse` 后重新缩进输出，保留引号 | 解析并**脱引号** |
| 空值 | `''` | `''` |
| 失败回退 | `String(value)` | — |

派生规则：判断编辑过的 YAML 是否有改动时用 `formatStructuredContent` 做基准比较。

### 8.5 权限模型

- 角色：`owner` / `member` / `viewer`；能力：`read` / `write` / `execute` / `manage`。
- 两个门控点：`ProjectAccessScope`（页面级资源阻断）与 `ProjectActionButton`（按钮级禁用）。
- 个人授权规则：每次人工执行、阶段推进或重试都使用**当前操作人**的授权；项目共享服务不含个人凭据。

### 8.6 模板函数

`shared/constants/templateFunctions.ts` 暴露两组 token：`builtinTemplateFunctions`（7 项，API 执行器，含 `{{$now}}` RFC3339 与 `{{$timestamp}}`）与 `uiBuiltinTemplateFunctions`（6 项，UI 执行器：无 `$now`，`$date` 为日期精度）。参数格式用 Go 时间布局（如 `2006-01-02`），会原样插入请求体并在服务端求值。

**债务**：UI 组是按位置索引从 API 组拼出来的（`builtinTemplateFunctions[0]/[1]/[4]/[5]/[6]`），插入或重排 API 组会静默改变 UI 组。新增只能**追加**，且要复核索引。

### 8.7 更新载荷

`shared/utils/payload.ts` 提供 `setValueIfChanged` / `setDefinedValueIfChanged` / `setBooleanIfChanged` / `setNormalizedTextIfChanged`；`src/utils/updatePayload.ts` 在其上组合各领域更新体。PATCH 只发送真正变化的字段。**规范**

---

## 9. 主题实现机制

深浅主题同时由五个机制驱动：

1. **`data-theme` 属性**：`ThemeProvider` 同时写到 `<html>` 与 `<body>`；CSS 侧几乎全部按 `:root[data-theme='dark']`（html）匹配，写 `<body>` 的那次实际未被使用。**债务**
2. **antd `ConfigProvider`**：`darkAlgorithm` / `defaultAlgorithm` + §4.3 的 token 覆盖，管辖未被手写 CSS 覆盖的 antd 组件。
3. **各文件自己的 `:root[data-theme='dark']` 块**：主流做法，15 个文件共 620 处。另有 3 处用反向选择器 `:root:not([data-theme='dark'])` 专门限定浅色规则。
4. **`app/styles/dark-polish.css`**：894 行，全部作用于 `:root[data-theme='dark'] .app-shell.app-shell-macos`，是四个工作台模块深色的最终话事人。**它必须在 `App.css` 中最后导入**，文件头注释已写明；它也是唯一持有完整深色语义标签调色板的地方。
5. **`@layer app-buttons`**：全仓唯一的分层。它不是分层体系，而是**特异性逃逸阀**——`buttons.css` 里所有属性都带 `!important`，而分层内的 `!important` 优先于未分层页面的 `!important`，因此无论 feature CSS 以什么顺序注入，都无法把渐变或彩色阴影加回按钮。

样式导入图：

```
main.tsx
├─ 'antd/dist/reset.css'
└─ '@/app/styles/index.css'  →  '@/index.css'          （基础 token + 描述字体白名单）
App.tsx
├─ '@/app/styles/theme.css'  →  '@/App.css'
│     ├─ features/auth/styles/auth.css
│     ├─ app/styles/layout.css
│     ├─ shared/styles/page-frame.css
│     ├─ app/styles/workbench.css
│     ├─ features/api-automation/styles/overview.css
│     ├─ features/ui-automation/styles/index.css
│     ├─ features/api-automation/styles/detail.css
│     ├─ features/base-services/styles/index.css
│     └─ app/styles/dark-polish.css                     ← 必须保持最后
└─ ThemeProvider  →  '@/app/styles/buttons.css'          （唯一 @layer）
```

`ai-testing` / `testing` / `test-cases` / `test-orders` 的样式是**组件级导入**（在页面文件顶部 `import .../styles/index.css`），因此它们的层叠顺序取决于打包器与运行时机——这正是 `dark-polish.css` 要求置尾、`buttons.css` 使用 `@layer` 的原因。**规范**：新增全局生效的样式要放进 `App.css` 的聚合链；只在单个 feature 内生效的样式按组件级导入，并自带深色对照。

---

## 10. 可执行的样式契约

以下测试直接锁定了本文件的规范条目，`npm run test` 会失败而不是"风格提醒"：

| 测试 | 锁定内容 |
| --- | --- |
| `app/styles/listSurfaceConsistency.test.ts` | 功能测试列表为基准；需求列表与测试设计任务列表在**两种主题**下的表头/行指纹（底色、高度、内距、`clip-path`、四个角半径）必须与之**完全相等**；基准表头四角必须是 `8px` |
| `app/styles/listNameConsistency.test.ts` | API 测试集 / UI 测试集 / 功能测试集 / 需求的名称，在深色下的 `color`/`cursor`/`font-size`/`font-weight`/`line-height`/`text-underline-offset` 必须与测试设计任务名称**完全相等** |
| `app/styles/darkSemanticTags.test.ts` | 16 个语义标签预设（含别名组）的深色前景/背景对 |
| `app/styles/darkSidebarTheme.test.ts` | 深色品牌区必须使用与侧栏/页头一致的固定画布色 `#0d1117` |
| `features/ai-testing/styles/taskListDarkTheme.test.ts`、`runResultModalLayout.test.ts`、`features/api-automation/styles/detailDarkTheme.test.ts`、`features/ui-automation/styles/darkEditorStyles.test.ts`、`features/requirements/components/RequirementDocumentPreviewModal.dark-theme.test.ts` | 各模块自身的深色与布局断言 |
| `shared/components/TextCodeEditor.test.tsx` | 编辑器高亮色值 |
| `shared/components/ActionButton/ActionButton.test.tsx`、`features/projects/components/ProjectActionButton.test.tsx` | 默认文案、`iconOnly` 可访问名、禁用/加载吞点击、删除需二次确认且只触发一次、无权限时不打开外层确认框 |

这些测试用 `?raw` 导入 CSS、注入 jsdom、设置 `document.documentElement.dataset.theme` 后读 `getComputedStyle`，断言的是**计算值**。因此改动共享皮肤时必须先跑它们。

---

## 11. 新增页面检查清单

1. 路由加在 `AppShell` 的嵌套 `<Routes>`，而不是 `app/router/routes.tsx`；同时确认侧栏高亮键的折叠逻辑。
2. 根节点用 `.workbench-page` + feature 类名，继承"外层不滚、内容自滚"的模型。
3. 选择列表页骨架（§3.5）或双栏/任务详情骨架（§3.6、§3.7），不要自创第三种。
4. 页面不渲染项目/迭代选择器，改从 `useActiveProject` / `useActiveSprint` 读。
5. 主操作与危险操作用 `ActionButton` / `ProjectActionButton`，传 `operation` 而非 `icon`；`iconOnly` 必须配 `aria-label`。
6. 列表如用表格，复制 §7.5 的整套皮肤（含 `clip-path`），并在两种主题下各写一份。
7. 加载态用「X加载中...」`Empty`，空态区分未配置与无数据，能带 CTA 就带；错误用内联 `Alert` + `getErrorMessage`。
8. 所有可见文案中文；交互控件有中文可访问名。
9. 新 token 用 `<feature>-*` 家族写在 feature 自己的 CSS 里，同文件给出 `:root[data-theme='dark']` 对照；不要往 `dark-polish.css` 里加（该文件只服务聚合链上必须置尾的外壳样式）。
10. 编辑器只用 `JsonEditor` / `TextCodeEditor`，配色只用 `codeEditorTheme.ts`。
11. 服务端数据走 Query，键按 §8.2 命名，失效交给对应 hook。
12. 跑 `npm run verify`（type-check + lint + build）与 `npm run test`。

---

## 12. 已知债务与收敛建议

按影响面排序，供后续迭代处理：

1. **按钮的失效重绘规则（影响最大，也最容易误导）。** `@layer app-buttons` 让下列规则全部不生效：`layout.css:197` 的实心蓝 `#006ef2`；`workbench.css:1417` 与 `2288` 的 `linear-gradient(180deg,#2f9bff,…)` + `border-radius: 10px` + 彩色阴影；`base-services/styles/index.css:1033/1067`；`testing/styles/index.css:1325`；`api-automation/styles/detail.css:3688`（深色薄荷渐变）；`api-automation/styles/overview.css` 的 `--tp-action-*` 五色 action 体系。**建议**：要么删除这些规则让意图唯一，要么在 `buttons.css` 顶部再写一段说明；否则下一个人会照着"改这里有反应"的假设继续加代码。
2. **深色画布三套并存**：`#0d1117`（GitHub dark / `--mac-dark-canvas` / `--github-dark-*`）、`#171b26`（`--app-bg` / `--tp-bg` / antd `bodyBg`）、`#191d27`（antd `colorBgBase`）。**建议**：确定唯一画布值，把另外两处改成别名。
3. **`--mac-dark-*` 与 `--github-dark-*` 重复且数值不一致**（panel `.78` vs `.86`、card `.72` vs `.78`、border `.86` vs `.9`），作用于同一选择器，胜负由导入顺序决定。**建议**：合并为一套。
4. **三个文件完全没有深色规则**：`shared/styles/page-frame.css`（1443 行，且硬编码 `#181b23`/`#5a6170`/`#fff`）、`features/test-orders/styles/index.css`（905 行）、`features/ui-automation/styles/index.css`（1018 行）。另有若干 AI 子组件的 CSS 同样只有浅色。**建议**：按 §4.5 补 `<feature>-*` 深色家族，并加断言测试防回归。
5. **`--tp-*` 家族被拆到三个文件**：浅色在 `workbench.css:612`、action 色在 `api-automation/styles/overview.css`（无深色对照）、深色在 `api-automation/styles/detail.css:2899`。**建议**：并入一个文件并补齐两种主题。
6. **`page-frame.css` 名实不符**：文件名提示"通用页面框架"，实际主要是迭代看板样式（约 70 个 `sprint-*` 类）。**建议**：改名或在文件头注明职责。
7. **表头/行的重复定义未收口**：`workbench.css:575` 的 `padding-top/bottom: 10px` 与 §7.5 的 `8px 16px` 并存；`panel-header` 与 `workbench-project-toolbar` 各有新旧两套尺寸（64px/16px 20px vs 48px/8px 14px），当前由后导入者胜出。**建议**：删除旧的一套。
8. **`page-frame.css` / `ui-automation` / `test-orders` 硬编码色值**（`#1677ff`、`#727786`、`#181b23` 等）没有 token 化，无法随主题切换。**建议**：逐步替换为 `--app-*` / `--<feature>-*`。
9. **布局 token 缺失**：没有 `--radius-*`、`--space-*`、`--shadow-*`、`--font-size-*`，圆角与间距全部硬编码（圆角有 15 种取值、间距有 `10px` 半步）。**建议**：若要做收敛，先定圆角三档与间距四档，再逐文件替换。
10. **`--description-font` 白名单重复书写**：同一批类名与 textarea 选择器在正文、placeholder、深色覆盖三处各写一遍。**建议**：抽出共享选择器列表，或改为按属性/数据属性匹配。
11. **模板函数的位置索引耦合**（§8.6）：`uiBuiltinTemplateFunctions` 依赖 `builtinTemplateFunctions` 的下标。**建议**：改为显式引用具名条目或独立声明。
12. **`features/test-cases/store/` 空目录**、`JsonEditor` 内部重复实现了 `saveBlob` 的下载逻辑、`data-theme` 写 `<body>` 无人使用——零散清理项。

---

## 附：常用校验命令

在 `apps/studio/` 下：

```sh
npm run type-check    # tsc -b --pretty false
npm run lint          # eslint .
npm run test          # vitest run（含本文 §10 的全部样式契约）
npm run build         # tsc -b && vite build
npm run verify        # type-check + lint + build
```
