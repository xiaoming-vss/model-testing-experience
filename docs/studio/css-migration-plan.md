# CSS 整改与迁移计划

2026-11-17。本文是 Studio CSS 存量整改与 Tailwind CSS v4 / CSS Modules 迁移的执行顺序、阶段目标和验收口径。策略约束见 [ADR 0004](adr/0004-tailwind-v4-new-code-styles.md)，日常编码规则见 [STRUCTURE S16](STRUCTURE.md#四目录与样式契约)。

**执行状态（2026-11-17）**：阶段 0–9 已完成。阶段 8 迁完 AI 测试/生成链的页面壳、生成链弹窗、画布、产物视图、关系图谱与 UI 生成可视化，删除 25 个旧 CSS（含 3 个组件内 CSS），新增 12 个根作用域 Module。阶段 9 删除 `App.css` 聚合，把 4 个超 600 行文件拆成 10 个 Module/样式文件（C1 归零），结构门禁新增单文件行数与 `App.css` 回归检查；`!important` 307 / 长前缀 121 / 重复规则体 110 保持不变，未达到归零目标，残余项与后续路径见阶段 9。

## 当前基线

| 指标 | 整改前（2026-11-17） | 阶段 3 前 | 阶段 3 完成后 | 阶段 4 第一批后 | 阶段 4 完成后 | 阶段 5 第一批后 | 阶段 5 第二批后 | 阶段 5 完成后 | 阶段 6 完成后 | 阶段 7 完成后 | 阶段 8 完成后 | 阶段 9 完成后 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CSS 文件 | 101 个 | 102 个 | 109 个（新增 7 个 CSS Modules，含运行结果/导入/基础服务连接/项目设置） | 109 个（`page-frame.css` 拆为 `legacy-surface.css` + Sprint feature 样式，文件数不变） | 112 个（新增 shell/antd-overrides/action-buttons/project-overview，删除 workbench/page-frame） | 112 个（删除 Admin 与 Base Services 页面 CSS，新增 3 个 Module） | 112 个（删除 Test Orders 列表 CSS，新增 1 个 Module） | 112 个（删除 Bugs/Test Cases/TestingPage 共 6 个旧 CSS，新增 6 个 Module，净持平） | 112 个（接口库 index.css 替换为 1 个 Module） | 109 个（删除 API 6 个 + UI 8 个旧 CSS，新增 5 + 6 个 Module） | 96 个（删除 AI 22 个 + 组件内 3 个旧 CSS，新增 12 个 Module） | 102 个（+7 拆分文件，-1 `App.css`） |
| CSS 总行数 | 23,658 行 | 22,732 行 | 22,770 行（作用域化根类前缀增加少量字符） | 22,782 行 | 22,348 行 | 22,039 行 | 22,029 行 | 21,449 行 | 21,427 行 | 21,488 行（Module 作用域与多选择器换行增加 61 行） | 21,673 行（作用域声明与选择器换行增加 185 行） | 21,696 行（拆分文件头增加 23 行） |
| `!important` | 582 处 | 500 处 | 493 处 | 493 处 | 420 处 | 402 处 | 402 处 | 307 处 | 307 处 | 307 处 | 307 处 | 307 处（不变） |
| `.app-shell.app-shell-macos` 长前缀 | 164 处 | 165 处 | 163 处 | 163 处 | 125 处 | 125 处 | 125 处 | 121 处 | 121 处 | 121 处 | 121 处 | 121 处（不变） |
| 重复规则体 | 约 446 组（历史审计口径） | 134 组（结构门禁口径：≥3 条声明且规则体 ≥40 字符） | 134 组 | 123 组 | 116 组 | 115 组 | 115 组 | 111 组 | 110 组 | 110 组 | 110 组 | 110 组（不变） |
| 超过 C1 上限（600 行）的文件 | 7 个，合计 9,008 行，占 38% | 7 个 | 5 个，合计 6,048 行，占 26.6% | 5 个，合计 6,019 行，占 26.4% | 5 个，合计 5,288 行，占 23.6% | 5 个，合计 5,289 行，占 24.0% | 5 个，合计 5,289 行，占 24.0% | 4 个，合计 4,232 行，占 19.7% | 4 个，合计 4,201 行，占 19.6% | 4 个，合计 4,203 行，占 19.6% | 4 个，合计 4,203 行，占 19.4% | 0 个 |
| `App.css` feature 导入 | 5 个 | 4 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个 | 0 个（`App.css` 已删除） |

历史审计的重复规则体口径更宽，不与结构门禁计数直接比较；后续 ratchet 只使用结构门禁口径。

阶段 3 之前，`src/App.css` 仍聚合 API `overview.css`、UI `index.css`、API `detail.css`、base-services `index.css`；这些文件的 `.api-filter-*`、`.api-collection-*`、`json-editor-*`、`api-case-nav-*` 等类被多个 feature 共用。阶段 3 已按实际消费方拆到共享 Module、共享 surface 层或 owner 组件，`App.css` 只保留 `layout.css`、`legacy-surface.css`、`shell.css`、`antd-overrides.css`、`action-buttons.css`、`shell-boundary.css`。阶段 9 删除 `App.css`，这六个导入按原顺序移入 `app/styles/theme.css`，全局层入口只剩一个文件。

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
- 环境相关：`api-env-var-picker-*` 归 `features/projects/styles/dynamic-value-picker.module.css`，`api-environment-*` 归 `features/projects/styles/environment-drawer.module.css`；项目设置抽屉归 `project-settings.module.css`。
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

- Admin：`AccountManagementPage` 的工具栏、筛选、表格单元与错误条改用 Tailwind utility；`LdapSettingsPage` 的页面骨架、两列表单、检查区与底部操作条改用 utility，只把 AntD `Form.Item` 间距留在 `ldap-settings.module.css`；删除 `account-management.css`、`ldap-settings.css`。
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

- Bugs：列表、详情、新建/编辑表单与禅道导入分别迁入 `bugs.module.css`、`bug-form.module.css`、`bug-import.module.css`，删除 `bugs-v2.css`、`bug-detail.css`、`bug-form.css`、`bug-import.css`；旧类名保留为测试与兼容钩子，详情专属根规则用 `.bugs-detail-page` 限定，避免列表被详情布局污染。
- Test Cases：`case-library-v2.css` 迁入 `case-library.module.css`；表格壳、左栏树、工具栏与空态保持原钩子，`case-library-title-cell` 等列样式留在 Module。
- TestingPage：标签外壳迁入 `testing-page.module.css`，保留页面常驻挂载与 `hidden` 切换；删除 `features/testing/styles/index.css`。
- 共享收敛：需求文档预览迁入 `requirements/styles/document-preview.module.css`；功能测试列表的共用字阶/颜色/名称列规则迁入 `shared/styles/list-table.css`；API/性能列表的工具栏内部排布迁入 `shared/styles/surface-tokens.css`；删除测试单搜索框的 2 处 `!important` 兼容覆盖。
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

- API 自动化：列表、详情壳、请求编辑器、请求头/请求体面板与规则/环境弹层分别迁入 `api-list.module.css`、`api-detail-shell.module.css`、`api-detail-editor.module.css`、`api-detail-request.module.css`、`api-detail-rules.module.css`；删除 `overview.css`、`list-v2.css`、`detail.css`、`detail-workbench-v2.css`、`detail-inspector-v2.css`、`detail-request-panels-v2.css`。
- API 作用域：列表页与详情页根节点挂 Module `.scope`；方法下拉通过 Select `classNames.popup.root`、环境 Popover 通过 `overlayClassName`、断言/提取规则 Modal 通过 `rootClassName` 把作用域带进 portal。
- UI 自动化：列表工具栏、测试集/步骤编辑器共享皮肤、详情壳、左栏流水线、右栏检查器与 React Flow 画布分别迁入 `ui-list.module.css`、`ui-suite.module.css`、`ui-detail-shell.module.css`、`ui-detail-pipeline.module.css`、`ui-detail-inspector.module.css`、`ui-execution-flow.module.css`；原 `step-editor-layout.css`、`suite-drawer-layout.css` 并入共享 Module；删除 8 个旧 CSS。阶段 9 再把详情顶栏拆到 `ui-detail-topbar.module.css`。
- UI 作用域：`UiAutomationPage` 同时挂列表与共享步骤样式作用域；`UiTestSuiteCasePage` 挂 5 个详情 Module；测试集 Drawer 在其 `className` 上追加作用域，缺失变量 Modal 在 `className` 上追加作用域；React Flow 仍由详情页根作用域覆盖宿主布局与节点样式。
- 测试夹具：API 请求面板与地址条测试改为读取新的 Module raw CSS；UI 自动化 70 个现有用例不需要改查询钩子。
- 指标：CSS 文件 112 → 109，全局 CSS 91 → 77；`!important` 保持 307，长前缀保持 121，重复规则体保持 110；总行数 21,427 → 21,488（Module 作用域声明与多选择器换行带来的格式开销），C1 文件保持 4 个（4,201 → 4,203 行）。
- 验证：API 36 个、UI 70 个 feature 用例通过；全量 188 个测试文件 / 943 个用例、`npm run verify`、CSS 双门禁与主题检查通过；1280 浅色/深色核对 API 列表/详情，1280/760 浅色/深色核对 UI 列表/详情、测试集抽屉、步骤编辑器与流程画布，760 复核 API 详情；深色下终端与表面 token 正常。

### 阶段 8：AI 测试/生成链

已完成（2026-11-17）：

- 需求生成页、生成链弹窗、画布与阶段检查器迁入 `requirement-design.module.css`、`generation-chain.module.css`、`generation-canvas.module.css`；`RequirementDetailPage` 根节点统一挂生成链/画布/产物/图谱/UI 生成/阶段可视化作用域，`GenerationArtifactFrame` 与图谱/导入弹窗各自在 `rootClassName` 上带作用域。
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
- `legacy-tokens.css` 的 27 个 `--legacy-*` 全部仍被 `shell.css` / `shell-header.css`、`project-overview.css`、`action-buttons.css` 消费，没有死 token；本阶段不删除仍被引用的别名，等对应外壳/项目概览迁移时再一并替换。
- 指标：CSS 文件 96 → 102（+7 拆分，-1 `App.css`），总行数 21,673 → 21,696（新文件头 +23），全局 CSS 52 → 53；C1 4 → 0；`!important` 307、长前缀 121、重复规则体 110 保持不变。
- 未完成的目标：文件 ≤45、行数 ≤9,000、`!important` ≤100、长前缀 0、重复规则体 ≤60。剩余 `!important` 主要集中在 `shell-header.css`、`buttons.css`、`antd-overrides.css`、`action-buttons.css` 等外壳与 AntD 覆盖层；121 处长前缀中 104 处在 `app/styles/`。这些规则用于压过 AntD/旧全局层，直接去前缀或去 `!important` 会改变同权重级联顺序，必须随剩余页面族（Test Orders 工作区、Test Cases 编辑器、Projects/Sprint 看板、shared 表格/按钮层）继续迁到 Tailwind/Module 时逐页浏览器对照，不能在本阶段靠机械替换清零。重复规则体的 110 组也以 flex/gap/ellipsis 微布局为主，需要在页面迁移时改成 Tailwind utility 才会自然消失。
- 验证：接口库/UI 自动化/Sprint 详情定向 18 个测试文件 / 118 个用例通过；全量 188 个测试文件 / 942 个用例、`npm run verify`、CSS 双门禁与主题检查通过；1280/760 浅色与深色浏览器冒烟覆盖接口库、UI 测试集详情、Sprint 详情和全局外壳。

## 目标指标

| 指标 | 阶段 4 完成后 | 阶段 5 第一批后 | 阶段 5 第二批后 | 阶段 5 完成后 | 阶段 6 完成后 | 阶段 7 完成后 | 阶段 8 完成后 | 阶段 9 完成后 | 结束目标 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CSS 文件 | 112 | 112 | 112 | 112 | 112 | 109 | 96 | 102 | ≤ 45 |
| CSS 行数 | 22,348 | 22,039 | 22,029 | 21,449 | 21,427 | 21,488 | 21,673 | 21,696 | ≤ 9,000 |
| `!important` | 420 | 402 | 402 | 307 | 307 | 307 | 307 | 307 | ≤ 100（仅 AntD Module） |
| 长前缀 | 125 | 125 | 125 | 121 | 121 | 121 | 121 | 121 | 0 |
| C1 超标文件 | 5 | 5 | 5 | 4 | 4 | 4 | 4 | 0 | 0 |
| `App.css` feature 导入 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0（文件删除） | 0 |
| 重复规则体（结构门禁口径） | 116 | 115 | 115 | 111 | 110 | 110 | 110 | 110 | ≤ 60 |

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
