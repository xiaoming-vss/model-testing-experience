# Studio CSS 存量整改总清单

> 2026-11-18。阶段 0–45 已执行完成。本文件是整改台账与后续维护基线。它覆盖 `apps/studio/src/**/*.css` 当前全部 **40 个文件**，不是单模块建议。阶段 29 前的 66 文件基线仍保留在下方表格的“阶段 29 前”口径中。
>
> 数据口径：`scripts/check-css-budget.mjs`、`scripts/check-css-structure.mjs` 与逐文件静态分类脚本。“布局”指 `display/flex/grid/gap/padding/margin/size/overflow` 等结构声明；“皮肤”指颜色、字体、边框、圆角、阴影、动效等声明；“深层规则”指带后代选择器、`:global(...)` 或组件内部 DOM 的规则。数字用于排序，不替代浏览器验收。

## 一、总账与达标缺口

| 指标 | 当前 | 目标 | 缺口 |
| --- | ---: | ---: | ---: |
| CSS 文件 | 40 | ≤ 45 | 已达标（余 5 个） |
| CSS 行数 | 6,738 | ≤ 9,000 | 已达标（余 2,256 行） |
| `!important` | 49 | ≤ 100 | 已达标（余 51 处） |
| 长前缀 | 0 | 0 | 已达标 |
| 重复规则体 | 5 | ≤ 60 | 已达标 |
| 单文件 > 600 行 | 0 | 0 | 已达标 |
| 布局声明 | 1,162 | 只降不升 | 已 ratchet |

**先看结论，避免继续“一个模块一个模块”地漏：**

1. **文件数、行数、`!important`、长前缀与重复体均已达标。** 49 处 `!important` 中 31 处在按钮调色板，5 处在主题覆盖，6 处在页签动效，其余 7 处分布在外壳、输入与分页契约；页面 Module 已无 `!important`。
2. **阶段 37 完成了第一轮全局契约收缩。** 把 `list-name` 并入 `list-table`、`table-row-dividers` 并入 `theme.css`，删除已无消费方的 `api-collection-*` / `sprint-card-*` 规则，并把页面工具栏、快速过滤条、API/性能工具栏与 Shell 重复块迁入 utility 或合并；16 个文件 2,469 → 14 个 2,022 行。阶段 43 又移除了 `list-table` 的 23 处与页面板面的 10 处 `!important`。
3. **当前底座占 21 个文件 / 3,587 行：**
   - 7 个 token 文件：1,828 行；
   - 14 个全局契约：1,759 行。
4. 其余 **19 个页面/共享组件 Module（3,157 行）** 已低于阶段 37 前的文件与行数上限；阶段 39 删除右栏卡片与测试单可视化，阶段 40 迁移测试单工作台、Bug、接口库、Sprint 概览与账户样式，阶段 41 删除禅道绑定与侧栏导航两个 CSS 文件，阶段 45 把页脚、页签、滚动承载层、表尾、Logo 与外壳头部残留布局迁入 utility。
5. 5 组重复规则体已在目标内，且多为跨页面同构皮肤；阶段 43 未为了清零合并语义不同的选择器。完整列表见附录 B。
6. **阶段 45 收口复核。** 全量 189 个测试文件 / 947 个用例、`npm run verify`、CSS 三件套与 `git diff --check` 通过；两个基线 ratchet 后为 40 文件 / 6,738 行 / 49 处 `!important` / 5 组重复体 / 1,162 条布局声明。普通页脚、工作台页签、滚动承载层与 SVG Logo 不再由 CSS 布局规则承担。

## 二、动作分类

| 动作 | 含义 | 文件数 | 行数 |
| --- | --- | ---: | ---: |
| **A** | 删除或并入宿主 Module 的确定候选；先迁 utility，再删文件 | 0 | 0 |
| **B** | 页面/共享组件 Module；按页面族迁移，能删则删，否则只留深层皮肤 | 19 | 3,157 |
| **C** | 全局契约；只做死规则、层叠和重复体收缩，不整体 utility 化 | 14 | 1,759 |
| **D** | Token / 主题 / Tailwind 层；保留，只清理无消费者 token | 7 | 1,828 |

> A 类已清零。B 类剩余文件只保留 AntD / React Flow / CodeMirror / DOCX 深层结构、状态、动效与页面高度链；阶段 41 已将侧栏导航迁入 utility 并删除 `sidebar.css`。

### A 类：已完成（0 个文件）

`shared/styles/base-services-connection.module.css`（195）、`shared/styles/case-import.module.css`（63）、`shared/styles/legacy-surface.css`（102）已随阶段 36 删除；`entity-card.css`、`json-editor.module.css` 也已并入共享 utility / 富文本编辑器深层样式。

### C 类：14 个全局契约（2,022 行）

`app/styles/*` 8 个、`index.css`、`shared/styles/` 下的 `list-table`、`pagination`、`surface-tokens`、`tab-motion`、`scrollbars`。这些规则服务于多个页面，且多数是在压 AntD/旧层叠；只允许在完整浏览器对照下删死规则、合并同体规则、减少可替代的 `!important`。**不要把这些文件当页面 Module 迁走。**

### D 类：7 个 Token 文件（1,847 行）

`chart-tokens`、`foundation-tokens`、`github-dark-foundation`、`github-dark-tokens`、`indigo-amber-light-tokens`、`ui-stage-visual-tokens`、`tailwind`。它们不产生页面布局，不参与文件数削减；只做“无消费者 token”清理。文件数目标必须从 A/B 里出，不能靠删 token 凑数。

## 三、完整文件清单

> 当前 **40 个文件**全部列入；权威行数与布局声明由 `apps/studio/scripts/css-structure-budget.json` 维护，本表随阶段收口更新。A 类已清零，B/C/D 分类见下。

### B 类：页面/共享组件 Module（19 个 / 3,120 行）

| 文件 | 行 | `!important` |
| --- | ---: | ---: |
| `features/ai-testing/styles/generation-chain.module.css` | 337 | 0 |
| `features/ui-automation/styles/ui-detail-shell.module.css` | 302 | 0 |
| `features/ai-testing/styles/ai-task-detail.module.css` | 282 | 0 |
| `features/ai-testing/styles/artifact-cases.module.css` | 247 | 0 |
| `features/api-automation/styles/api-detail-shell.module.css` | 230 | 0 |
| `features/ai-testing/styles/generation-canvas.module.css` | 220 | 0 |
| `features/requirements/styles/requirement-detail.module.css` | 160 | 0 |
| `features/ui-automation/styles/ui-suite.module.css` | 157 | 0 |
| `shared/styles/account.module.css` | 148 | 0 |
| `features/ai-testing/styles/ui-stage-visual.module.css` | 143 | 0 |
| `features/projects/styles/sprint-overview.module.css` | 138 | 0 |
| `features/test-cases/styles/case-library.module.css` | 134 | 0 |
| `features/bugs/styles/bugs.module.css` | 132 | 0 |
| `shared/styles/run-view.module.css` | 119 | 0 |
| `features/interface-library/styles/interface-detail.module.css` | 99 | 0 |
| `features/interface-library/styles/interface-library.module.css` | 80 | 0 |
| `features/projects/styles/environment-drawer.module.css` | 76 | 0 |
| `features/api-automation/styles/api-detail-rules.module.css` | 59 | 0 |
| `features/test-orders/styles/test-order-workspace.module.css` | 57 | 0 |

### C 类：全局契约（14 个 / 2,048 行）

| 文件 | 行 | `!important` |
| --- | ---: | ---: |
| `shared/styles/surface-tokens.css` | 391 | 0 |
| `app/styles/shell.css` | 379 | 3 |
| `app/styles/buttons.css` | 203 | 31 |
| `app/styles/shell-header.css` | 190 | 0 |
| `shared/components/RichTextEditor/rich-text-editor.css` | 184 | 0 |
| `shared/styles/list-table.css` | 172 | 0 |
| `app/styles/layout.css` | 143 | 1 |
| `index.css` | 95 | 2 |
| `shared/styles/pagination.css` | 87 | 1 |
| `app/styles/antd-overrides.css` | 60 | 0 |
| `app/styles/action-buttons.css` | 50 | 0 |
| `shared/styles/tab-motion.css` | 33 | 6 |
| `app/styles/theme.css` | 32 | 5 |
| `shared/styles/scrollbars.css` | 29 | 0 |

### D 类：Token / 主题 / Tailwind 层（7 个 / 1,828 行）

| 文件 | 行 | `!important` |
| --- | ---: | ---: |
| `shared/styles/foundation-tokens.css` | 569 | 0 |
| `shared/styles/github-dark-foundation.css` | 522 | 0 |
| `shared/styles/indigo-amber-light-tokens.css` | 323 | 0 |
| `shared/styles/github-dark-tokens.css` | 227 | 0 |
| `shared/styles/ui-stage-visual-tokens.css` | 89 | 0 |
| `shared/styles/chart-tokens.css` | 50 | 0 |
| `shared/styles/tailwind.css` | 48 | 0 |

> 剩余文件的规则均为 AntD / React Flow / CodeMirror / DOCX 深层结构、状态、动效或页面高度链；普通页面布局不再回流。
## 四、阶段排期（29–38）

> 每个阶段覆盖一个完整页面族，不再“今天只做一个模块”。阶段内的子批只用于控制验证范围，不改变该阶段必须覆盖的文件全集。

| 阶段 | 范围 | 当前 | 达标线 | 文件目标 | 核心动作 | 风险 |
| --- | --- | ---: | ---: | :---: | --- | --- |
| 29 | UI 自动化全部 5 个 Module | 1,959 | ≤ 650 | 5 → 3 | **已完成（546 行）**：测试集/步骤编辑器、执行流水线、检查器、详情壳、顶栏一次排完；顶栏与流程深层规则并入详情壳；保留回放/控制台/React Flow 深层皮肤 | 中 |
| 30 | API 自动化全部 4 个 Module | 1,466 | ≤ 450 | 4 → 2 | **已完成（336 行）**：删除 `api-list` 与 `api-detail-request`；列表、详情、请求面板、环境弹层与后置操作迁 utility；保留 AntD/CodeMirror 深层规则 | 中 |
| 31 | 测试单全部 5 个 Module | 1,154 | ≤ 350 | 5 → 2 | **已完成（329 行）**：删除图谱/列表/图谱执行 Module；执行视图并入工作台；列表、工作台骨架、图谱壳与判定区迁 utility；保留可视化容器查询与 AntD 表格深层规则 | 中高 |
| 32 | 接口库全部 3 个 Module | 1,550 | ≤ 550 | 3 → 2 | **已完成（238 行）**：列表/树/抽屉、详情、编辑器面板、键值表与 OpenAPI 导入流程迁 utility；删除编辑器 Module，AntD 深层规则并入详情 | 低–中 |
| 33 | AI 测试/生成链全部 10 个 Module | 3,759 | ≤ 1,450 | 10 → 5 | **已完成（1,449 行）**：三个产物 Module 与关系/UI 生成并入宿主；画布、生成链、阶段可视化、任务详情全量迁 utility；删除 `ai-page`、`artifact-api`、`artifact-misc`、`relations`、`ui-generation` | 高 |
| 34 | 用例 / Bug / 需求 3 个 Module | 1,465 | ≤ 650 | 3 → 3 | **已完成（527 行）**：表格、筛选、详情、活动流、表单骨架、文档预览布局迁 utility；保留 AntD / DOCX 深层结构与高度链 | 高 |
| 35 | 基础服务 / Auth / 个人设置 / Projects 6 个 Module | 1,142 | ≤ 450 | 6 → 4 | **已完成（449 行）**：登录/个人设置合并为共享 `account` Module，删除 `profile-settings`；项目概览并入 Sprint 看板，删除 `projects-overview`；环境抽屉、动态值选择与禅道绑定只留 AntD 深层规则 | 中 |
| 36 | 共享组件 7 个文件 | 1,448 | ≤ 450 | 7 → 2 | **已完成（304 行）**：基础服务连接、导入弹窗、实体卡片、遗留表面与 JSON 编辑器 Module 删除，布局/皮肤进共享 utility；保留富文本与运行报告深层结构 | 高 |
| 37 | 全局契约 16 个文件 | 2,469 | ≤ 2,100 | 16 → 14 | **已完成（2,022 行）**：`list-name` 并入 `list-table`、`table-row-dividers` 并入 `theme.css`；删除无消费方 API/卡片规则，合并 Shell 重复块，页面工具栏/快速过滤/API 工具栏迁 utility；`!important` 95 → 93 | 高 |
| 38 | 收口 | — | ≤ 9,000 / ≤ 45 | 44 | **已完成**：全量 187 个测试文件 / 942 个用例、`npm run verify`、CSS 三件套与 `git diff --check` 通过；两个基线 ratchet 未回退；D 类 token 审计未发现需删除的孤儿族，保留调色板契约 | 低 |

**目标校验**：阶段 29–37 的 8,047 行 / 44 文件是预算收口口径；阶段 39–45 再删除 4 个文件并收缩深层规则，最终为 **40 个文件 / 6,738 行 / 49 处 `!important` / 5 组重复体 / 1,162 条布局声明**，全部低于 ≤7,000 / ≤41 / ≤50 目标。阶段 38、阶段 44 与阶段 45 的复测和基线 ratchet 均已完成，指标未回退。

### 各阶段完成口径

每个阶段结束必须同时满足：

- 该阶段列出的每个文件都已处理：删除、并入或缩到只剩深层皮肤；不能留“下阶段再说”的页面类规则。
- `npx tsc --noEmit -p tsconfig.app.json`、全量 `npm test`、`npm run verify`、CSS 三件套、`git diff --check` 通过。
- 浏览器按 1280 / 900 / 760、浅色 / 深色核对页面族；表格、弹窗、Drawer、空态、长文本、页面切换残留覆盖都要看。
- `node scripts/check-css-structure.mjs --update` 只 ratchet 已完成的下降；不得为了过关放宽文件/行数/规则数上限。
- 更新 `docs/studio/css-migration-plan.md` 的阶段状态和指标表，并保留本文作为全量台账。

## 五、`!important` 全量清单

当前 49 处，分布在 7 个文件；页面 Module 已无 `!important`。风险集中在按钮调色板与主题/动效覆盖：

| 文件 | 数量 | 风险点 |
| --- | ---: | --- |
| `app/styles/buttons.css` | 31 | AntD 按钮所有状态；反向压制基础按钮层与 portal 覆盖 |
| `shared/styles/tab-motion.css` | 6 | Tab 指示器透明与动效关闭 |
| `app/styles/theme.css` | 5 | 浅色主题控件表面与全局行分隔线 |
| `app/styles/shell.css` | 3 | 紧凑头部、表格单元格伪元素与 mac 玻璃文字 |
| `index.css` | 2 | 描述文字颜色 |
| `shared/styles/pagination.css` | 1 | 表格页脚背景 |
| `app/styles/layout.css` | 1 | 布局链接强调色 |

完整分类与保留理由见附录 A。处理原则：

- 先确认是否有同权重替代规则或 `@layer` 可覆盖；只有确认无替代才保留 `!important`。
- 全局按钮/主题契约一次只动一个文件，并用 computed style 对比，不允许“批量去 `!important`”。
- 阶段 43 已把表格、页面板面与滚动区内距的 39 处移除；剩余 49 处均通过列表/板面契约测试与浏览器计算样式复核。

## 六、重复规则体（5 组）

结构门禁当前 5 组，已在 ≤60 目标内。它们是跨页面的 `display:none`、`font-size`、`width:100%`、`margin:0`、`flex:0 0 auto`、`min-width:0` 等单属性皮肤/布局规则：

- 权威列表由 `apps/studio/scripts/css-structure-budget.json` 的 `duplicateBodies` 维护，门禁按哈希与计数 ratchet。
- 不为了把 5 降到 0 合并语义不同的选择器；页面批次中只有同一宿主/同一 utility 能表达时才合并。
- 阶段 43 后剩余组均为跨 feature 的状态/表面单属性，保留。

## 七、附录

### 附录 A：`!important` 保留清单（49 处）

| 文件 | 数量 | 保留理由 |
| --- | ---: | --- |
| `app/styles/buttons.css` | 31 | 按钮调色板在 `@layer app-buttons` 内，需要压过未分层页面/portal 覆盖；含调色、悬停/禁用、图标动作尺寸与焦点环 |
| `app/styles/theme.css` | 5 | 浅色/深色主题对顶栏、输入与列表分隔线的最终覆盖 |
| `shared/styles/tab-motion.css` | 6 | 共享页签指示器与 Segmented 的透明背景/禁用过渡 |
| `app/styles/shell.css` | 3 | 紧凑头部内距、表格分隔伪元素与 mac 玻璃文字 |
| `index.css` | 2 | 描述正文的只读排版颜色 |
| `shared/styles/pagination.css` | 1 | 浅色页脚背景覆盖 |
| `app/styles/layout.css` | 1 | 布局链接的强调色 |

### 附录 B：重复规则体

阶段 43 后 5 组重复体全部是跨 feature 的同构单属性。成员选择器与哈希由 `css-structure-budget.json` 的 `duplicateBodies` 维护；本文不再复制易失效的选择器清单。修改样式后运行 `node scripts/check-css-structure.mjs`，计数上升会在门禁中失败。

## 八、执行顺序建议

1. **阶段 29–45（UI / API 自动化、测试单、接口库、AI 测试/生成链、用例/Bug/需求、基础服务/Auth/Projects、共享组件、全局契约、结构整改与收口）已完成**，当前 40 文件 / 6,738 行。
2. **阶段 38 收口、阶段 44 最终收口与阶段 45 残留布局清理均已完成**：全量复测、基线 ratchet、D 类 token 审计与 `--legacy-*` 清理；未批量删除调色板 token。
3. **最终目标已达成**：40 ≤ 41 文件、6,738 ≤ 7,000 行、49 ≤ 50 处 `!important`、0 长前缀、5 ≤ 60 组重复体、1,162 条布局声明；后续只允许向下 ratchet。

## 九、完成与未完成记录

> 2026-11-18 收口时点的边界记录。后续新计划从这里开始，不重复已完成项。

### 已完成

- **阶段 0–45 全部执行完成**：包括页面族整族迁移、全局契约收缩、共享组件迁移、结构性整改、残留布局清理、收口复测与基线 ratchet。
- **页面级 Tailwind 化**：UI / API 自动化、测试单、接口库、AI 测试/生成链、用例/Bug/需求、基础服务/Auth/个人设置/Projects、共享组件与顶部导航的布局、间距、排版与响应式排布已迁入 utility。
- **结构收缩**：从阶段 29 前的 66 个文件压到 40 个；阶段 39–41 删除 `ui-detail-inspector`、`test-order-visualization`、`zentao-binding`、`sidebar` 四个文件，`list-name` 并入 `list-table`，`table-row-dividers` 并入 `theme.css`，Shell/工具栏/按钮重复块已合并或 utility 化。
- **最终指标**：40 个文件 / 6,738 行 / 49 处 `!important` / 0 长前缀 / 5 组重复规则体 / 1,162 条布局声明 / 0 个超过 600 行的文件。
- **验证**：全量 189 个测试文件 / 947 个用例、`npm run verify`、CSS 三件套与 `git diff --check` 通过；阶段 29–45 已按各阶段记录完成对应页面与断点的浏览器核对；两个基线已 ratchet 且无回退。
- **Token 审计**：28 个 `--legacy-*` 别名已内联删除；无消费者的动作、详情玻璃、AI 折叠、项目概览与 scope 标记 token 已清理；剩余调色板 token 作为设计系统资产保留。

### 阶段 39 已完成（2026-11-18）

- **度量**：结构门禁新增 `layoutDeclarations`；全量布局声明 1,893 → 1,530（−363）。
- **迁移**：删除 `ui-detail-inspector.module.css`（71 行，右栏卡片抽为 `shared/components/RunCard.tsx`）与 `test-order-visualization.module.css`（119 行，面板/步骤/关系图迁 utility，容器查询改用 Tailwind 变体）；`api-detail-rules` 105 → 65；`ui-stage-visual` 217 → 156，浅色规则迁 `uiStageVisualClasses.ts`。
- **指标**：44 → 42 文件，8,047 → 7,756 行；`!important` 93、长前缀 0、10 组重复体、0 个超过 600 行的文件。
- **验证**：`npm run verify`、CSS 三件套、`git diff --check` 通过；当时全量 188 个测试文件 / 946 个用例通过（阶段 38 基线为 187/942）；UI 自动化、测试单可视化、API 自动化、AI 阶段可视化与运行报告定向测试通过。
- **浏览器核对**：当前 `perf-e2e-1794842106` 项目无 UI/API 测试数据，`Zata-Platform` 无项目权限；列表与空态可打开，详情/回放/图谱需真实数据，留阶段 42 补齐，未伪造验收。

### 阶段 40 已完成（2026-11-18）

- **页面布局迁移**：`test-order-workspace.module.css` 210 → 57（工具栏、条目表、侧翻页、底部判定条迁 utility，保留高度链与 AntD 深层规则）；`bugs.module.css` 213 → 133（详情栏、证据预览、描述模板迁 utility，保留 Modal/上传/导入与伪元素）；`interface-library.module.css` 138 → 84（页面内距与 HTTP 方法签迁 utility，抽共享 `shared/components/MethodBadge.tsx`，保留 Tree/Table 深层规则）；`sprint-overview.module.css` 164 → 154（进度/严重度子项迁 utility）；`account.module.css` 151 → 149（标题色迁 utility）。
- **指标**：42 文件，7,756 → 7,457 行（−299）；布局声明 1,530 → 1,464；重复规则体 10 → 9；`!important` 93、长前缀 0、0 个超过 600 行的文件。
- **验证**：`npm run verify`、当时全量 188 个测试文件 / 946 个用例、CSS 三件套与 `git diff --check` 通过；接口库 45 项、项目/认证 54 项定向测试通过。
- **测试调整**：登录页标题由 CSS Module 改为 utility 后，jsdom 无法计算 Tailwind 类，断言从 computed style 改为类名契约；`--app-auth-text` token 仍由 foundation token 测试保护。

### 阶段 41 已完成（2026-11-18）

- **共享板面契约**：`shell-header.css` 新增 `.workbench-panel-flat`，在 macOS 外壳内以更高优先级压平玻璃底；UI 测试集、性能、Bug、API、UI、用例库、测试单条目与 Sprint 详情统一追加该标记类，删除两份页面级 `!important` 复位块（10 处）与 `surface-tokens` 的 5 处 `tp-list-panel` `!important`。
- **文件合并/删除**：禅道绑定弹窗改用 AntD `styles` 语义槽与 utility，删除 `zentao-binding.module.css`（59 行）；顶部导航整体迁入 `AppSidebar` / `TopNavTabMenu` / `SidebarIcon` 的 utility，删除 `sidebar.css`（110 行）。`RunCard` 与 `MethodBadge` 成为共享原语。
- **深层规则收缩**：生成链状态胶囊与节点几何抽为 `generationClasses.ts` / 画布 utility；继续优化侧栏、产物视图切换、API 接口选择器、仓库画像网格与需求文档工具栏迁 utility；`generation-chain` 426 → 337、`generation-canvas` 256 → 220、`artifact-cases` 255 → 247、`requirement-detail` 179 → 160、`ui-stage-visual` 156 → 143。
- **指标**：42 → 40 文件，7,457 → 6,996 行；`!important` 93 → 49；重复规则体 9 → 5；布局声明 1,464 → 1,248。
- **验证**：AI 测试/需求 51 个测试文件 / 279 个用例通过；全量测试最终 189 文件 / 947 用例；`npm run verify`、CSS 三件套与 `git diff --check` 通过。

### 阶段 42 已完成可执行范围（2026-11-18）

- **真实数据核对**：在 `perf-e2e-1794842106` 本地项目创建迭代「CSS 视觉核对」，核对 Sprint 详情页（1280 深色）：健康摘要、执行进度、测试执行概览正常，`.sprint-overview-panel-unified` 计算样式为 `border 0 / radius 0 / transparent / no shadow / no backdrop`，页面无横向溢出。
- **列表与外壳**：1280 / 760 深色与 1280 浅色核对顶部导航、资产库用例列表、测试单空态；导航指示器、活动项、窄屏间距与 `workbench-panel-flat` 均符合预期，`scrollWidth === clientWidth`。
- **计算样式基线**：列表表格注入探针在移除 23 处 `!important` 前后，表头/单元格的 height、padding、border、radius、color、background 完全一致；新增 `shellSurfaceConsistency.test.ts` 锁定 flat 板面契约。
- **未覆盖范围**：运行报告、测试单图谱执行、AI 生成链真实产物、需求 DOCX 预览仍缺真实运行记录/AI 服务/文档样本，未做浏览器验收；对应组件测试、类型检查与构建通过。该缺口保留，不用单元测试冒充视觉验收。

### 阶段 43 已完成（2026-11-18）

- **`!important` 收缩**：`list-table.css` 23 → 0（表头/行/悬停/圆角/伪元素），页面板面复位 10 → 0，`tp-list-panel` 5 → 0，`tp-list-scroll` 1 → 0；总数 93 → 49。
- **保留理由**：31 处按钮调色板仍在 `@layer app-buttons` 内，需要压过未分层页面/portal 覆盖；主题 5、页签动效 6、外壳 3、输入 2、分页 1、布局 1 均依赖级联顺序或 AntD 内部状态，逐条核对后保留。
- **测试**：`listSurfaceConsistency.test.ts`、`listPanelConsistency.test.ts` 在无 `!important` 下通过；新增 `shellSurfaceConsistency.test.ts`；浏览器计算样式复测一致。
- **未追数字**：未继续强删按钮 `!important` 以冲击 ≤30；剩余项需要跨全部 portal 的视觉基线，保留比机械删除更安全。

### 阶段 44 已完成（2026-11-18）

- **`--legacy-*` 清零**：28 个别名全部内联到消费者 token（`--tp-*`、`--mac-glass-*`、`--project-overview-*`、`--mac-action-blue-border`），删除 `shell.css`、`shell-header.css`、`sprint-overview.module.css`、`action-buttons.css` 中的别名层；主题文件中同名 token 直接定义。
- **无消费者 token**：删除 `--tp-action-*`（15）、未使用的 `--detail-glass-*`（5）、`--ai-fold-*` / `--ai-card-*` / `--ai-popover-arrow`（11）、项目概览未消费 token（18）、`--uisv-6b7f9e`、运行报告未消费变量；页面 scope 标记变量（14）一并清理。
- **阶段 44 指标**：40 个文件 / 6,996 行 / 49 处 `!important` / 0 长前缀 / 5 组重复规则体 / 1,248 条布局声明 / 0 个超过 600 行的文件。
- **交付状态**：`origin/dev` 已推进到 `13a29dd`（阶段 39 与性能改动已推送）；阶段 40–45 改动（含本文档）仍在工作树，尚未提交。

### 阶段 45 已完成（2026-11-18）

- **页脚与列表残留**：`pagination.css` 的 `.table-footer` 布局迁入 `shared/utils/surfaceClasses.ts` 的 `tableFooterClass` / `tableFooterCompactClass`，19 处列表/抽屉/弹窗/选择器页脚统一追加；`list-table.css` 的操作列标题、名称列宽度与动作列对齐迁到列 render 的 utility；`test-order-workspace`、`bugs`、`ui-suite`、`performance`、`account` 等页脚保持 58px / 12×16 内距。
- **页签与滚动承载**：`shell.css` 的 `.workbench-tabs` 与 `.table-body-scroll` 布局迁入 `workbenchTabsClass` / `workbenchTabsCompactClass` / `workbenchTabsAiClass` 与 `tableScrollClass`，Projects、Sprint、AI Skill 库、用例库、Bug、性能、基础服务、环境抽屉与 UI 测试集分别按原内距接管；Sprint 与 AI Skill 库的页面级 padding 覆盖规则删除。
- **外壳头部去重**：项目选择器、顶栏导航、反馈入口、头部动作区与 `app-header-main` 的布局迁到 `AppShell` / `AppSidebar` utility；`shell.css` 与 `shell-header.css` 删除重复块，`shell-header.css` 只保留 macOS 玻璃皮肤、项目选择器尺寸与 900px 以下高度回退。
- **页面根与 Logo**：接口库三页的页面间距迁到 `interfacePageRootClass`，仅保留 760px 高度链；API 详情删除与 `surface-tokens` 重复的 `.api-automation-content` 高度/内距覆盖，`--detail-glass-border` 移到 `.scope`；`MtxLogo` 的描边与投影改为 SVG 属性 + utility，`layout.css` 删除 5 条 Logo 规则与未使用的 `.brand`。
- **指标**：6,996 → 6,738 行（−258）；布局声明 1,248 → 1,162（−86）；文件数 40、`!important` 49、长前缀 0、重复体 5 不变；结构基线已 ratchet 到 4,529 条声明 / 1,162 条布局声明。
- **验证**：全量 189 个测试文件 / 947 个用例、`npm run verify`、CSS 三件套与 `git diff --check` 通过；浏览器核对 1280 深/浅色、900、760 下的顶部导航、Sprint 详情、Bug 列表、用例库、UI 测试列表、性能运行记录、账号管理与接口库空态，页脚与头部计算样式一致，无横向溢出；API 详情、运行报告、图谱执行、AI 生成链与 DOCX 预览仍受真实数据缺口限制。
- **测试调整**：`paginationConsistency` 与 `listPanelConsistency` 从“读取 CSS 计算值”改为“断言共享 utility 类契约 + 分页圆角仍由公共样式维护”，与阶段 43 的 computed-style 测试形成互补。

### 剩余不可迁移 / 明确保留

- **B 类页面/共享 Module（19 个文件 / 3,157 行）**：AntD / React Flow / CodeMirror / DOCX 深层选择器、状态色、动效、页面高度链与容器查询。生成链/画布的节点状态与动画是产品视觉的一部分，不再 utility 化。
- **C 类全局契约（14 个文件 / 1,759 行）**：按钮层、列表表格、表面 token、外壳、滚动条、分页、页签动效；保留 49 处 `!important` 的级联理由已逐文件登记。
- **D 类 Token（7 个文件 / 1,828 行）**：主题、调色板与 Tailwind 层声明保留；剩余无直接消费者的调色板 token 属设计系统资产，未在缺少设计确认时批量删除。
- **视觉验收缺口**：运行报告、图谱执行、AI 生成链、DOCX 预览未取得真实数据；后续补数据时按阶段 42 记录的路由、断点与主题复测。

### 阶段 39–45：执行结果

阶段 38 只完成预算收口；阶段 39–45 完成结构性整改，最终达到 **40 个文件 / 6,738 行 / 49 处 `!important` / 1,162 条布局声明**：

1. **39 重新定界 + 安全 B 类第一批（已完成）**：布局声明审计入基线；删除 `ui-detail-inspector`、`test-order-visualization`，收缩 `api-detail-rules`、`ui-stage-visual`。
2. **40 B 类页面布局第二批（已完成）**：测试单工作台、Bug、接口库、Sprint 概览、账户样式迁 utility。
3. **41 共享原语与合并（已完成）**：`RunCard` / `MethodBadge` / `workbench-panel-flat`；删除禅道绑定与侧栏导航 CSS；收缩生成链/画布/需求文档。
4. **42 数据依赖界面视觉验收（已完成可执行范围）**：Sprint 详情与列表/外壳已核对；运行报告、图谱、AI 生成链、DOCX 预览缺口保留记录。
5. **43 C 类全局契约收缩（已完成）**：`!important` 93 → 49，移除项配 computed-style 测试，保留项逐条登记。
6. **44 D 类 token 清理与最终收口（已完成）**：`--legacy-*` 清零，未定义 fallback 消除，最终指标与不可迁移清单更新。
7. **45 残留布局清理（已完成）**：页脚、工作台页签、滚动承载层、表尾、Logo 与外壳头部去重；6,996 → 6,738 行，布局声明 1,248 → 1,162。
