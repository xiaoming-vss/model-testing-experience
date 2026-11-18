# CSS 整改与迁移计划

2026-11-17（2026-11-18 更新阶段 26）。本文是 Studio CSS 存量整改与 Tailwind CSS v4 / CSS Modules 迁移的执行顺序、阶段目标和验收口径。策略约束见 [ADR 0004](adr/0004-tailwind-v4-new-code-styles.md)，日常编码规则见 [STRUCTURE S16](STRUCTURE.md#四目录与样式契约)。

**执行状态（2026-11-18）**：阶段 0–26 已执行完成；结束指标中的 `!important`（95）、长前缀（0）与重复规则体（57）已达标，文件数（67）与行数（18,556）仍高于 ≤45 / ≤9,000 的目标。阶段 8 迁完 AI 测试/生成链的页面壳、生成链弹窗、画布、产物视图、关系图谱与 UI 生成可视化，删除 25 个旧 CSS（含 3 个组件内 CSS），新增 12 个根作用域 Module。阶段 9 删除 `App.css` 聚合，把 4 个超 600 行文件拆成 10 个 Module/样式文件（C1 归零），结构门禁新增单文件行数与 `App.css` 回归检查；`!important` 307 / 长前缀 121 / 重复规则体 110 保持不变。阶段 10 把 Test Orders 工作台、图谱、可视化与加入用例弹窗迁为 7 个根作用域 Module，删除 9 个旧 CSS。阶段 11 把用例编辑弹窗、用例库页面骨架与导入禅道弹窗迁为 Module，删除 3 个旧 CSS。阶段 12 把 Projects 看板与 Sprint 详情迁为 3 个 Module，删除 5 个旧 CSS。阶段 13 删除外壳、旧侧栏、项目头和按钮层的零引用规则，`!important` 307 → 262、长前缀 121 → 101、重复规则体 110 → 109。阶段 14 把最后 4 个非 Module feature CSS 迁为根作用域 Module，feature 内非 Module CSS 归零；`--legacy-*` 审计确认 28 个别名全部仍被消费，未删除。阶段 15 开始 Tailwind 化试点：个人设置/修改密码的布局与排版迁入 utility，删除两个 Module；修正 AntD reset 的 layer 归属，使 utility 能覆盖 reset。阶段 16 把 TestingPage、项目设置抽屉、导入禅道弹窗、加入用例弹窗与测试单列表的布局/间距迁入 utility，再删除两个 Module。阶段 17 把 Projects/Sprint 看板、用例库与测试单工作台的列表/详情骨架迁入 utility，三处 Module 收缩到只剩皮肤与 AntD 深层结构。阶段 18 完成：需求详情、API 测试集详情壳/编辑器、UI 测试详情、关系图谱与 AI 生成链的布局迁入 utility，六个主要 Module 合计 2,285 → 1,674 行；顺带修正 UI 详情 1180px 以下堆叠时画布与检查器重叠。阶段 19 完成共享层安全收缩：删除 `tp-list-toolbar` 中已无引用的 test-orders/ai-task 选择器，把列表搜索框 288px 宽度迁到各页面 `w-72` utility；预算基线收紧到 253 处 `!important`、91 组重复规则体。按钮字体继承与 `.tp-tone-tag` 的未分层契约保留并记录。阶段 20 完成共享原语分层与死规则收缩：控件字体重置去重，`.tp-chip`/`.tp-tone-tag`/`.tp-list-toolbar`/筛选原语移入 `@layer components`，`app-buttons` 纳入层声明；`!important` 253 → 236、长前缀 101 → 98。阶段 21 合并同根/同宿主 Module 与小型全局文件，93 → 68 个 CSS 文件；行数因合并分隔注释 +7，`!important`/长前缀/重复规则体不变。阶段 22 合并同文件同规则体的选择器列表，重复规则体 91 → 59、`!important` 236 → 235，文件数 68 不变。阶段 23 把 macOS 外壳前缀统一为单类 `.app-shell-macos`，长前缀 98 → 0；删除 140 处可被层叠顺序替代的 `!important`，`!important` 235 → 95，行数 19,169 → 19,014。阶段 24 恢复逐页 Tailwind 化主线：Projects/Sprint 环境抽屉与动态值选择器的布局、间距和响应式排布迁入 utility，`environment-drawer.module.css` 592 → 318 行，行数 19,014 → 18,736，重复规则体 59 → 57，文件数与 `!important` 不变。阶段 25 删除 UI 测试列表的 `ui-list.module.css`，把工具栏与运行配置徽标整体迁入 utility，文件数 68 → 67、行数 18,736 → 18,657。阶段 26 把 UI 测试集顶栏的工具栏壳、面包屑、动作区与表单容器迁入 utility，`ui-detail-topbar.module.css` 388 → 287 行，行数 18,657 → 18,556。

## 当前基线

| 指标 | 整改前（2026-11-17） | 阶段 3 前 | 阶段 3 完成后 | 阶段 4 第一批后 | 阶段 4 完成后 | 阶段 5 第一批后 | 阶段 5 第二批后 | 阶段 5 完成后 | 阶段 6 完成后 | 阶段 7 完成后 | 阶段 8 完成后 | 阶段 9 完成后 | 阶段 10 完成后 | 阶段 11 完成后 | 阶段 12 完成后 | 阶段 13 完成后 | 阶段 14 完成后 | 阶段 15 完成后 | 阶段 16 完成后 | 阶段 17 完成后 | 阶段 18 完成后 | 阶段 19 完成后 | 阶段 20 完成后 | 阶段 21 完成后 | 阶段 22 完成后 | 阶段 23 完成后 | 阶段 24 完成后 | 阶段 25 完成后 | 阶段 26 完成后 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CSS 文件 | 101 个 | 102 个 | 109 个（新增 7 个 CSS Modules，含运行结果/导入/基础服务连接/项目设置） | 109 个（`page-frame.css` 拆为 `legacy-surface.css` + Sprint feature 样式，文件数不变） | 112 个（新增 shell/antd-overrides/action-buttons/project-overview，删除 workbench/page-frame） | 112 个（删除 Admin 与 Base Services 页面 CSS，新增 3 个 Module） | 112 个（删除 Test Orders 列表 CSS，新增 1 个 Module） | 112 个（删除 Bugs/Test Cases/TestingPage 共 6 个旧 CSS，新增 6 个 Module，净持平） | 112 个（接口库 index.css 替换为 1 个 Module） | 109 个（删除 API 6 个 + UI 8 个旧 CSS，新增 5 + 6 个 Module） | 96 个（删除 AI 22 个 + 组件内 3 个旧 CSS，新增 12 个 Module） | 102 个（+7 拆分文件，-1 `App.css`） | 100 个（删除 Test Orders 9 个旧 CSS，新增 7 个 Module） | 99 个（删除 Test Cases 3 个旧 CSS，新增 2 个 Module） | 97 个（删除 Projects/Sprint 5 个旧 CSS，新增 3 个 Module） | 97 个（不变） | 97 个（4 个旧 CSS 换为 4 个 Module，净持平） | 95 个（删除 2 个 Module） | 93 个（删除 2 个 Module） | 93 个（不变） | 93 个（不变） | 93 个（不变） | 93 个（不变） | 68 个（合并 25 个 Module/全局文件） | 68 个（不变） | 68 个（不变） | 68 个（不变） | 67 个（删除 `ui-list.module.css`） | 67 个（不变） |
| CSS 总行数 | 23,658 行 | 22,732 行 | 22,770 行（作用域化根类前缀增加少量字符） | 22,782 行 | 22,348 行 | 22,039 行 | 22,029 行 | 21,449 行 | 21,427 行 | 21,488 行（Module 作用域与多选择器换行增加 61 行） | 21,673 行（作用域声明与选择器换行增加 185 行） | 21,696 行（拆分文件头增加 23 行） | 21,702 行（Module 头与作用域换行增加 6 行） | 21,706 行（Module 头与合并换行增加 4 行） | 21,714 行（Module 头与合并换行增加 8 行） | 21,423 行（删除外壳/侧栏死规则与重复块） | 21,725 行（4 个 Module 根作用域展开 +302） | 21,566 行（布局迁 utility -159） | 21,423 行（布局迁 utility -143） | 19,881 行（布局迁 utility -1,542） | 19,270 行（布局迁 utility -611） | 19,262 行（删除共享死选择器 -8） | 19,162 行（共享原语分层与死规则收缩 -100） | 19,169 行（合并分隔注释 +7） | 19,015 行（选择器合并 -154） | 19,014 行（收缩 -155） | 18,736 行（环境抽屉/选择器布局迁 utility -278） | 18,657 行（UI 列表模块迁 utility -79） | 18,556 行（UI 顶栏布局迁 utility -101） |
| `!important` | 582 处 | 500 处 | 493 处 | 493 处 | 420 处 | 402 处 | 402 处 | 307 处 | 307 处 | 307 处 | 307 处 | 307 处（不变） | 307 处（不变） | 307 处（不变） | 307 处（不变） | 262 处（删除死规则 45 处） | 262 处（不变） | 262 处（不变） | 262 处（不变） | 253 处（删除重复声明 9 处） | 253 处（不变） | 253 处（不变） | 236 处（删除重复/无效声明 17 处） | 236 处（不变） | 235 处（合并重复声明 1 处） | 95 处（删除冗余声明 140 处） | 95 处（不变） | 95 处（不变） | 95 处（不变） |
| `.app-shell.app-shell-macos` 长前缀 | 164 处 | 165 处 | 163 处 | 163 处 | 125 处 | 125 处 | 125 处 | 121 处 | 121 处 | 121 处 | 121 处 | 121 处（不变） | 121 处（不变） | 121 处（不变） | 121 处（不变） | 101 处（删除死规则 20 处） | 101 处（不变） | 101 处（不变） | 101 处（不变） | 101 处（不变） | 101 处（不变） | 101 处（不变） | 98 处（删除无效分支 3 处） | 98 处（不变） | 98 处（不变） | 0 处（统一单类 `.app-shell-macos`） | 0 处（不变） | 0 处（不变） | 0 处（不变） |
| 重复规则体 | 约 446 组（历史审计口径） | 134 组（结构门禁口径：≥3 条声明且规则体 ≥40 字符） | 134 组 | 123 组 | 116 组 | 115 组 | 115 组 | 111 组 | 110 组 | 110 组 | 110 组 | 110 组（不变） | 110 组（不变） | 110 组（不变） | 110 组（不变） | 109 组（删除重复外壳块 1 组） | 109 组（不变） | 109 组（不变） | 107 组（合并删除 2 组） | 101 组（合并删除 6 组） | 92 组（合并删除 9 组） | 91 组（删除 1 组） | 91 组（不变） | 91 组（不变） | 59 组（合并同文件重复选择器） | 59 组（不变） | 57 组（迁移删除 2 组） | 57 组（不变） | 57 组（不变） |
| 超过 C1 上限（600 行）的文件 | 7 个，合计 9,008 行，占 38% | 7 个 | 5 个，合计 6,048 行，占 26.6% | 5 个，合计 6,019 行，占 26.4% | 5 个，合计 5,288 行，占 23.6% | 5 个，合计 5,289 行，占 24.0% | 5 个，合计 5,289 行，占 24.0% | 4 个，合计 4,232 行，占 19.7% | 4 个，合计 4,201 行，占 19.6% | 4 个，合计 4,203 行，占 19.6% | 4 个，合计 4,203 行，占 19.4% | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 |
| `App.css` feature 导入 | 5 个 | 4 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） | 0 个（`App.css` 已删除） |

历史审计的重复规则体口径更宽，不与结构门禁计数直接比较；后续 ratchet 只使用结构门禁口径。

阶段 3 之前，`src/App.css` 仍聚合 API `overview.css`、UI `index.css`、API `detail.css`、base-services `index.css`；这些文件的 `.api-filter-*`、`.api-collection-*`、`json-editor-*`、`api-case-nav-*` 等类被多个 feature 共用。阶段 3 已按实际消费方拆到共享 Module、共享 surface 层或 owner 组件，`App.css` 只保留 `layout.css`、`legacy-surface.css`、`shell.css`、`antd-overrides.css`、`action-buttons.css`、`theme.css`。阶段 9 删除 `App.css`，这六个导入按原顺序移入 `app/styles/theme.css`，全局层入口只剩一个文件。

Tailwind utilities 位于 `@layer utilities`，旧 CSS 未分层。未分层的普通声明优先于所有分层规则，迁移页面如果还保留旧全局规则，utility 会被覆盖，最终只能靠 `!important` 对抗。本计划因此按“先切断污染，再迁移页面”的顺序执行。

## 新顺序原则

1. **先停增长，再迁移**：新增全局 CSS、`!important`、长前缀先由门禁挡住。
2. **先所有权，再改样式**：跨 feature 共用的样式先拆到正确归属，再迁移页面。
3. **先共享原语，再逐页迁移**：工具栏、列表表面、卡片、分栏、弹窗先有共享实现。
4. **先布局，后皮肤**：Tailwind 负责布局/间距/排版；渐变、阴影、伪元素、动画、AntD 深层结构放 CSS Modules。
5. **先列表/表单，后编辑器，最后图谱**：复杂画布与代码编辑器放最后。
6. **迁移即删除**：一个页面族迁完，同一改动删除原 CSS 文件；不保留双份样式。
7. **预算只降不升**：`!important`、长前缀、重复规则体、文件体积按 baseline ratchet。

## 阶段路线图

| 阶段 | 类型 | 范围 | 主要产出 | 状态 |
| --- | --- | --- | --- | --- |
| 0 | 整改 | 度量与门禁 | CSS 结构检查、预算 ratchet、`verify` 接入 | 已完成 |
| 1 | 整改 | 死 CSS + 安全所有权 | 删除确认死规则；确认 `auth.css` 无跨 feature 依赖 | 已完成 |
| 2 | 迁移 | AuthPage 试点 | Tailwind 布局 + `auth.module.css`，删除 `auth.css` | 已完成 |
| 3 | 整改 | 跨 feature 所有权拆分 | 拆 `overview.css` / `detail.css` / UI/base-services 共享部分；App.css 只剩 shell/tokens | 已完成 |
| 4 | 迁移 | 共享原语 + Shell/Projects | `EntityCard`、`ListSurface`、`PageToolbar`；Projects 卡片迁移；`workbench.css` / `page-frame.css` 拆分与死规则清理 | 已完成 |
| 5 | 迁移 | 列表/工作台 | Bugs、Base Services、Admin、Test Cases、Test Orders、TestingPage 包装层 | 已完成 |
| 6 | 迁移 | 接口库 | 树、列表、编辑器、导入弹窗 | 已完成 |
| 7 | 迁移 | API/UI 自动化详情 | API 列表/详情/请求编辑器；UI 列表/测试集抽屉/详情壳/步骤编辑器/React Flow | 已完成 |
| 8 | 迁移 | AI 测试/生成链 | 需求生成页/生成链弹窗/画布；产物、关系图谱、UI 生成与阶段可视化；Skill 库 | 已完成 |
| 9 | 整改 | 收口 | 删除 `App.css` 聚合；4 个 C1 文件拆分；结构门禁锁 600 行上限；文档收口 | 已完成（结构收口；`!important` / 长前缀 / 重复体未归零，转入后续页面迁移） |

### 阶段 0：门禁

- 新增 `scripts/check-css-structure.mjs` 与 `scripts/css-structure-budget.json`。
- 检查新增全局 CSS、跨 feature CSS 导入、孤儿 CSS、每文件 rules/declarations/selectors 与 600 行上限、重复规则体、共享 Module 私有选择器、Tailwind layer 声明，以及 `App.css` 回归。
- `npm run verify` 增加 `check:css:all`。
- `--update` 只更新计数与重复体 baseline，不自动放行新增全局文件。

### 阶段 1：死 CSS 与安全所有权

- 删除无生产引用、非动态拼接的死规则；分组选择器只删死分支。
- 只做无跨 feature 依赖的安全移动；`auth.css` 经确认只服务 AuthPage，没有移动旧文件，而是在阶段 2 直接迁移并删除。
- `overview.css`、`detail.css`、UI/base-services 的共享类保留全局，等阶段 3 拆分后再移除。

### 阶段 2：AuthPage 试点

- `AuthPage.tsx` 显式导入 `auth.module.css`；布局、间距、排版改用 Tailwind utility。
- 渐变、纹理、玻璃壳、AntD 深层选择器进 `auth.module.css`，不新增 `!important`。
- 旧 CSS 的 `max-width: 900px` 登记为 `--breakpoint-narrow: 900.01px`，统一使用 `max-narrow:`；Tailwind 的 `max-[900px]` 在正好 900px 时不命中，不能直接替代旧断点。
- 删除 `auth.css`、`page-frame.css` 中重复的 `.auth-page` 规则、失效的 layout 测试和测试里的 CSS 导入。
- 验收：`/login`、`/register` 在 1280/900/760、浅色/深色下人工核对；登录/注册表单、错误态、LDAP/本地切换、主题切换正常，无横向溢出。
- 试点结论作为后续页面迁移模板：旧页面 CSS 必须同一改动删除，否则未分层规则会压过 utility；结构性布局用 utility，伪元素/渐变/AntD 深层结构留在 Module；断点等重复值先登记 token。

### 阶段 3：所有权拆分

已完成（2026-11-17）：

- `overview.css`：`:root --tp-action-*` 与 action 按钮过渡移到 `app/styles/buttons.css`；共享页面骨架、筛选控件、卡片皮肤移到 `shared/styles/surface-tokens.css`；仅 API 环境选择器留在 feature 文件，由 `ApiAutomationPage.tsx` 导入。
- UI/用例库：`.api-case-sidebar*`、`.api-case-nav-*` 移到 `test-cases/styles/index.css`；UI 列表样式由 UI 页面自己导入。
- `json-editor-*` 基础皮肤移到 `shared/styles/json-editor.module.css`，保留兼容类供宿主覆盖和测试查询。
- 环境相关：`api-env-var-picker-*` 归 `features/projects/styles/environment-drawer.module.css`，`api-environment-*` 归 `features/projects/styles/environment-drawer.module.css`；项目设置抽屉归 `project-settings.module.css`。
- 运行结果：`api-case-run-result-*`、`api-collection-run-history/report-*` 归 `shared/styles/run-view.module.css`，由历史/报告弹窗与 API 运行控制台提供根类。
- 用例导入：`api-case-import-*` 归 `shared/styles/case-import.module.css`，API、UI、用例库三处复用。
- 基础服务连接卡片：`base-services-connection-*`、`base-services-empty-card`、`base-services-card-scroll` 归 `shared/styles/base-services-connection.module.css`，基础服务、性能监控、AI Skill 库共用。
- `detail.css` 只保留 API 详情专用规则，1,804 → 415 行，由 `ApiCollectionDetailPage.tsx` 导入；`App.css` feature 导入 0 个，只保留 shell 与共享基础层。

共享层仍保留 `api-filter-*`、`api-collection-*` 等旧类名（S7 存量豁免），这是阶段 4 共享原语落地前的过渡；结构门禁已登记 `json-editor-*`、`api-case-run-result-*`、`api-collection-*`、`base-services-*`、`sprint-card-*` 等 shared 兼容类族，后续不得再新增新的 feature 前缀。

浏览器冒烟（2026-11-17）：在 1280/900/760 与浅色/深色下核对 API 列表、基础服务、Skill 库、性能监控、用例库、环境管理抽屉、项目设置抽屉和接口请求体编辑器；布局、筛选控件、卡片、抽屉与 CodeMirror 均正常，无横向溢出。运行历史/报告、用例导入和动态值选择器因当前项目无对应数据未做视觉核对，根类祖先关系已由 Modal/Drawer 探针和组件测试覆盖。

### 阶段 4：共享原语与 Shell

第一批已完成（2026-11-17）：

- `EntityCard` 增加 `className`、`titleAs`、`footerNoteClassName`、`actionsClassName`，继续作为卡片骨架唯一实现。
- 新增 `shared/components/ListSurface.tsx` 与 `PageToolbar.tsx`；`ProjectsPage`、`SprintBoard` 改用共享板面和工具栏，页面只保留标题块、主体与操作。
- `RequirementCards`、`SprintBoard` 改用 `EntityCard`；删除 `requirements-list.css`、`sprint-board.css` 中重复的卡片表面、标题、meta、footer 规则。
- `page-frame.css` 拆分：共享的 `page-frame`、`sprint-card`、加载态和 `requirement-panel-head` 进 `shared/styles/legacy-surface.css`；Sprint 看板与报告样式归 `features/projects/styles/sprint-overview.css`（阶段 9 再拆出 `sprint-dashboard.css`）；删除 `page-frame.css`。补上 `.sprint-dashboard-test-empty` 的跨列规则，修复“本迭代暂无平台执行记录”挤在总数列折行的问题。
- 清理已不反映生产的表格测试夹具：`listSurfaceConsistency` 不再比较需求表，`listNameConsistency` 只保留共享表格名称基线。
- 验证：`npm run verify`、185 个测试文件 / 933 个用例通过；浅色/深色与 1280/900/760 浏览器核对 Projects 列表、需求卡片、迭代卡片和迭代详情。

第二批已完成（2026-11-17）：

- `workbench.css` 拆分并删除：外壳/侧栏/顶栏/通用工作台 → `app/styles/shell.css`，AntD 标签状态色板 → `app/styles/antd-overrides.css`，未分层的动作按钮语言 → `app/styles/action-buttons.css`；Projects 专用变量、概览、空态 → `features/projects/styles/project-overview.css`。
- 删除零引用规则：`.project-requirement-list-*`、`.workbench-project-toolbar*`、`.sprint-card-grid-workbench`、`.sprint-card-title/value/description`、`.requirement-card-grid-workbench`、`.requirements-list-name/-file/-icon`、`.requirement-filter-bar`、`.ui-import-conflict-*` 及旧项目概览 `sprint-card` 覆盖。
- 删除不再反映生产的表格样式测试夹具；`listSurfaceConsistency`、`listNameConsistency` 只保留共享列表基线。
- 指标：`!important` 493 → 420，长前缀 163 → 125，重复规则体 123 → 116，CSS 行数 22,782 → 22,348，C1 5 个文件合计 6,019 → 5,288 行。
- 验证：构建通过；深色/浅色与 1280/900/760 浏览器核对 Projects、需求卡片、迭代看板、迭代详情、API 列表、基础服务、Skill 库和用例库。

后续安排：

- `FilterBar`、`DetailSplit` 跟随首个真实消费方（阶段 6/7）落地，不先建空抽象。
- `@layer` 契约统一与按钮反向压制 `!important` 清零并入阶段 9 收口，避免在页面迁移前改动全局层序。
- 剩余 Stage 4 目标（文件数、重复规则体）由页面迁移自然下降，不为了数字拆碎文件。

### 阶段 5：列表/工作台

第一批已完成（2026-11-17）：

- Admin：`AccountManagementPage` 的工具栏、筛选、表格单元与错误条改用 Tailwind utility；`LdapSettingsPage` 的页面骨架、两列表单、检查区与底部操作条改用 utility，AntD `Form.Item` 间距改用 `[&_.ant-form-item]:mb-4` utility；删除 `account-management.css`、`ldap-settings.css`。
- Base Services：页面壳与内层布局改用 utility；删除 `features/base-services/styles/index.css`。`--base-*` token、卡片/空态皮肤合并进 `shared/styles/base-services-connection.module.css`；禅道绑定与需求仓库关联分别迁入 `zentao-binding.module.css`、`requirement-code-binding.module.css`；删除共享卡片的内联 20px 内距和重复覆盖，卡片计算样式与迁移前一致。
- 修复窄屏外壳：`#root` 加入 ≤900px 的 `height:auto / overflow:visible` 组，LDAP 这类超过一屏的页面可通过 `body` 滚动到保存条；此前 `#root` 的 `height:100%; overflow:hidden` 会裁掉内容。
- 基础服务卡片在 900/760px 下为 2 列、680px 下为 1 列，确认 760–980px 三列问题已消失；`baseServicesGrid.test.ts` 增加 980px 两列断言。
- 指标：CSS 行数 22,348 → 22,039，`!important` 420 → 402，重复规则体 116 → 115；Admin 与 Base Services 页面级 CSS 全部删除。
- 验证：Admin、Base Services 相关 35 个用例通过；浅色/深色与 1280/900/760 浏览器核对账号管理、LDAP、性能监控卡片和 GitLab 空态。

第二批已完成（2026-11-17）：

- Test Orders 列表接入 `ListSurface`，删除 `test-orders-v2.css`；工具栏筛选改用 utility，进度条、状态胶囊与搜索按钮皮肤迁入 `test-orders-list.module.css`，卡片继续使用 `EntityCard`。
- 共享 `DebouncedSearchInput` 首次挂载不再提交空值，避免用户刚翻页就被 300ms 防抖重置回第一页；补充组件单测。
- 列表分页保持 `tp-list-body > table-footer` 契约，`test-orders-card-scroll` 等测试钩子保留。
- 指标：CSS 行数 22,039 → 22,029，文件数保持 112；`!important` 与长前缀维持 402/125，其中搜索框的 2 处 `!important` 是暂时压过 `testing/styles/index.css` 的旧外壳规则，等 TestingPage 包装层迁移后删除（第三批已删除）。
- 验证：Test Orders 页面、分页一致性、搜索框单测通过；1280/760 浏览器核对工具栏、空态和窄屏换行。

第三批已完成（2026-11-17）：

- Bugs：列表、详情、新建/编辑表单与禅道导入分别迁入 `bugs.module.css`、`bugs.module.css`、`bugs.module.css`，删除 `bugs-v2.css`、`bug-detail.css`、`bug-form.css`、`bug-import.css`；旧类名保留为测试与兼容钩子，详情专属根规则用 `.bugs-detail-page` 限定，避免列表被详情布局污染。
- Test Cases：`case-library-v2.css` 迁入 `case-library.module.css`；表格壳、左栏树、工具栏与空态保持原钩子，`case-library-title-cell` 等列样式留在 Module。
- TestingPage：标签外壳迁入 `testing-page.module.css`，保留页面常驻挂载与 `hidden` 切换；删除 `features/testing/styles/index.css`。
- 共享收敛：需求文档预览迁入 `requirements/styles/requirement-detail.module.css`；功能测试列表的共用字阶/颜色/名称列规则迁入 `shared/styles/list-table.css`；API/性能列表的工具栏内部排布迁入 `shared/styles/surface-tokens.css`；删除测试单搜索框的 2 处 `!important` 兼容覆盖。
- 测试夹具：`listSurfaceConsistency` 与 `listNameConsistency` 不再读取已删除的 testing CSS，只使用共享 `list-table.css` / `list-name.css`。
- 指标：CSS 行数 22,029 → 21,449，`!important` 402 → 307，长前缀 125 → 121，重复规则体 115 → 111；C1 超标文件 5 → 4（合计 5,289 → 4,232 行）。
- 验证：Bugs 77 个用例、Test Cases 25 个用例、TestingPage 4 个用例与两份共享列表样式测试通过；1280/760 浏览器核对用例库、Test Orders、Bugs、API、UI、性能测试、需求文档预览与窄屏滚动；浅色主题下未发现布局回归，深色由 token 层与既有测试覆盖。


### 阶段 6：接口库

已完成（2026-11-17）：

- 接口库详情工作区、软件仓库树、参数/请求头/请求体/响应/设置面板与分组弹窗统一迁入 `features/interface-library/styles/interface-library.module.css`；页面根、Modal 与 Drawer 根都挂 `.scope`，保留 `interface-library-page`、`if-*` 旧钩子。阶段 9 再按列表/方法签/OpenAPI/详情壳/编辑器拆为 5 个 Module，入口根节点改挂五个作用域。
- 软件仓库管理页和新建/编辑抽屉复用同一 Module；列表工具栏、`tp-list-body` / `tp-list-scroll` 与表头行高保持原值。
- OpenAPI 导入弹窗通过 `rootClassName={styles.scope}` 取得同一套 `if-import-*`、方法签和 JSON 状态样式。
- 删除 `features/interface-library/styles/index.css`；清除 `if-switch-line`、`if-app-name em`、`if-app-child em`、`if-app-name-cell .ant-tag` 等零引用规则。
- 指标：CSS 总行数 21,449 → 21,427，`!important` 保持 307，长前缀保持 121，重复规则体 111 → 110，全局 CSS 92 → 91；接口库文件 1,585 → 1,554 行，C1 文件数保持 4。
- 验证：接口库 feature 45 个用例、全量 187 个测试文件 / 937 个用例通过；`npm run verify`、CSS 双门禁、主题检查通过；1280/760 浅色/深色浏览器核对工作区、软件仓库列表、编辑抽屉、OpenAPI 导入弹窗和窄屏滚动。

### 阶段 7：API/UI 自动化详情

已完成（2026-11-17）：

- API 自动化：列表、详情壳、请求编辑器、请求头/请求体面板与规则/环境弹层分别迁入 `api-list.module.css`、`api-detail-shell.module.css`、`api-detail-shell.module.css`、`api-detail-request.module.css`、`api-detail-rules.module.css`；删除 `overview.css`、`list-v2.css`、`detail.css`、`detail-workbench-v2.css`、`detail-inspector-v2.css`、`detail-request-panels-v2.css`。
- API 作用域：列表页与详情页根节点挂 Module `.scope`；方法下拉通过 Select `classNames.popup.root`、环境 Popover 通过 `overlayClassName`、断言/提取规则 Modal 通过 `rootClassName` 把作用域带进 portal。
- UI 自动化：列表工具栏、测试集/步骤编辑器共享皮肤、详情壳、左栏流水线、右栏检查器与 React Flow 画布分别迁入 `ui-list.module.css`、`ui-suite.module.css`、`ui-detail-shell.module.css`、`ui-detail-shell.module.css`、`ui-detail-inspector.module.css`、`ui-execution-flow.module.css`；原 `step-editor-layout.css`、`suite-drawer-layout.css` 并入共享 Module；删除 8 个旧 CSS。阶段 9 再把详情顶栏拆到 `ui-detail-topbar.module.css`。
- UI 作用域：`UiAutomationPage` 同时挂列表与共享步骤样式作用域；`UiTestSuiteCasePage` 挂 5 个详情 Module；测试集 Drawer 在其 `className` 上追加作用域，缺失变量 Modal 在 `className` 上追加作用域；React Flow 仍由详情页根作用域覆盖宿主布局与节点样式。
- 测试夹具：API 请求面板与地址条测试改为读取新的 Module raw CSS；UI 自动化 70 个现有用例不需要改查询钩子。
- 指标：CSS 文件 112 → 109，全局 CSS 91 → 77；`!important` 保持 307，长前缀保持 121，重复规则体保持 110；总行数 21,427 → 21,488（Module 作用域声明与多选择器换行带来的格式开销），C1 文件保持 4 个（4,201 → 4,203 行）。
- 验证：API 36 个、UI 70 个 feature 用例通过；全量 188 个测试文件 / 943 个用例、`npm run verify`、CSS 双门禁与主题检查通过；1280 浅色/深色核对 API 列表/详情，1280/760 浅色/深色核对 UI 列表/详情、测试集抽屉、步骤编辑器与流程画布，760 复核 API 详情；深色下终端与表面 token 正常。

### 阶段 8：AI 测试/生成链

已完成（2026-11-17）：

- 需求生成页、生成链弹窗、画布与阶段检查器迁入 `ai-task-detail.module.css`、`generation-chain.module.css`、`generation-canvas.module.css`；`RequirementDetailPage` 根节点统一挂生成链/画布/产物/图谱/UI 生成/阶段可视化作用域，`GenerationArtifactFrame` 与图谱/导入弹窗各自在 `rootClassName` 上带作用域。
- 产物视图按职责拆分：用例树/浏览器/审核字段在 `artifact-cases.module.css`，API 配置/设计在 `artifact-api.module.css`，仓库画像/模块进度/YAML 问题在 `artifact-misc.module.css`；关系图谱与查看器合并为 `relations.module.css`，测试单图谱继续复用同一 Module。
- UI 生成来源、输入弹窗、用例选择器与模型连接弹窗合并为 `ui-generation.module.css`；UI 三阶段可视化迁入 `ui-stage-visual.module.css`，深色 `:root[data-theme="dark"]` 规则改为 `:root[data-theme="dark"] .scope` 作用域。
- Skill 库页面与运行记录/代码风险分别迁入 `ai-page.module.css`、`ai-task-detail.module.css`；原散在 `components/` 下的 `RevisionSidePanel.css`、`FunctionalCaseRelationsViewer.css`、`FunctionalCaseRelationsGraph.css` 一并并入 `styles/` Module。
- `TestOrderGraphViewer` 继续复用 AI 的关系图谱 Module，作为既有跨 feature 导入保留在结构门禁基线；变化只是导入路径从组件 CSS 换成 `relations.module.css`。
- 删除 22 个 `styles/*.css` 与 3 个组件内 CSS，新增 12 个根作用域 Module；组件不再直接引入全局 CSS。测试夹具改为读取 Module raw CSS 并在测试 DOM 外层补 `.scope`。
- 指标：CSS 文件 109 → 96，全局 CSS 77 → 52；`!important` 保持 307，长前缀保持 121，重复规则体保持 110；总行数 21,488 → 21,673（作用域声明与选择器换行增加 185 行），C1 文件保持 4 个（4,203 行）。
- 验证：AI feature 47 个测试文件 / 265 个用例、全量 188 个测试文件 / 943 个用例、`npm run verify`、CSS 双门禁与主题检查通过；1280 浅色/深色核对需求生成画布、需求评审阅读态、UI 生成弹窗与代码风险弹窗，760 深色核对生成画布堆叠，Skill 库深色 1280 核对；生成链节点、阅读态侧栏、弹窗步骤条与空态均正常。

### 阶段 5-8：页面族迁移

按“列表/表单 → 接口库 → API/UI 自动化 → AI 测试/生成链”的顺序。每个页面族必须同时完成：

- 旧 CSS 文件删除；
- 共享原语复用；
- 浅色/深色、1280/900/760 浏览器验收；
- 文档实现位置更新；
- 预算下降或不变。

### 阶段 9：收口

已完成（2026-11-17）：

- 删除 `src/App.css`，六个全局层导入按原顺序移入 `app/styles/theme.css`；结构门禁移除 `App.css` 特判，新增「`src/App.css` 不得回归」与「单文件 ≤600 行」检查。
- 4 个 C1 文件全部拆到 600 行以内：
  - 接口库 `interface-library.module.css` 1,554 行拆为列表/仓库、方法签、OpenAPI 导入、详情壳、编辑器 5 个 Module；五个入口页/组件统一挂五个 `.scope`。
  - `shell.css` 980 行按「基础结构 / 共享色板与顶栏」拆为 `shell.css`（591）+ `shell-header.css`（391），`theme.css` 按原顺序导入。
  - `sprint-overview.css` 975 行按「页面骨架 / 看板指标、图表、报告与响应式」拆为 `sprint-overview.css`（456）+ `sprint-dashboard.css`（521），`SprintDetailPage` 顺序导入。
  - `ui-detail-shell.module.css` 694 行把顶栏抽为 `ui-detail-topbar.module.css`（393），壳保留板面/控制条/窄屏（304）；`UiTestSuiteCasePage` 根节点挂新作用域。
- `foundation-tokens.css` 的 28 个 `--legacy-*` 全部仍被 `shell.css` / `shell-header.css`、`projects-overview.module.css`、`action-buttons.css` 消费，没有死 token；本阶段不删除仍被引用的别名，等对应外壳/项目概览迁移时再一并替换。
- 指标：CSS 文件 96 → 102（+7 拆分，-1 `App.css`），总行数 21,673 → 21,696（新文件头 +23），全局 CSS 52 → 53；C1 4 → 0；`!important` 307、长前缀 121、重复规则体 110 保持不变。
- 未完成的目标：文件 ≤45、行数 ≤9,000、`!important` ≤100、长前缀 0、重复规则体 ≤60。剩余 `!important` 主要集中在 `shell-header.css`、`buttons.css`、`antd-overrides.css`、`action-buttons.css` 等外壳与 AntD 覆盖层；121 处长前缀中 104 处在 `app/styles/`。这些规则用于压过 AntD/旧全局层，直接去前缀或去 `!important` 会改变同权重级联顺序，必须随剩余页面族（Test Orders 工作区、Test Cases 编辑器、Projects/Sprint 看板、shared 表格/按钮层）继续迁到 Tailwind/Module 时逐页浏览器对照，不能在本阶段靠机械替换清零。重复规则体的 110 组也以 flex/gap/ellipsis 微布局为主，需要在页面迁移时改成 Tailwind utility 才会自然消失。
- 验证：接口库/UI 自动化/Sprint 详情定向 18 个测试文件 / 118 个用例通过；全量 188 个测试文件 / 942 个用例、`npm run verify`、CSS 双门禁与主题检查通过；1280/760 浅色与深色浏览器冒烟覆盖接口库、UI 测试集详情、Sprint 详情和全局外壳。

### 阶段 10：Test Orders 工作区

已完成（2026-11-18）：

- 旧 9 个 CSS 全部迁为根作用域 Module：`test-order-workspace.module.css`（页面高度链、详情外壳、摘要、前置条件与步骤）、`test-order-workspace.module.css`（工具栏、执行条目表格、筛选弹层与批量条）、`test-order-graph-execution.module.css`（判定、缺陷与底栏）、`test-order-workspace.module.css`（加入用例弹窗）、`test-order-graph.module.css`（图谱页壳与查看器）、`test-order-graph-execution.module.css`（图谱执行面板）、`test-order-visualization.module.css`（可视化与批量图解）。
- 删除 `workspace-v2.css`、`workspace-list-v2.css`、`workspace-verdict-v2.css`、`workspace-content-v3.css`、`index.css`、`graph-page.css`、`graph-viewer.css`、`graph-execution.css`、`case-visualization.css`；`features/test-orders` 下不再有非 Module CSS，组件不再直接引入全局 CSS。
- 作用域接线：工作台页面根同时挂 workspace / workspace-list / verdict 三个 `.root`；加入用例 Modal 与外层详情 Modal 通过 `rootClassName` 挂弹窗 Module 的 `.root`；图谱页壳、查看器与执行面板分别挂各自 Module 的根类；可视化面板与批量按钮分别挂 `.panel` / `.batch`。旧类名全部保留为 `:global()` 测试与兼容钩子；高度链用 `:global(.app-shell):has(.root)` 与 `:global(.app-content):has(.root)` 保持原选择器作用。
- 级联顺序：图谱执行面板单独成文件，保持“执行面板 → `relations.module.css` → 查看器”的原加载顺序，避免查看器规则被关系图谱 Module 反向覆盖。
- 删除 `TestOrderPage.tsx` 对 `styles/index.css` 的死导入；`TestOrderEntryList`、`TestOrderCaseContent`、`TestOrderVerdictButtons` 不再直接引入旧样式。
- 指标：CSS 文件 102 → 100，全局 CSS 53 → 44，总行数 21,696 → 21,702（Module 头与作用域换行 +6）；`!important` 307、长前缀 121、重复规则体 110 保持不变；C1 超标文件保持 0。
- 验证：test-orders 10 个测试文件 / 71 个用例、全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；浏览器覆盖 1280/900/760 与浅色/深色下的工作台列表、详情、筛选弹层、加入用例弹窗、内嵌图谱、独立图谱页和可视化面板，关键计算样式与迁移前一致。
- 未覆盖：当前测试单没有已生成图谱，图谱执行面板的实际渲染未做视觉核对；其样式与工作台判定控件共用 `test-order-graph-execution.module.css`，执行面板自身的布局规则已由计算样式与类名接线确认。

### 阶段 11：Test Cases 编辑弹窗与推送

已完成（2026-11-18）：

- `case-editor-v2.css` 迁为 `case-library.module.css`；弹窗 `className` 同时带 `case-library-case-modal tp-surface` 与 Module `.root`，24 处压 AntD 输入/选择控件的 `!important` 暂时原样保留，等阶段 13 统一审计。
- `index.css` 合并进 `case-library.module.css`：页面骨架、测试集侧栏与 `api-case-*` 规则改为 `.root :global(...)`；合并块放在原 Module 规则之前，保持原来“index.css 先、case-library.module.css 后”的同权重级联顺序，并核对了 `case-library-main`、`case-library-nav-*`、`case-library-sidebar-foot` 的 5 处冲突属性。
- `case-push.css` 迁为 `case-library.module.css`；`ProjectActionModal` 通过 `rootClassName` 挂 `.root`，`CasePushModal` 不再直接引入全局 CSS。
- 删除 `features/test-cases/styles/index.css`、`case-editor-v2.css`、`case-push.css`；`features/test-cases` 只保留 `case-library.module.css`、`case-library.module.css`、`case-library.module.css`。
- 指标：CSS 文件 100 → 99，全局 CSS 44 → 41，总行数 21,702 → 21,706；`!important` 307、长前缀 121、重复规则体 110 保持不变；C1 超标文件保持 0。
- 验证：test-cases 6 个测试文件 / 45 个用例、全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁、主题检查通过；浏览器覆盖 1280/900/760 与浅色/深色下的用例库列表、测试集侧栏、编辑弹窗和导入禅道弹窗，900px 以下编辑表单收为单列，页面无横向溢出。
- 未覆盖：导入禅道弹窗只核对了目标表单初始态与 Module 作用域，未执行真实预览/推送；未决核对区由现有组件测试与后端协议覆盖。

### 阶段 12：Projects / Sprint 看板

已完成（2026-11-18）：

- `sprint-overview.css` → `sprint-overview.module.css`（456 行），`sprint-dashboard.css` → `sprint-overview.module.css`（522 行），保持原导入顺序；Sprint 详情页根节点同时挂两个 Module 的 `.root`。
- `requirements-list.css`、`sprint-board.css`、`project-overview.css` 合并为 `projects-overview.module.css`（171 行），规则顺序保持 requirements-list → sprint-board → project-overview；Projects 页面根节点挂 `.root`，RequirementCards / SprintBoard 不再直接引入全局 CSS。
- 报告 Modal 的 `className` 追加 dashboard Module `.root`，报告 Drawer 通过 `rootClassName` 挂同一作用域；`:root:root` 长链与 `#root .requirements-page` 规则按原权重改写。
- 删除 5 个旧 CSS；`features/projects` 只保留 `projects-overview.module.css`、`sprint-overview.module.css`、`sprint-overview.module.css` 及既有表单/抽屉 Module。
- 指标：CSS 文件 99 → 97，全局 CSS 41 → 36，总行数 21,706 → 21,714；`!important` 307、长前缀 121、重复规则体 110 保持不变；C1 超标文件保持 0。
- 验证：projects 16 个测试文件 / 46 个用例、全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁与主题检查通过；浏览器覆盖 1280/900/760 与浅色/深色下的迭代看板、需求卡片、Sprint 详情健康带/执行概览/趋势区，760px 单列且无横向溢出。
- 未覆盖：报告 Modal 与 Drawer 因当前迭代没有快照/报告数据未实际打开；作用域接线由类型检查、构建与组件测试覆盖，后续有报告数据时补一次视觉核对。

### 阶段 13：App Shell / AntD / 按钮层冗余清理

已完成（2026-11-18）：

- 删除旧侧栏与项目头死层：`shell.css` / `shell-header.css` 中 `.app-sider`、`.brand-row`、`.project-actions`、`.project-selector-label` / `.project-separator`、`.project-selector-divider`、`.settings-page`、`.app-header-feedback` 及重复的 base-services / macOS 侧栏块；`.app-sider` / `.brand-row` 在 TS/TSX 中已零引用。
- 删除已无消费方的按钮/标签分支：`action-buttons.css` 的 `.ai-testing-overview-page`、`.ai-testing-hero-action`、`.api-case-import-trigger`、`.json-editor-toolbar-link`、`.action-btn-run`；`buttons.css` 的 `.service-card-actions`；`antd-overrides.css` 的 `.sprint-card-status` / `.zentao-binding-summary-tag` 入口；`theme.css` 的 `.app-search-field`。
- 保留承重规则：`.json-editor-toolbar-btn.ant-btn`、`.sprint-card-actions`、`.app-action-run`（由 `ActionButton operation="run"` 动态生成）等仍在消费的选择器不删；`!important` 与 `.app-shell.app-shell-macos` 前缀只随死规则消失，不做机械替换。
- 指标：CSS 文件 97（不变），全局 CSS 36（不变），总行数 21,714 → 21,423（-291）；`!important` 307 → 262（-45），长前缀 121 → 101（-20），重复规则体 110 → 109；C1 超标文件保持 0。
- 验证：全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁（基线已收紧）、主题检查与 `git diff --check` 通过；浏览器覆盖 1280/900/760 与浅色/深色下的顶栏、项目/迭代选择、按钮层、项目下拉、新建迭代 Drawer、新建项目 Modal、删除 Popconfirm，760px 无横向溢出。

### 阶段 14：Shared / Token 清理与最后 4 个小文件

已完成（2026-11-18）：

- `requirements/styles/detail.css` → `requirement-detail.module.css`（需求详情页根挂 `.root`，面包屑/主画布/阶段侧栏/文档工作区规则改为 `.root :global(...)`；`RequirementDetailHeader` 不再直接 import 页面 CSS）。
- `profile/pages/ProfilePage.css` → `profile/styles/profile-settings.module.css`（个人设置与独立修改密码页共用；两页根节点都挂 `.root`，`auth` 保留对 profile Module 的跨 feature 导入这一项显式豁免）。
- `base-services/styles/zentao-mcp-service.css` → `zentao-mcp-service.module.css`（MCP 卡片根挂 `.root`，标题/状态/实例省略规则改为作用域选择器）。
- `auth/styles/change-password.css` → `change-password.module.css`（独立修改密码页同时挂 profile 与 change-password 两个 `.root`，保留 720px 单栏与单列网格）。
- 删除 4 个旧 CSS；`src/features` 下不再有非 Module CSS，非 Module CSS 只剩 `app/styles`、`shared/styles`、`shared/components/RichTextEditor` 与入口 `index.css`，共 32 个文件。
- `--legacy-*` 审计：28 个别名全部有且仅有一处消费（`shell.css` 5、`shell-header.css` 13、`projects-overview.module.css` 9、`action-buttons.css` 1），没有死 token，全部保留；此前文档记作 27 个，已按实际定义更正。
- 指标：CSS 文件 97（4 删 4 增），全局 CSS 36 → 32，总行数 21,423 → 21,725（Module 根作用域展开 +302）；`!important` 262、长前缀 101、重复规则体 109 保持不变；C1 超标文件保持 0；跨 feature CSS 导入保持 2。
- 验证：requirements/base-services/auth 定向 10 个测试文件 / 47 个用例、全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；浏览器覆盖需求详情（1280 浅色、900 浅色、760 深色）、个人设置（1280 浅色、900、760 深色）、修改密码（1280 浅色、760 深色）与禅道 MCP 卡片（1280 浅色、760 深色），根作用域、栅格、输入/按钮尺寸与卡片省略均生效，无横向溢出。

### 阶段 15：Tailwind 化试点（个人设置 / 修改密码 / 禅道 MCP）

已完成（2026-11-18）：

- `profile-settings.module.css` 只保留渐变、卡片表面、阴影与 AntD 深层结构；个人设置和修改密码的页面 padding、栅格、标题/正文间距、字段与操作条排布迁为 Tailwind utility。
- 删除 `auth/styles/change-password.module.css`：修改密码页复用 profile Module 皮肤，720px 单栏与单列网格直接由 utility 表达。
- 删除 `base-services/styles/zentao-mcp-service.module.css`：MCP 卡片的标题 flex、状态条高度与实例省略由 `ZentaoMcpServiceCard.tsx` 的 utility 负责。
- 修正样式层级：`antd/dist/reset.css` 从 `main.tsx` 的未分层导入移到 `src/index.css` 的 `layer(reset)`，层顺序改为 `theme, base, antd, reset, components, utilities`；reset 仍压过 AntD 组件默认字重，但 utility 可以覆盖 reset。结构门禁同步校验 reset 的 layer 归属。
- 登记 `--breakpoint-narrow-md: 1000.01px` 与 `--breakpoint-narrow-sm: 760.01px`，保证 1000/760px 边界与旧 `max-width` 规则一致。
- 指标：CSS 文件 97 → 95，总行数 21,725 → 21,566（-159），全局 CSS 保持 32；`!important` 262、长前缀 101、重复规则体 109 保持不变。
- 验证：base-services/auth 定向 10 个测试文件 / 47 个用例、全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；浏览器覆盖个人设置（1280 浅色/深色、900、760 浅色）、修改密码（1280 浅色、760 深色）与禅道 MCP 卡片（1280 浅色、760 深色）；回归确认 Projects 默认标题在 reset 分层后仍保持原字重，页面无横向溢出。

### 阶段 16：列表/弹窗 Module Tailwind 化

已完成（2026-11-18）：

- TestingPage 的标签外壳与 pane 子页布局改为 utility；`hidden` 与 `flex` 按活动页二选一，避免 display utility 互相覆盖；删除 `testing-page.module.css`。
- 项目设置抽屉的 body padding 改用 Drawer `styles.body`，三行设置项与复制区改用 flex/gap/min-width utility；删除 `project-settings.module.css`。
- 导入禅道弹窗保留 AntD 深层规则与分隔线，body/toolbar/选择宽度/标题布局迁为 utility。
- 加入用例弹窗保留文字与步骤圆点皮肤，筛选行、详情栅格、步骤行布局迁为 utility。
- 测试单列表保留进度条/状态胶囊皮肤，搜索框宽度、900px 断点与进度行布局迁为 utility。
- 指标：CSS 文件 95 → 93，总行数 21,566 → 21,423（-143），全局 CSS 保持 32；`!important` 262、长前缀 101、重复规则体 109 → 107。
- 验证：test-orders 10 个测试文件 / 71 个用例、test-cases/projects/testing 23 个测试文件 / 95 个用例、全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；浏览器覆盖测试工作台（1280、760、680px 边界）、项目设置抽屉、测试单列表（1280/900 搜索框与进度行）、导入禅道弹窗初始态与加入用例弹窗详情预览；导入禅道的预览表格因本地禅道 MCP 返回“工具执行失败”未进入，布局类已由组件测试和构建覆盖。

### 阶段 17：列表与看板页 Tailwind 化

已完成（2026-11-18）：

- Projects/Sprint：需求卡片、迭代看板与 Sprint 详情把卡片行、标题/状态/进度排版、健康带与指标网格、趋势图容器及 600/768/900/1200/1280 边界迁入 utility；`projects-overview`、`sprint-overview`、`sprint-dashboard` 三个 Module 收缩为皮肤与 Recharts/AntD/Markdown 深层规则。
- 用例库：两栏 grid、测试集导航、筛选/快速过滤、选中条与表头行布局迁入 utility；保留侧栏渐变、选中态、等宽徽标与优先级色块皮肤。共享 `tp-list-toolbar` 的搜索框 288px 宽度已在阶段 19 迁到页面 `w-72` utility。
- 测试单工作台：列表工具栏、进度色条、批量条、详情骨架、前置条件/步骤排版、判定区与底部操作条迁入 utility；保留进度段选中态、判定按钮色调、步骤表表面与 AntD 深层结构。用例编号的等宽字体仍留在 Module，因为未分层的 `button { font-family: inherit }` 会压过 utility。
- 指标：CSS 文件 93 保持不变，总行数 21,423 → 19,881（-1,542），`!important` 262 → 253，长前缀 101 不变，重复规则体 107 → 101。
- 验证：projects 16 个测试文件 / 46 个用例、test-cases 6 / 45、test-orders 10 / 71、全量 188 / 944、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；浏览器覆盖 Projects 需求/迭代（1280、760、680 边界、浅/深色）、Sprint 详情（1440、1280、1000、760、600、浅/深色）、用例库（1280、900、760、浅/深色、900 条数据）与测试单列表/详情（1280、760、浅/深色、批量条与判定条）。

### 阶段 18：复杂详情/AI/图谱 Tailwind 化（已完成）

已完成（2026-11-18），按四个子批推进：

- 需求详情：页面高度链、面包屑、主/侧栏骨架与 840/900px 堆叠迁入 `RequirementDetailPage` / `RequirementDetailHeader` utility；`requirement-detail.module.css` 218 → 122 行，只保留链接/工具栏表面、侧栏动画、画布与文档容器深层结构。
- API 测试集详情：两栏网格、1180px 堆叠、顶栏、用例列表行、编辑器表单/请求栏/键值行与控制台骨架迁入页面/组件 utility；`api-detail-shell.module.css` 325 → 176 行、`api-detail-shell.module.css` 586 → 395 行，只保留卡片表面、环境 chip、方法徽标、悬停/选中态、CodeMirror/AntD 深层结构。
- UI 测试详情：7:5 双栏、1180px 堆叠、画布/步骤编辑器与检查器骨架、缺失变量弹窗排版迁入 utility；`ui-detail-shell.module.css` 304 → 211 行。堆叠时网格不再参与剩余高度拉伸，恢复「整页滚动」，修掉 1180px 以下画布与检查器重叠。
- 关系图谱：页面栏、图例、正文与 JSON 视图骨架迁入 `FunctionalCaseRelationsViewer` / `TestOrderGraphViewer` utility；`relations.module.css` 417 → 351 行，只保留图谱/节点皮肤、图例线与 JSON 深层结构。
- AI 生成链：全景根节点、标题栏工具槽与弹窗标题排版迁入 utility；`generation-chain.module.css` 435 → 419 行，`generation-canvas.module.css` 的 `.gc-canvas-panorama` 只保留画布背景覆盖，间距/内边距/溢出改由 utility 承担。
- 指标：CSS 19,881 → 19,270 行（-611），`!important` 253、长前缀 101 不变，重复规则体 101 → 92，文件数 93 不变。
- 验证：requirements 5 个测试文件 / 22 个用例、api-automation 8 / 36、ui-automation 13 / 70、ai-testing 47 / 265、test-orders 10 / 71，全量 188 / 944、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；浏览器覆盖需求详情（1280/760、浅/深色、画布）、API 详情（1280 浅/深色、1000 堆叠）、UI 详情（1280 浅/深色、1000/760 堆叠整页滚动）、测试单图谱（1280 浅/深色）与 AI 生成全景（1280 浅/深色、760 画布）。

### 阶段 19：共享层审计与指标收口（已完成）

已完成（2026-11-18），只做安全收缩：

- `tp-list-toolbar` 审计：删除已无引用的 `.test-orders-search-field` 与 `.ai-task-*` 选择器；四处搜索框的 288px 宽度迁到页面 `w-72` utility（API 两页保留 `min-w-[240px]`，UI 列表的 256px 下限因共享 `.api-filter-field { min-width: 0 }` 未分层仍留在 feature Module）。
- 预算收紧：`scripts/css-budget.json` 与 `scripts/css-structure-budget.json` 以当前值重建，`!important` 基线 262 → 253、重复规则体 107 → 91、长前缀 101 不变。
- 当时保留的未分层契约：全局控件字体、`.tp-tone-tag` 的 `display`、`.api-filter-field` 的 `min-width`。阶段 20 已处理：删除重复的控件字体覆盖、把 tone tag 与 filter 原语移入 `@layer components`。
- 指标：CSS 19,270 → 19,262 行（-8），重复规则体 92 → 91，文件数 93、`!important` 253、长前缀 101 不变。
- 验证：受影响的 performance/api-automation/ui-automation/test-cases 34 个测试文件 / 183 个用例、全量 188 / 944、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；浏览器复核 API/UI 列表与用例库搜索框 1280/760 宽度。
- 验收边界：本阶段以「安全收缩 + 基线 ratchet」为完成口径，不以结束指标为验收；剩余 `!important` 主要在 AntD 深层皮肤，文件数与行数目标需要后续按模块合并/删除专项推进。

### 阶段 20：共享原语分层与死规则收缩（已完成）

已完成（2026-11-18），分三个子批：

- 20A 控件与胶囊：删除 `src/index.css` 中与 AntD reset 重复的控件字体覆盖；`.tp-chip`、`.tp-tone-tag` 移入 `@layer components`，去掉 `.tp-chip` 的 `font: inherit`。用例库类型标签改用 `inline-block align-middle max-w-full`，测试单图谱标题胶囊改用 `whitespace-normal`，删除两个 Module 覆盖。
- 20B 筛选与工具栏：`.api-filter-field`、`.api-filter-group`、`.api-filter-field-label`、`.tp-list-toolbar` 及其子规则移入 `@layer components`；UI 列表搜索框的 256px 下限改用 `min-w-64 max-narrow:w-full max-narrow:min-w-0`，删除 Module 中的 900px 规则。`app-buttons` 加入 `tailwind.css` 层顺序（`components` 与 `utilities` 之间）并同步结构门禁；两个直接注入共享 CSS 的 jsdom 测试增加 layer 解包 helper。
- 20C 死规则：删除 `shell-header.css` 的 base-services 镜像块与重复 header/选择器声明，`surface-tokens.css` 的无引用 `.tp-chip-count`、重复 filter 规则、无效 macOS list-scroll 分支和 refresh `!important`，以及 `list-table.css` 中与物理圆角重复的逻辑圆角声明。
- 指标：CSS 19,262 → 19,162 行（-100），`!important` 253 → 236（-17），长前缀 101 → 98（-3），重复规则体 91 不变，文件数 93 不变；两个预算基线已 ratchet。
- 验证：全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；浏览器覆盖 1280/900/760 浅/深色外壳、基础服务主题、测试单表格/工具栏/按钮、UI 列表搜索框、用例库标签与图谱标题胶囊。构建产物确认 `app-buttons` 位于 `utilities` 之前。

### 阶段 21：同根/同宿主 Module 合并（已完成）

已完成（2026-11-18），只做不改变作用域与导入顺序的合并：

- 测试单：`test-order-workspace-list` 并入 `test-order-workspace`，`add-cases-modal` 并入 `test-order-workspace`，`test-order-verdict` 并入 `test-order-graph-execution`。
- Projects：`sprint-dashboard` 并入 `sprint-overview`；`dynamic-value-picker` 并入 `environment-drawer`。
- API / UI：`api-detail-editor` 并入 `api-detail-shell`；`ui-detail-pipeline` 并入 `ui-detail-shell`。
- Bugs：`bug-form`、`bug-import` 并入 `bugs`。
- 接口库：`interface-method`、`interface-openapi` 并入 `interface-detail`，五个 Module 收缩为三个。
- 用例库：`case-editor`、`case-push` 并入 `case-library`。
- 需求：`document-preview` 并入 `requirement-detail`。
- AI：`artifact-view-switch` 并入 `ui-stage-visual`，`requirement-design` 并入 `ai-task-detail`，`artifact-view-host` 并入 `artifact-misc`。
- 共享/全局：`artifact-view` 并入 `run-view`，`editor-tokens` 并入 `chart-tokens`，`legacy-tokens` 并入 `foundation-tokens`，`shell-boundary` 并入 `theme.css`，删除 `app/styles/index.css`（`main.tsx` 直接导入 `src/index.css`）；`error-boundary`、`ldap-settings`、`asset-library` 改为 utility。
- 指标：CSS 文件 93 → 68（-25），行数 19,162 → 19,169（合并分隔注释 +7），`!important` 236、长前缀 98、重复规则体 91 不变；预算基线已按 68 个文件重算。
- 验证：全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；浏览器抽查测试单工作台、Sprint 详情、API 详情、UI 详情、需求详情、用例库/资产库、Bug 列表与 LDAP 表单。

### 阶段 22：同文件重复规则体合并（已完成）

已完成（2026-11-18）。结构门禁的 91 组重复规则体中，先处理同一文件内规则体完全一致、且移动后不会跨过同主体同属性竞争规则的选择器：

- 把同一文件、同一规则体的选择器合并为一个选择器列表，例如 AI 产物视图的省略号规则、API 详情的小圆点/等宽 meta/标签计数、接口库的导入字段标题、Bug 附件与证据上传网格、UI 步骤双列网格、Run 视图的历史/报告标题、富文本引用/代码块/图片、暗色 tone 与 Sprint 图表 tooltip。
- 仅在确认没有 `@media` 上下文差异、且被移动选择器在中间规则中不存在同主体同属性覆盖时执行；跨文件重复与需要改组件 DOM 的 32 组保持不动，留待后续 utility 迁移。
- 指标：重复规则体 91 → 59（-32），`!important` 236 → 235（合并 1 处重复声明），行数 19,169 → 19,015（-154），文件数 68、长前缀 98 不变；两个预算基线已 ratchet 到 59 组 / 235 处。
- 验证：`npx tsc --noEmit`、全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；浏览器在 1280/900/760 下核对测试单工作台表头 42px、无横向溢出，浅/深色主题切换、API 详情圆点与标签计数、UI 测试集步骤网格、需求详情画布、接口新建页、用例库与 Sprint 图表。

### 阶段 23：外壳前缀归一与 `!important` 收缩（已完成）

已完成（2026-11-18）。只做能用级联顺序和更窄选择器替代的声明，不改变可见样式：

- 把 12 个 CSS 文件中的 98 处 `.app-shell.app-shell-macos` 统一为单类 `.app-shell-macos`；外壳布局在 1400/1280/900/760 下的 header/main/nav/project/actions/tabs 矩形与改动前逐像素一致。
- 修复两处降权重后暴露的覆盖：Sprint 详情移除失效的 `gap: 0`，恢复 macOS 页签 12px 间距；base-services 的 `.sprint-card-label` 保留 `!important` 以维持弱化色。
- 删除可被顺序替代的 `!important` 共 140 处：feature/shared Modules 约 71、action-buttons 15、antd-overrides 27、shell-header 29（保留 1 处 weak label 颜色）；`buttons.css`、`list-table.css`、`surface-tokens.css` 等仍承担全局契约的文件保持不动。
- 指标：长前缀 98 → 0，`!important` 235 → 95，行数 19,169 → 19,014（-155），文件数 68、重复规则体 59 不变；预算基线已 ratchet 到 0 长前缀 / 95 处。
- 验证：`npx tsc --noEmit`、全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；14 条页面路由在浅/深色下的 computed-style 指纹与基线一致，另在 1280/900/760 与深色下人工核对外壳与项目页。

### 阶段 24：Projects/Sprint 环境抽屉与动态值选择器 Tailwind 化（已完成）

已完成（2026-11-18）。这是阶段 20–23 清障后的第一个页面族 utility 迁移单元，只迁纯布局、间距与响应式排布，皮肤、AntD 深层结构与 Markdown 排版留在 Module：

- `EnvironmentDrawer` 的根壳、上下分区、分区头、工具栏、列表与空态卡片、变量表容器改用 `flex/gap/min-h/flex-[0_0_320px]` 等 utility；搜索框宽度、900px 以下工具栏/分区头/列表间距改用 `max-narrow:*`。
- `DynamicValuePickerModal` 的三栏工作区、来源导航、列表行、预览区与页脚改用 utility；900px 以下收成两栏、隐藏预览与来源计数，浏览器边框仍由媒体查询保留。
- 删除 `.root, .root *` 的重复 box-sizing、抽屉/选择器中的纯布局规则与 900px 媒体块；`environment-drawer.module.css` 592 → 318 行。
- 迁移时确认两个级联细节：Tailwind utility 位于 `@layer utilities`，必须先删除原未分层布局声明才会生效；模板字符串中以 `${...}` 结尾的最后一个 utility 候选可能不被扫描，类名末尾补空格后再拼接动态 `active` 类。
- 指标：行数 19,014 → 18,736（-278），重复规则体 59 → 57，文件数 68、`!important` 95、长前缀 0 不变；结构基线已 ratchet 到 57 组与新的单文件计数。
- 验证：`npx tsc --noEmit`、全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；浏览器在 1280 与 900/760 下逐项对比抽屉/选择器的 computed layout（flex/grid/gap/padding/尺寸）与迁移前一致，浅/深色截图核对通过。

### 阶段 25：UI 测试列表 Tailwind 化与 `ui-list` Module 删除（已完成）

已完成（2026-11-18）。UI 自动化页面族的第一批：列表页工具栏与运行配置徽标。

- `UiSuiteListToolbar` 的筛选组、需求标签、搜索框圆角、⌘K 提示、右侧动作区与环境选择宽度改用 utility；`UiSuiteRunConfigCell` 的三枚徽标把间距、内距、圆角、描边、色调、字号与等宽字体全部移入 utility。
- 删除 `ui-list.module.css`（79 行）及 `UiAutomationPage` 的 scope 引用；列表页 CSS 文件 68 → 67。
- 等宽字体使用显式 `font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace]`，避免 `font-mono` 的 Liberation Mono 回退改变徽标宽度（视口徽标保持 73px）。
- 指标：行数 18,736 → 18,657（-79），文件数 68 → 67，重复规则体 57、`!important` 95、长前缀 0 不变；结构基线已 ratchet 到 67 个文件。
- 验证：`npx tsc --noEmit`、全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；浏览器在深/浅色下对比工具栏、搜索框、环境选择与 4 张卡片的 12 枚徽标 computed style，尺寸/字体/颜色与迁移前一致。

### 阶段 26：UI 测试集顶栏 Tailwind 化（已完成）

已完成（2026-11-18）。UI 自动化页面族第二批：测试集详情与用例顶栏。

- `UiSuiteDetailToolbar` 的工具栏壳、主区、面包屑、测试集名省略、动作区、环境选择宽度与响应式换行改用 utility；`min-[1181px]` 还原桌面单行，900px 以下继续换行。
- `UiTestSuiteCasePage` 的表单容器改用 `flex-auto flex min-h-0 flex-col gap-3`；面包屑名称项的位置、弹性宽度与边距，以及用例启用行也迁入 utility。
- 删除 `ui-detail-topbar.module.css` 中十条纯布局规则及其 1181px 媒体块，文件 388 → 287 行；顶栏描边/圆角/底色与 AntD 输入深层规则保留。
- 迁移时确认同属性竞争：动作区 6px 间距与环境选择 140px 下限来自 `ui-detail-shell` 的后期媒体规则，迁移前后 computed 值一致；`sr-only` 替代手写视觉隐藏规则，渲染仍为 1×1 不可见。
- 指标：行数 18,657 → 18,556（-101），文件数 67、重复规则体 57、`!important` 95、长前缀 0 不变；结构基线已 ratchet 到新的单文件计数。
- 验证：`npx tsc --noEmit`、全量 188 个测试文件 / 944 个用例、`npm run verify`、CSS 双门禁、主题检查与 `git diff --check` 通过；1280 下测试集流程与用例流程的顶栏/面包屑/动作区 computed style 与迁移前逐项一致，900 下换行布局一致。

#### Tailwind 化后续阶段

| 阶段 | 范围 | 风险 | 状态 |
| --- | --- | --- | --- |
| 16 | 列表/弹窗 Module：TestingPage、加入用例弹窗、用例推送、测试单列表、项目设置 | 低–中 | 已完成 |
| 17 | 列表与看板页：Projects/Sprint、用例库、测试单工作台 | 中 | 已完成 |
| 18 | 复杂详情/AI/图谱：需求详情、API/UI 详情、AI 生成链、关系图谱 | 高，最后做 | 已完成（2026-11-18） |
| 19 | 共享层审计与指标收口；外壳/按钮/表格全局契约只收缩 | 高，只做安全收缩 | 已完成（2026-11-18） |
| 20 | 共享原语分层、控件/筛选/工具栏 utility 解锁与死规则收缩 | 中，逐子批验证 | 已完成（2026-11-18） |
| 21 | 同根/同宿主 Module 合并与小文件吸收 | 低–中 | 已完成（2026-11-18） |
| 22 | 同文件重复规则体合并为选择器列表 | 低 | 已完成（2026-11-18） |
| 23 | macOS 前缀归一与 `!important` 收缩（外壳/按钮/表格契约） | 高，逐批验证 | 已完成（2026-11-18） |
| 24 | Projects/Sprint：环境抽屉与动态值选择器布局/响应式 utility 化 | 中 | 已完成（2026-11-18） |
| 25 | UI 测试列表：工具栏与运行配置徽标整体迁 utility，删除 `ui-list` Module | 低 | 已完成（2026-11-18） |
| 26 | UI 测试集顶栏：工具栏壳、面包屑、动作区与表单容器迁 utility | 中 | 已完成（2026-11-18） |

后续继续按页面族推进：UI 自动化 → API 自动化 → 测试单 → 接口库 → AI 测试 → 用例/Bug/需求/基础服务 → 共享外壳与列表表面；每族单独迁移、验证并 ratchet 指标。

## 目标指标

| 指标 | 阶段 4 完成后 | 阶段 5 第一批后 | 阶段 5 第二批后 | 阶段 5 完成后 | 阶段 6 完成后 | 阶段 7 完成后 | 阶段 8 完成后 | 阶段 9 完成后 | 阶段 10 完成后 | 阶段 11 完成后 | 阶段 12 完成后 | 阶段 13 完成后 | 阶段 14 完成后 | 阶段 15 完成后 | 阶段 16 完成后 | 阶段 17 完成后 | 阶段 18 完成后 | 阶段 19 完成后 | 阶段 20 完成后 | 阶段 21 完成后 | 阶段 22 完成后 | 阶段 23 完成后 | 阶段 24 完成后 | 阶段 25 完成后 | 阶段 26 完成后 | 结束目标 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CSS 文件 | 112 | 112 | 112 | 112 | 112 | 109 | 96 | 102 | 100 | 99 | 97 | 97 | 97 | 95 | 93 | 93 | 93 | 93 | 93 | 68 | 68 | 68 | 68 | 67 | 67 | ≤ 45 |
| CSS 行数 | 22,348 | 22,039 | 22,029 | 21,449 | 21,427 | 21,488 | 21,673 | 21,696 | 21,702 | 21,706 | 21,714 | 21,423 | 21,725 | 21,566 | 21,423 | 19,881 | 19,270 | 19,262 | 19,162 | 19,169 | 19,015 | 19,014 | 18,736 | 18,657 | 18,556 | ≤ 9,000 |
| `!important` | 420 | 402 | 402 | 307 | 307 | 307 | 307 | 307 | 307 | 307 | 307 | 262 | 262 | 262 | 262 | 253 | 253 | 253 | 236 | 236 | 235 | 95 | 95 | 95 | 95 | ≤ 100（仅 AntD Module） |
| 长前缀 | 125 | 125 | 125 | 121 | 121 | 121 | 121 | 121 | 121 | 121 | 121 | 101 | 101 | 101 | 101 | 101 | 101 | 101 | 98 | 98 | 98 | 0 | 0 | 0 | 0 | 0 |
| C1 超标文件 | 5 | 5 | 5 | 4 | 4 | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `App.css` feature 导入 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0（文件删除） | 0（文件删除） | 0（文件删除） | 0（文件删除） | 0（文件删除） | 0（文件删除） | 0（文件删除） | 0（文件删除） | 0（文件删除） | 0（文件删除） | 0（文件删除） | 0（文件删除） | 0（文件删除） | 0（文件删除） | 0 | 0 | 0 | 0 | 0 个（`App.css` 已删除） |
| 重复规则体（结构门禁口径） | 116 | 115 | 115 | 111 | 110 | 110 | 110 | 110 | 110 | 110 | 110 | 109 | 109 | 109 | 107 | 101 | 92 | 91 | 91 | 91 | 59 | 59 | 57 | 57 | 57 | ≤ 60 |

## 迁移单元

一个迁移单元 = 一个页面族或共享原语 + 它的旧 CSS + 相关测试 + 文档。默认在同一改动内完成，便于回滚和视觉核对。不要在一个改动里同时迁移多个 feature，也不要把全局 Shell 改动混进单页迁移。

## 验收

每个阶段固定：

```bash
cd apps/studio
npm run verify
npm test
npm run check:css
node scripts/check-css-structure.mjs
git diff --check
```

页面迁移另需人工确认浅色/深色、1280/900/760、表格/弹窗/Drawer/空态/长文本，以及页面切换后无残留覆盖。jsdom 不解析 `@layer`、不算真实布局，不能替代浏览器检查。

## 已知风险

- 移动 CSS import 会改变等优先级规则的先后顺序，必须逐页做浏览器对照。
- AntD 深层选择器优先用 `ConfigProvider` token 解决；仍需要时放 CSS Module，不新增页面级全局 CSS。
- 死类扫描会把 `segment-${key}`、`is-${state}` 等动态类误判为死类；扫描器只报告，删除必须人工确认。
- 基础服务卡片在 760–980px 的 3 列问题已于阶段 5 第一批修复：模块断点保持从宽到窄，900/760px 实测为 2 列。
- 当前没有浏览器 E2E；进入阶段 5 前建议补核心路由截图基线。
- 若 CSS WIP 尚未稳定，先确认工作树再 ratchet baseline。
