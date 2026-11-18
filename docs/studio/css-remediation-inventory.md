# Studio CSS 存量整改总清单

> 2026-11-18。阶段 0–32 已完成；本文件是阶段 33 起的完整整改台账。它覆盖 `apps/studio/src/**/*.css` 当前全部 **58 个文件**，不是单模块建议。阶段 29 前的 66 文件基线仍保留在下方表格的“阶段 29 前”口径中。
>
> 数据口径：`scripts/check-css-budget.mjs`、`scripts/check-css-structure.mjs` 与逐文件静态分类脚本。“布局”指 `display/flex/grid/gap/padding/margin/size/overflow` 等结构声明；“皮肤”指颜色、字体、边框、圆角、阴影、动效等声明；“深层规则”指带后代选择器、`:global(...)` 或组件内部 DOM 的规则。数字用于排序，不替代浏览器验收。

## 一、总账与达标缺口

| 指标 | 当前 | 目标 | 缺口 |
| --- | ---: | ---: | ---: |
| CSS 文件 | 58 | ≤ 45 | **-13** |
| CSS 行数 | 13,579 | ≤ 9,000 | **-4,579** |
| `!important` | 95 | ≤ 100 | 已达标（数值） |
| 长前缀 | 0 | 0 | 已达标 |
| 重复规则体 | 38 | ≤ 60 | 已达标 |
| 单文件 > 600 行 | 0 | 0 | 已达标 |

**先看结论，避免继续“一个模块一个模块”地漏：**

1. **真正的缺口是文件数和行数，不是 `!important`。** 95 处 `!important` 中 85 处在全局外壳/表格/按钮/表面契约，只有 10 处在页面 Module（`sprint-overview` 4、`ui-detail-shell` 6）。后面不应为了数字机械去 `!important`。
2. **只迁布局达不到行数目标。** 只迁布局仍覆盖不了 4,579 行的缺口；阶段 29–32 已实际验证，必须同时迁皮肤。要达标，颜色、字体、边框、圆角、阴影等皮肤声明也必须随 JSX utility 或共享 token 迁走，最终让大部分页面 Module 整体消失。
3. **按当前文件边界，保留底座已经占 23 个文件 / 4,316 行：**
   - 7 个 token 文件：1,847 行；
   - 9 个外壳/全局基础文件：1,565 行；
   - 7 个共享全局契约：904 行。
4. 因此其余 **35 个页面/共享组件文件（9,263 行）必须压到 ≤22 个文件、≤4,684 行**：至少 **13 个文件要删除或并入宿主 Module**，约 **49.4% 的页面 CSS 行要消失**。这是阶段 33–38 的硬约束。
5. 38 组重复规则体已在目标内，且多为跨页面同构皮肤；不单独立项，随页面批次顺手合并。完整列表见附录 B。

## 二、动作分类

| 动作 | 含义 | 文件数 | 行数 |
| --- | --- | ---: | ---: |
| **A** | 删除或并入宿主 Module 的确定候选；先迁 utility，再删文件 | 5 | 612 |
| **B** | 页面/共享组件 Module；按页面族迁移，能删则删，否则只留深层皮肤 | 30 | 8,651 |
| **C** | 全局契约；只做死规则、层叠和重复体收缩，不整体 utility 化 | 16 | 2,469 |
| **D** | Token / 主题 / Tailwind 层；保留，只清理无消费者 token | 7 | 1,847 |

> A 类不是“删掉就完事”：必须先把对应 JSX 的布局与可迁移皮肤换成 utility，确认无消费方后再删文件。B 类中标注“删除候选”的文件，在皮肤迁完后同样要转 A；否则文件数目标无法达成。

### A 类：5 个确定删除/并入候选（612 行）

| 文件 | 行 | 删除前必须迁走的内容 |
| --- | ---: | --- |
| `features/ai-testing/styles/artifact-misc.module.css` | 187 | 67 条布局 + 34 条皮肤；3 条深层规则 |
| `features/profile/styles/profile-settings.module.css` | 65 | 7 条布局 + 19 条皮肤；4 条深层规则 |
| `shared/styles/base-services-connection.module.css` | 195 | 61 条布局 + 35 条皮肤；0 条深层规则 |
| `shared/styles/case-import.module.css` | 63 | 28 条纯布局 + 3 条皮肤；5 条深层规则 |
| `shared/styles/legacy-surface.css` | 102 | 37 条布局 + 12 条皮肤；遗留全局类 |

### C 类：16 个全局契约（2,469 行）

`app/styles/*` 8 个、`index.css`、`shared/styles/` 下的 `list-name`、`list-table`、`pagination`、`surface-tokens`、`tab-motion`、`table-row-dividers`、`scrollbars`。这些规则服务于多个页面，且多数是在压 AntD/旧层叠；只允许在完整浏览器对照下删死规则、合并同体规则、减少可替代的 `!important`。**不要把这些文件当页面 Module 迁走。**

### D 类：7 个 Token 文件（1,847 行）

`chart-tokens`、`foundation-tokens`、`github-dark-foundation`、`github-dark-tokens`、`indigo-amber-light-tokens`、`ui-stage-visual-tokens`、`tailwind`。它们不产生页面布局，不参与文件数削减；只做“无消费者 token”清理。文件数目标必须从 A/B 里出，不能靠删 token 凑数。

## 三、完整文件清单（按页面族）

> 每一行都是一个待办项；“动作”列用 A/B/C/D 标记。当前 58 个文件均已列入，没有省略项；阶段 29–32 删除的 8 个文件不再保留条目。


### 一、外壳与全局基础

外壳、布局、侧栏、主题与全局 reset；全部 C 类，不随页面迁移。

**9 个文件 / 1,565 行 / 273 条布局声明 / 394 条皮肤声明**

| 文件 | 行 | 布局（纯/混） | 皮肤 | 深层规则 | `!important` | 重复体 | 动作 | 整改说明 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| `app/styles/action-buttons.css` | 196 | 0 / 0 | 18 | 9 | 0 | 0 | **C** | 全局按钮/动作图标皮肤；只做死规则与层叠收缩 |
| `app/styles/antd-overrides.css` | 60 | 0 / 0 | 28 | 1 | 0 | 0 | **C** | 全局 AntD 覆盖；只做死规则与层叠收缩 |
| `app/styles/buttons.css` | 219 | 0 / 6 | 107 | 10 | 31 | 0 | **C** | 全局按钮契约，31 处 `!important`，最高风险 |
| `app/styles/layout.css` | 200 | 13 / 34 | 59 | 1 | 2 | 2 | **C** | 外壳布局契约；不随页面迁移 |
| `app/styles/shell-header.css` | 231 | 31 / 12 | 64 | 2 | 1 | 0 | **C** | 外壳头部契约；只收缩 |
| `app/styles/shell.css` | 424 | 90 / 29 | 52 | 3 | 3 | 0 | **C** | 外壳布局契约；只收缩 |
| `app/styles/sidebar.css` | 110 | 18 / 32 | 39 | 2 | 0 | 1 | **C** | 全局侧栏；只收缩 |
| `app/styles/theme.css` | 27 | 1 / 3 | 7 | 3 | 4 | 0 | **C** | 主题变量与玻璃层；只收缩 |
| `index.css` | 98 | 2 / 2 | 20 | 0 | 2 | 0 | **C** | 全局 reset/基础层；只收缩 |

### 二、UI 自动化（阶段 29 已完成）

测试集列表、详情壳、检查器、执行流水线与测试集抽屉。

**3 个文件 / 546 行（阶段 29 前：5 个 / 1,959 行）**。页面布局与可迁移皮肤已全部迁入组件 utility；以下只保留 AntD / React Flow 深层规则。

| 文件 | 行 | 布局（纯/混） | 皮肤 | 深层规则 | `!important` | 重复体 | 动作 | 整改说明 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| `features/ui-automation/styles/ui-detail-inspector.module.css` | 71 | — | — | 2 | 0 | 0 | **B** | 右栏卡片原语与 AntD 空态；阶段 29 后不再承载页面布局 |
| `features/ui-automation/styles/ui-detail-shell.module.css` | 317 | — | — | 多 | 6 | 0 | **B** | 板面、顶栏输入、未保存态、React Flow 深层规则 |
| `features/ui-automation/styles/ui-suite.module.css` | 158 | — | — | 多 | 0 | 0 | **B** | 测试集抽屉与步骤编辑器的 AntD 表单深层规则 |

### 三、API 自动化（阶段 30 已完成）

测试集列表、详情壳、请求编辑器、请求头/请求体、规则/后置操作与环境选择。

**2 个文件 / 336 行（阶段 30 前：4 个 / 1,466 行）**。列表、顶栏、用例行、请求面板、环境弹层与后置操作已迁入组件 utility；以下只保留 AntD / CodeMirror 深层规则和页面级玻璃变量。

| 文件 | 行 | 布局（纯/混） | 皮肤 | 深层规则 | `!important` | 重复体 | 动作 | 整改说明 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| `features/api-automation/styles/api-detail-shell.module.css` | 231 | — | — | 多 | 0 | 0 | **B** | 用例名称行、方法 Select、路径输入、Tabs、键值输入、请求头表与请求体 CodeMirror |
| `features/api-automation/styles/api-detail-rules.module.css` | 105 | — | — | 多 | 0 | 0 | **B** | 环境弹层、规则弹窗、AntD 卡片/按钮与 JSON 编辑器玻璃外壳 |

### 四、测试单（阶段 31 已完成）

列表、工作台、图谱与可视化。

**2 个文件 / 329 行（阶段 31 前：5 个 / 1,154 行）**。列表、工作台骨架、图谱页壳/查看器、执行面板与判定区已迁入组件 utility；以下只保留页面高度链、AntD 表格/弹层深层规则与可视化容器查询。

| 文件 | 行 | 布局（纯/混） | 皮肤 | 深层规则 | `!important` | 重复体 | 动作 | 整改说明 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| `features/test-orders/styles/test-order-visualization.module.css` | 119 | — | — | 多 | 0 | 5 | **B** | 可视化面板的容器查询布局与图表/空态皮肤 |
| `features/test-orders/styles/test-order-workspace.module.css` | 210 | — | — | 多 | 0 | 6 | **B** | 页面高度链、工具栏/条目表格、详情翻页、加入用例弹窗、执行条与判定控件 |

### 五、接口库（阶段 32 已完成）

接口列表/树、详情与编辑器。

**2 个文件 / 238 行（阶段 32 前：3 个 / 1,550 行）**。列表、软件仓库树、抽屉表单、详情两栏、请求地址条、标签页、面板、键值表与 OpenAPI 导入流程已迁入组件 utility；以下只保留页面壳、AntD 深层规则和方法签。

| 文件 | 行 | 布局（纯/混） | 皮肤 | 深层规则 | `!important` | 重复体 | 动作 | 整改说明 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| `features/interface-library/styles/interface-detail.module.css` | 100 | — | — | 多 | 0 | 0 | **B** | 名称/路径输入、方法 Select、键值表输入、面板工具按钮与导入 Tag 间距 |
| `features/interface-library/styles/interface-library.module.css` | 138 | — | — | 多 | 0 | 0 | **B** | 页面壳与移动端内距、加载态、软件仓库树搜索/标签/空态、仓库表格深层规则与方法签 |

### 六、AI 测试 / 生成链

需求生成、生成链、画布、产物、关系图谱、UI 生成与阶段可视化。

**10 个文件 / 3,759 行 / 2,188 条布局声明 / 2,026 条皮肤声明**

| 文件 | 行 | 布局（纯/混） | 皮肤 | 深层规则 | `!important` | 重复体 | 动作 | 整改说明 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| `features/ai-testing/styles/ai-page.module.css` | 215 | 11 / 14 | 94 | 9 | 0 | 0 | **B** | 皮肤为主（94 条），布局收益低；放到 AI 批次末尾 |
| `features/ai-testing/styles/ai-task-detail.module.css` | 386 | 86 / 54 | 112 | 1 | 0 | 5 | **B** | 任务详情骨架可迁；保留产物/AntD 皮肤 |
| `features/ai-testing/styles/artifact-api.module.css` | 512 | 58 / 117 | 119 | 0 | 0 | 3 | **B** | 产物 API 视图；0 条深层规则，布局可整块迁 |
| `features/ai-testing/styles/artifact-cases.module.css` | 395 | 64 / 92 | 145 | 2 | 0 | 2 | **B** | 产物用例视图；40 条上下文选择器，逐块迁 |
| `features/ai-testing/styles/artifact-misc.module.css` | 187 | 45 / 22 | 34 | 3 | 0 | 2 | **A** | 187 行小 Module，迁完布局与少量皮肤后删除 |
| `features/ai-testing/styles/generation-canvas.module.css` | 283 | 194 / 166 | 305 | 20 | 0 | 15 | **B** | 画布/检查器 665 条声明，AI 批次最大单元 |
| `features/ai-testing/styles/generation-chain.module.css` | 419 | 284 / 219 | 354 | 12 | 0 | 19 | **B** | 生成链 857 条声明，AI 批次最大单元 |
| `features/ai-testing/styles/relations.module.css` | 351 | 68 / 124 | 138 | 3 | 0 | 2 | **B** | 关系图谱；55 条上下文选择器 |
| `features/ai-testing/styles/ui-generation.module.css` | 421 | 82 / 69 | 87 | 5 | 0 | 3 | **B** | UI 生成来源/弹窗；按弹窗分块迁 |
| `features/ai-testing/styles/ui-stage-visual.module.css` | 590 | 133 / 286 | 638 | 3 | 0 | 4 | **B** | 阶段可视化 1,057 条声明、皮肤 638 条；只迁页面类，文件保留 |

### 七、用例 / Bug / 需求

三个高频详情/列表模块；深层 AntD 规则最多，单独核对。

**3 个文件 / 1,465 行 / 613 条布局声明 / 487 条皮肤声明**

| 文件 | 行 | 布局（纯/混） | 皮肤 | 深层规则 | `!important` | 重复体 | 动作 | 整改说明 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| `features/test-cases/styles/case-library.module.css` | 503 | 54 / 32 | 141 | 24 | 0 | 3 | **B** | 用例库 503 行；24 条深层规则，表格/编辑弹窗分块迁 |
| `features/bugs/styles/bugs.module.css` | 472 | 192 / 168 | 238 | 43 | 0 | 4 | **B** | Bug 列表/表单 598 条声明；高收益但 43 条深层规则 |
| `features/requirements/styles/requirement-detail.module.css` | 490 | 63 / 104 | 108 | 3 | 0 | 1 | **B** | 需求详情 490 行；保留文档/AI 皮肤 |

### 八、基础服务 / Auth / 个人设置 / Projects

禅道绑定、登录、个人设置、环境抽屉、项目概览与 Sprint 看板。

**6 个文件 / 1,142 行 / 193 条布局声明 / 364 条皮肤声明**

| 文件 | 行 | 布局（纯/混） | 皮肤 | 深层规则 | `!important` | 重复体 | 动作 | 整改说明 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| `features/base-services/styles/zentao-binding.module.css` | 209 | 42 / 22 | 40 | 9 | 0 | 2 | **B** | 禅道绑定页；9 条深层规则 |
| `features/auth/styles/auth.module.css` | 175 | 3 / 10 | 53 | 14 | 0 | 0 | **B** | 页面专属但 14 条深层规则；低收益，最后处理 |
| `features/profile/styles/profile-settings.module.css` | 65 | 2 / 5 | 19 | 4 | 0 | 0 | **A** | 65 行小 Module，整体迁 utility 后删除 |
| `features/projects/styles/environment-drawer.module.css` | 318 | 9 / 36 | 121 | 10 | 0 | 0 | **B** | 阶段 24 已迁布局；剩余皮肤/AntD 深层，只清死规则 |
| `features/projects/styles/projects-overview.module.css` | 99 | 18 / 7 | 55 | 13 | 0 | 3 | **B** | 99 行；13 条深层规则，皮肤为主，低收益 |
| `features/projects/styles/sprint-overview.module.css` | 276 | 17 / 22 | 76 | 9 | 4 | 0 | **B** | Sprint 看板；保留 4 处 `!important`，最后动 |

### 九、共享组件

富文本、连接表单、导入弹窗、实体卡片、JSON 编辑器、运行报告与遗留表面。

**7 个文件 / 1,448 行 / 463 条布局声明 / 283 条皮肤声明**

| 文件 | 行 | 布局（纯/混） | 皮肤 | 深层规则 | `!important` | 重复体 | 动作 | 整改说明 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| `shared/components/RichTextEditor/rich-text-editor.css` | 226 | 11 / 37 | 56 | 3 | 0 | 2 | **B** | 共享富文本；跨页面，最后与 run-view 一起动 |
| `shared/styles/base-services-connection.module.css` | 195 | 42 / 19 | 35 | 0 | 0 | 0 | **A** | 195 行、0 条深层规则；整文件迁 utility 后删除 |
| `shared/styles/case-import.module.css` | 63 | 28 / 0 | 3 | 5 | 0 | 2 | **A** | 63 行、纯布局 28 条；整文件迁 utility 后删除 |
| `shared/styles/entity-card.css` | 166 | 31 / 29 | 41 | 0 | 0 | 1 | **B** | 共享卡片原语；迁布局，皮肤进 token |
| `shared/styles/json-editor.module.css` | 138 | 18 / 13 | 36 | 1 | 0 | 1 | **B** | 共享 JSON 编辑器；保留编辑器皮肤 |
| `shared/styles/legacy-surface.css` | 102 | 31 / 6 | 12 | 0 | 0 | 2 | **A** | 102 行遗留表面；类可迁 utility/共享层后删除 |
| `shared/styles/run-view.module.css` | 558 | 113 / 85 | 100 | 6 | 0 | 4 | **B** | 共享运行报告 558 行；跨 API/UI/测试单，最后迁 |

### 十、共享全局契约

列表名称、表格、分页、表面、Tab 动效、分隔线与滚动条；只收缩，不整体 utility 化。

**7 个文件 / 904 行 / 213 条布局声明 / 252 条皮肤声明**

| 文件 | 行 | 布局（纯/混） | 皮肤 | 深层规则 | `!important` | 重复体 | 动作 | 整改说明 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| `shared/styles/list-name.css` | 19 | 0 / 0 | 12 | 2 | 6 | 0 | **C** | 全局列表名称契约；6 处 `!important`，只收缩 |
| `shared/styles/list-table.css` | 152 | 7 / 10 | 50 | 5 | 16 | 0 | **C** | 全局表格契约；16 处 `!important`，最高风险 |
| `shared/styles/pagination.css` | 87 | 4 / 25 | 19 | 1 | 1 | 0 | **C** | 全局分页契约；只收缩 |
| `shared/styles/surface-tokens.css` | 577 | 97 / 60 | 146 | 2 | 12 | 7 | **C** | 全局表面契约；12 处 `!important`，只收缩 |
| `shared/styles/tab-motion.css` | 33 | 4 / 4 | 16 | 4 | 6 | 0 | **C** | 全局 Tab 动效；6 处 `!important`，行为契约 |
| `shared/styles/table-row-dividers.css` | 7 | 0 / 0 | 1 | 0 | 1 | 0 | **C** | 1 条全局表格分隔线契约；可并入 list-table |
| `shared/styles/scrollbars.css` | 29 | 2 / 0 | 8 | 0 | 0 | 0 | **C** | 全局滚动条行为；保留，最多合并 |

### 十一、Token / 主题 / Tailwind 基础

主题 token 与 Tailwind 层声明；保留，不参与页面迁移。

**7 个文件 / 1,847 行 / 0 条布局声明 / 1,647 条皮肤声明**

| 文件 | 行 | 布局（纯/混） | 皮肤 | 深层规则 | `!important` | 重复体 | 动作 | 整改说明 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |
| `shared/styles/chart-tokens.css` | 50 | 0 / 0 | 40 | 0 | 0 | 0 | **D** | 图表 token；保留 |
| `shared/styles/foundation-tokens.css` | 575 | 0 / 0 | 534 | 0 | 0 | 0 | **D** | 基础 token；保留 |
| `shared/styles/github-dark-foundation.css` | 522 | 0 / 0 | 498 | 0 | 0 | 0 | **D** | 深色主题 token；保留 |
| `shared/styles/github-dark-tokens.css` | 233 | 0 / 0 | 200 | 0 | 0 | 0 | **D** | 深色主题 token；保留 |
| `shared/styles/indigo-amber-light-tokens.css` | 329 | 0 / 0 | 288 | 6 | 0 | 0 | **D** | 浅色主题 token；保留 |
| `shared/styles/tailwind.css` | 48 | 0 / 0 | 0 | 0 | 0 | 0 | **D** | Tailwind 层声明；保留 |
| `shared/styles/ui-stage-visual-tokens.css` | 90 | 0 / 0 | 87 | 0 | 0 | 0 | **D** | 阶段可视化 token；保留 |


## 四、阶段排期（29–38）

> 每个阶段覆盖一个完整页面族，不再“今天只做一个模块”。阶段内的子批只用于控制验证范围，不改变该阶段必须覆盖的文件全集。

| 阶段 | 范围 | 当前 | 达标线 | 文件目标 | 核心动作 | 风险 |
| --- | --- | ---: | ---: | :---: | --- | --- |
| 29 | UI 自动化全部 5 个 Module | 1,959 | ≤ 650 | 5 → 3 | **已完成（546 行）**：测试集/步骤编辑器、执行流水线、检查器、详情壳、顶栏一次排完；顶栏与流程深层规则并入详情壳；保留回放/控制台/React Flow 深层皮肤 | 中 |
| 30 | API 自动化全部 4 个 Module | 1,466 | ≤ 450 | 4 → 2 | **已完成（336 行）**：删除 `api-list` 与 `api-detail-request`；列表、详情、请求面板、环境弹层与后置操作迁 utility；保留 AntD/CodeMirror 深层规则 | 中 |
| 31 | 测试单全部 5 个 Module | 1,154 | ≤ 350 | 5 → 2 | **已完成（329 行）**：删除图谱/列表/图谱执行 Module；执行视图并入工作台；列表、工作台骨架、图谱壳与判定区迁 utility；保留可视化容器查询与 AntD 表格深层规则 | 中高 |
| 32 | 接口库全部 3 个 Module | 1,550 | ≤ 550 | 3 → 2 | **已完成（238 行）**：列表/树/抽屉、详情、编辑器面板、键值表与 OpenAPI 导入流程迁 utility；删除编辑器 Module，AntD 深层规则并入详情 | 低–中 |
| 33 | AI 测试/生成链全部 10 个 Module | 3,759 | ≤ 1,450 | 10 → 5 | 33A 三个产物 Module 合并、关系并入生成链；33B 画布/生成链/阶段可视化；33C 生成页/任务详情；UI 生成并入任务详情，删 `ai-page` | 高 |
| 34 | 用例 / Bug / 需求 3 个 Module | 1,465 | ≤ 650 | 3 → 3 | 表格、筛选、表单骨架迁 utility；三个 Module 各自保留深层 AntD 皮肤，24/43 条深层规则单独核对 | 高 |
| 35 | 基础服务 / Auth / 个人设置 / Projects 6 个 Module | 1,142 | ≤ 450 | 6 → 4 | 删 `profile-settings`；项目概览并入 Sprint 看板；环境抽屉、Auth 以皮肤为主，低收益，最后处理 | 中 |
| 36 | 共享组件 7 个文件 | 1,448 | ≤ 450 | 7 → 2 | 删 `case-import`、`base-services-connection`、`legacy-surface`；实体卡片/JSON 编辑器并入共享原语；保留富文本与运行报告 | 高 |
| 37 | 全局契约 16 个文件 | 2,469 | ≤ 2,100 | 16 → 14 | 只做死规则、重复体、可替代 `!important`；把 `table-row-dividers` 与 `list-name` 并入 `list-table` | 高 |
| 38 | 收口 | — | ≤ 9,000 / ≤ 45 | 44 | 全量复测、ratchet 两个基线、清理无消费者 token、更新本文与迁移计划 | 低 |

**目标校验**：546（阶段 29 实际）+ 336（阶段 30 实际）+ 329（阶段 31 实际）+ 238（阶段 32 实际）+ 1,450 + 650 + 450 + 450 + 2,100 + 1,847（token）= **8,396 行**；文件目标 **44**（≤45，留 1 个文件余量）。达标线是排期目标，最终以实际数字为准；如果某阶段只完成布局迁移，必须在阶段 38 前补做皮肤迁出，否则目标不成立。

### 各阶段完成口径

每个阶段结束必须同时满足：

- 该阶段列出的每个文件都已处理：删除、并入或缩到只剩深层皮肤；不能留“下阶段再说”的页面类规则。
- `npx tsc --noEmit -p tsconfig.app.json`、全量 `npm test`、`npm run verify`、CSS 三件套、`git diff --check` 通过。
- 浏览器按 1280 / 900 / 760、浅色 / 深色核对页面族；表格、弹窗、Drawer、空态、长文本、页面切换残留覆盖都要看。
- `node scripts/check-css-structure.mjs --update` 只 ratchet 已完成的下降；不得为了过关放宽文件/行数/规则数上限。
- 更新 `docs/studio/css-migration-plan.md` 的阶段状态和指标表，并保留本文作为全量台账。

## 五、`!important` 全量清单

当前 95 处，分布在 14 个文件。**85 处在全局契约，10 处在页面 Module**；后者只有 `sprint-overview`（4）和 `ui-detail-shell`（6）。因此它不是当前主矛盾，但下列文件仍是高风险区：

| 文件 | 数量 | 风险点 |
| --- | ---: | --- |
| `app/styles/buttons.css` | 31 | AntD 按钮所有状态；反向压制基础按钮层，牵一发动全身 |
| `shared/styles/list-table.css` | 16 | 表格表头/行/圆角/分隔线；列表一致性测试依赖 |
| `shared/styles/surface-tokens.css` | 12 | 列表板面、macOS 玻璃面、过滤组 |
| `features/ui-automation/styles/ui-detail-shell.module.css` | 6 | macOS 详情板面透明化 |
| `shared/styles/list-name.css` | 6 | 列表名称字体/颜色；跨所有列表 |
| `shared/styles/tab-motion.css` | 6 | Tab 指示器透明与动效关闭 |
| `app/styles/theme.css` | 4 | 浅色主题控件表面 |
| `features/projects/styles/sprint-overview.module.css` | 4 | macOS Sprint 看板板面 |
| `app/styles/shell.css` | 3 | 紧凑头部、表格单元格伪元素、项目选择 |
| `app/styles/layout.css` | 2 | 项目选择器内距、Tab 激活色 |
| `src/index.css` | 2 | 描述文字颜色 |
| `app/styles/shell-header.css` | 1 | macOS 弱化文字 |
| `shared/styles/pagination.css` | 1 | 表格页脚背景 |
| `shared/styles/table-row-dividers.css` | 1 | 全局行分隔线 |

完整规则与声明见附录 A。处理原则：

- 先确认是否有同权重替代规则或 `@layer` 可覆盖；只有确认无替代才保留 `!important`。
- 全局按钮/表格/表面契约一次只动一个文件，并用 computed style 对比，不允许“批量去 `!important`”。
- 页面 Module 剩余 10 处随阶段 35/38 处理；全局 85 处随阶段 37 处理，优先合并同体规则和删死规则，而不是硬去 `!important`。

## 六、重复规则体（38 组）

结构门禁口径 38 组，已在 ≤60 目标内。它们主要是跨页面的 `display:none`、`font-size`、`width:100%`、`margin:0`、`flex:0 0 auto`、`min-width:0` 等单属性皮肤/布局规则。处理方式：

- 不单独立项，不为了把 44 降到 0 而合并语义不同的选择器。
- 页面批次里如果同一规则体落在同一宿主/同一 utility 能表达，就合并；否则保留。
- 附录 B 列出全部 38 组的成员选择器，供批次内查重，不要求逐组清零。

## 七、附录

### 附录 A：全部 `!important` 规则

#### `app/styles/buttons.css`
- `.ant-btn`
  - `color: var(--button-current-text) !important`; `background: var(--button-current-bg) !important`; `border-color: var(--button-current-border) !important`; `-webkit-backdrop-filter: none !important`; `backdrop-filter: none !important`; `box-shadow: none !important`; `text-shadow: none !important`; `transform: none !important`; `font-weight: 500 !important`
- `.ant-btn:not(.ant-btn-circle):not(.ant-btn-round)`
  - `border-radius: 8px !important`
- `.ant-btn:not(:disabled):not(.ant-btn-disabled):not(.ant-btn-loading):hover`
  - `background: var(--button-current-hover) !important`; `border-color: var(--button-current-hover-border) !important`
- `.ant-btn:not(:disabled):not(.ant-btn-disabled):not(.ant-btn-loading):active`
  - `background: var(--button-current-active) !important`
- `.ant-btn:focus-visible`
  - `outline: 2px solid var(--button-focus) !important`; `outline-offset: 2px !important`
- `.ant-btn:disabled, .ant-btn.ant-btn-disabled`
  - `color: var(--button-disabled-text) !important`; `background: var(--button-disabled-bg) !important`; `border-color: var(--button-disabled-border) !important`; `cursor: not-allowed !important`
- `:is(.ant-btn-text, .ant-btn-link):is(:disabled, .ant-btn-disabled)`
  - `background: transparent !important`; `border-color: transparent !important`
- `.ant-btn.app-action-icon, .ant-table .ant-btn.ant-btn-icon-only:is(.ant-btn-text, .ant-btn-link), .sprint-card-actions .ant-btn.ant-btn-icon-only`
  - `width: 28px !important`; `min-width: 28px !important`; `height: 28px !important`; `padding: 0 !important`; `border-radius: 6px !important`; `font-size: 14px !important`
- `.ant-btn.app-action-icon > .ant-btn-icon, .ant-table .ant-btn.ant-btn-icon-only > .ant-btn-icon`
  - `font-size: 14px !important`
- `.ant-table .ant-btn.app-action-run`
  - `height: 28px !important`; `font-size: 12px !important`; `gap: 4px !important`
#### `app/styles/layout.css`
- `.project-select .ant-select-selector`
  - `padding-inline: 0 !important`
- `.workbench-tabs .ant-tabs-tab-active .ant-tabs-tab-btn`
  - `color: var(--app-accent-hover) !important`
#### `app/styles/shell-header.css`
- `.app-shell-macos .sprint-card-label, .app-shell-macos .api-collection-description`
  - `color: var(--mac-glass-muted) !important`
#### `app/styles/shell.css`
- `.compact-header .project-select .ant-select-selector`
  - `padding-inline: 0 !important`
- `.workbench-panel .ant-table-cell::before`
  - `background-color: var(--tp-border-soft) !important`
- `.app-shell .project-select .ant-select-selector`
  - `color: var(--app-glass-text) !important`
#### `app/styles/theme.css`
- `:root:root:not([data-theme='dark']) .app-shell :is(.ant-input-affix-wrapper, .ant-select-selector, .ant-select:not(.ant-select-borderless):not(.ant-select-disabled) .ant-select-content)`
  - `background: var(--app-control-surface) !important`; `border-color: var(--button-border) !important`
- `:root:root:not([data-theme='dark']) .app-shell .ant-input-affix-wrapper input`
  - `background: transparent !important`
#### `features/projects/styles/sprint-overview.module.css`
- `:root:root :global(.app-shell-macos) .root :global(.sprint-overview-panel-unified)`
  - `border: 0 !important`; `border-radius: 0 !important`; `background: transparent !important`; `box-shadow: none !important`
#### `features/ui-automation/styles/ui-detail-shell.module.css`
- `:global(.app-shell-macos) .scope :global(.api-automation-content > .workbench-panel.ui-suite-detail-board)`
  - `border: 0 !important`; `border-radius: 0 !important`; `background: transparent !important`; `box-shadow: none !important`; `-webkit-backdrop-filter: none !important`; `backdrop-filter: none !important`
#### `index.css`
- `.ant-empty-description, .ant-form-item-extra, .project-description-text, .api-collection-description, .api-env-var-picker-item-desc`
  - `color: var(--description-text) !important`
- `.ant-empty-description, .ant-form-item-extra`
  - `color: var(--description-text-muted) !important`
#### `shared/styles/list-name.css`
- `:root:root .app-shell-macos .ant-table-wrapper .ant-table .ant-table-tbody .tp-list-name .ant-typography`
  - `color: var(--app-list-name) !important`; `font-family: Arial, "Microsoft YaHei", "Noto Sans CJK SC", sans-serif !important`; `font-size: 13px !important`; `font-weight: 400 !important`; `line-height: 24px !important`
- `:root:root .app-shell-macos .ant-table-wrapper .ant-table .ant-table-tbody .tp-list-name :is(.ant-typography:hover, .ant-typography:focus-visible, a:focus-visible .ant-typography)`
  - `color: var(--app-list-name-hover) !important`
#### `shared/styles/list-table.css`
- `:root .tp-list-surface .tp-list-table .ant-table-thead > tr > th.ant-table-cell, :root .app-shell-macos .tp-list-surface .tp-list-table .ant-table-thead > tr > th.ant-table-cell`
  - `padding: 0 16px !important`; `border: 0 !important`; `border-bottom: 1px solid var(--app-list-header-border) !important`; `border-radius: 0 !important`; `color: var(--srf-list-header-text) !important`; `background: var(--srf-list-header-bg) !important`; `box-shadow: none !important`
- `:root .tp-list-surface .tp-list-table .ant-table-tbody > tr:not(.ant-table-measure-row) > td, :root .app-shell-macos .tp-list-surface .tp-list-table .ant-table-tbody > tr:not(.ant-table-measure-row) > td`
  - `padding: 8px 16px !important`; `border-bottom: 1px solid var(--app-list-row-border) !important`; `background: var(--srf-list-row-bg) !important`
- `:root .tp-list-surface .tp-list-table .ant-table-tbody > tr:not(.ant-table-measure-row):hover > td, :root .app-shell-macos .tp-list-surface .tp-list-table .ant-table-tbody > tr:not(.ant-table-measure-row):hover > td`
  - `background: var(--srf-list-row-hover) !important`
- `:root .tp-list-surface .tp-list-table .ant-table-thead > tr > th.ant-table-cell:first-child`
  - `border-top-left-radius: 8px !important`; `border-bottom-left-radius: 8px !important`
- `:root .tp-list-surface .tp-list-table .ant-table-thead > tr > th.ant-table-cell:last-child`
  - `border-top-right-radius: 8px !important`; `border-bottom-right-radius: 8px !important`
- `:root .tp-list-surface .tp-list-table .ant-table-thead > tr > th.ant-table-cell::before`
  - `display: none !important`
#### `shared/styles/pagination.css`
- `:root:root:not([data-theme='dark']) .app-shell .table-footer`
  - `background: var(--app-list-toolbar-bg) !important`
#### `shared/styles/surface-tokens.css`
- `.app-shell-macos .testing-page .tp-surface .api-automation-content > .workbench-panel.tp-board`
  - `border: 0 !important`; `border-radius: 0 !important`; `background: transparent !important`; `box-shadow: none !important`; `-webkit-backdrop-filter: none !important`; `backdrop-filter: none !important`
- `:root:root .app-shell-macos .tp-surface .tp-board.tp-list-panel, .tp-surface .tp-board.tp-list-panel`
  - `border: 1px solid var(--srf-card-border) !important`; `border-radius: var(--srf-radius-card) !important`; `background: var(--srf-card) !important`; `box-shadow: none !important`; `backdrop-filter: none !important`
- `.tp-surface .tp-list-panel .tp-list-scroll`
  - `padding: 16px !important`
#### `shared/styles/tab-motion.css`
- `:root [role='tablist'].has-shared-tab-motion [role='tab'][aria-selected='true']`
  - `background: transparent !important`; `box-shadow: none !important`; `border-color: transparent !important`
- `:root [role='tablist'].has-shared-tab-motion .ant-tabs-tab-active`
  - `background: transparent !important`; `box-shadow: none !important`
- `.shared-tab-motion-indicator, .ant-segmented-thumb`
  - `transition: none !important`
#### `shared/styles/table-row-dividers.css`
- `:root:root .ant-table-wrapper .ant-table-tbody > tr.ant-table-row > td.ant-table-cell`
  - `border-bottom: 1px solid var(--app-list-row-border) !important`


### 附录 B：全部 38 组重复规则体

> 每组列出所有成员（文件 → 选择器）。只用于查重，不表示必须合并。

1. `src/app/styles/layout.css → .app-shell.app-shell-requirement-detail`；`src/features/test-orders/styles/test-order-workspace.module.css → :global(.app-shell):has(.root)`
2. `src/app/styles/layout.css → .app-shell.app-shell-requirement-detail > .ant-layout`；`src/features/projects/styles/projects-overview.module.css → :global(.app-shell):has(:global(.requirements-page)) :global(.workbench-page):global(.requirements-page)`
3. `src/features/ai-testing/styles/ai-task-detail.module.css → .scope :global(.ai-requirement-design-history)`；`src/features/ai-testing/styles/ai-task-detail.module.css → .scope :global(.ai-requirement-design-panel)`
4. `src/features/ai-testing/styles/ai-task-detail.module.css → .scope :global(.code-risk-report)`；`src/features/ai-testing/styles/artifact-misc.module.css → .scope :global(.repository-profile-report)`；`src/shared/styles/surface-tokens.css → .api-collection-card .ant-card-body`
5. `src/features/ai-testing/styles/artifact-api.module.css → .scope :global(.api-config-visual-rule-title)`；`src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-inspector-heading)`；`src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-inspector-review-heading)`
6. `src/features/ai-testing/styles/artifact-api.module.css → .scope :global(.api-config-visual-step)`；`src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-inspector-reading-tools .gc-footer-row)`
7. `src/features/ai-testing/styles/artifact-api.module.css → .scope :global(.api-design-visual-case-head strong)`；`src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-visual-group > header strong)`
8. `src/features/ai-testing/styles/artifact-cases.module.css → .scope :global(.ai-case-name-tree)`；`src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-artifact-scroll.is-case-names)`
9. `src/features/ai-testing/styles/artifact-cases.module.css → .scope :global(.ai-generated-case-editor label)`；`src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-modal-footer)`
10. `src/features/ai-testing/styles/artifact-misc.module.css → .scope :global(.gc-profile-binding-list)`；`src/features/test-orders/styles/test-order-visualization.module.css → .batch :global(.test-order-viz-batch-counts)`
11. `src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.api-interface-selector-scope)`；`src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.api-interface-selector-toolbar)`；`src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.revision-attachments)`；`src/features/test-orders/styles/test-order-visualization.module.css → .panel :global(.test-order-viz-toolbar)`；`src/features/test-orders/styles/test-order-visualization.module.css → .panel :global(.test-order-viz-toolbar) > div`；`src/shared/styles/surface-tokens.css → .tp-surface .tp-quick-filters`
12. `src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-canvas-frame)`；`src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-canvas-stage)`
13. `src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-flow-group-header small)`；`src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-visual-group > header small)`
14. `src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-flow-group-header)`；`src/features/ai-testing/styles/ui-stage-visual.module.css → .scope :global(.ai-artifact-mode-controls)`；`src/features/bugs/styles/bugs.module.css → .root :global(.bugs-filter-popover) :global(.api-filter-field)`；`src/shared/styles/json-editor.module.css → .toolbarActions`
15. `src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-flow-stage .gc-node-main strong)`；`src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-node > strong)`
16. `src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-flow-stage .gc-node-main)`；`src/features/ai-testing/styles/ui-stage-visual.module.css → .scope :global(.uisv-control-cell)`
17. `src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-inspector-header .gc-state.is-failed)`；`src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-inspector-header .gc-state.is-rejected)`；`src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-state.is-danger)`；`src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-trace-chip.is-danger)`
18. `src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-inspector-section h3)`；`src/features/ai-testing/styles/generation-canvas.module.css → .scope :global(.gc-inspector-review h3)`；`src/features/ai-testing/styles/ui-generation.module.css → .scope :global(.ui-source-block h4)`
19. `src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-import-footer)`；`src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.revision-footer-actions)`
20. `src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-import-record > div)`；`src/features/ai-testing/styles/ui-stage-visual.module.css → .scope :global(.uisv-readiness-copy)`
21. `src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-import-title > div)`；`src/shared/styles/entity-card.css → .entity-card-meta > div`
22. `src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-import-title)`；`src/features/test-orders/styles/test-order-visualization.module.css → .panel :global(.test-order-viz-detail-heading)`
23. `src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-node-meta > span:last-child)`；`src/features/ai-testing/styles/ui-stage-visual.module.css → .scope :global(.uisv-precondition-strip span)`
24. `src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-state.is-ok)`；`src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-trace-chip.is-ok)`
25. `src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-upstream-trigger-text)`；`src/features/bugs/styles/bugs.module.css → .root :global(.bug-form-project) > span:not(:global(.anticon))`；`src/shared/styles/run-view.module.css → .reportRoot :global(.api-collection-run-report-item-title strong)`
26. `src/features/ai-testing/styles/generation-chain.module.css → .scope :global(.gc-version-button.is-active)`；`src/features/ai-testing/styles/ui-generation.module.css → .scope :global(.ui-source-version-button.is-active)`
27. `src/features/ai-testing/styles/relations.module.css → .scope :global(.gc-relations-controls)`；`src/features/bugs/styles/bugs.module.css → .root :global(.bug-column-options)`；`src/features/test-orders/styles/test-order-visualization.module.css → .panel :global(.test-order-viz-state) > div`；`src/shared/styles/run-view.module.css → .root :global(.api-collection-run-history-layout)`；`src/shared/styles/run-view.module.css → .root :global(.api-collection-run-history-list)`
28. `src/features/ai-testing/styles/ui-generation.module.css → .scope :global(.ui-source-summary-actions)`；`src/features/base-services/styles/zentao-binding.module.css → .settingsDetails`
29. `src/features/base-services/styles/zentao-binding.module.css → .formRow`；`src/features/bugs/styles/bugs.module.css → .root :global(.bug-form-title-line)`
30. `src/features/projects/styles/projects-overview.module.css → .root :global(.requirements-binding-item) img`；`src/features/projects/styles/projects-overview.module.css → .root :global(.sprint-board-binding-status) img`
31. `src/features/requirements/styles/requirement-detail.module.css → .root :global(.requirement-document-modal-title-row)`；`src/shared/styles/run-view.module.css → .reportRoot :global(.api-collection-run-report-title)`
32. `src/features/test-cases/styles/case-library.module.css → .root :global(.case-editor-head-title)`；`src/shared/styles/surface-tokens.css → .tp-surface .api-test-header-main .api-panel-head-main`
33. `src/features/test-orders/styles/test-order-workspace.module.css → .root :global(.test-order-entry-list-panel) > :global(.test-order-workspace-toolbar)`；`src/features/test-orders/styles/test-order-workspace.module.css → .root :global(.test-order-detail-panel) > :global(.test-order-workspace-toolbar)`；`src/features/test-orders/styles/test-order-workspace.module.css → .root :global(.test-order-graph-viewer) > :global(.test-order-workspace-toolbar)`；`src/shared/styles/surface-tokens.css → .tp-surface .tp-list-panel > .tp-list-toolbar`
34. `src/features/test-orders/styles/test-order-workspace.module.css → .root:global(.tp-surface) :global(.test-order-workspace)`；`src/features/test-orders/styles/test-order-workspace.module.css → .root :global(.api-automation-content)`；`src/shared/styles/case-import.module.css → .root :global(.ant-modal-body)`
35. `src/features/ui-automation/styles/ui-detail-inspector.module.css → .scope :global(.ui-wb-card-head)`；`src/shared/styles/surface-tokens.css → .tp-surface .tp-quickbar`
36. `src/features/ui-automation/styles/ui-detail-shell.module.css → :global(.app-shell-macos) .scope :global(.api-automation-content > .workbench-panel.ui-suite-detail-board)`；`src/shared/styles/surface-tokens.css → .app-shell-macos .testing-page .tp-surface .api-automation-content > .workbench-panel.tp-board`
37. `src/shared/components/RichTextEditor/rich-text-editor.css → .rich-text-content .tiptap code`；`src/shared/components/RichTextEditor/rich-text-editor.css → .rich-text-viewer code`
38. `src/shared/styles/legacy-surface.css → .requirement-panel-head`；`src/shared/styles/surface-tokens.css → .api-filter-group`

## 八、执行顺序建议

1. **阶段 29–32（UI / API 自动化、测试单、接口库）已完成**，当前 58 文件 / 13,579 行；继续 33（AI 测试/生成链），把文件数压到约 53。
2. **再 33（AI）**：最大、最深，单独排期；先 33A 产物/关系，再 33B 画布/生成链，最后 33C 生成页/任务详情。
3. **再 34–36（用例/Bug/需求、基础服务、共享组件）**：深层 AntD 与跨页面组件集中处理，必须在浏览器里逐页对照。
4. **最后 37–38（全局契约与收口）**：只收缩，不整体迁移；所有 `!important` 变更都在这里做，避免和页面迁移混在一起难以回滚。
