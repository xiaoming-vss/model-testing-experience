# CSS 整改与迁移计划

2026-11-17。本文是 Studio CSS 存量整改与 Tailwind CSS v4 / CSS Modules 迁移的执行顺序、阶段目标和验收口径。策略约束见 [ADR 0004](adr/0004-tailwind-v4-new-code-styles.md)，日常编码规则见 [STRUCTURE S16](STRUCTURE.md#四目录与样式契约)。

**执行状态（2026-11-17）**：阶段 0、1、2 已完成；阶段 3 起待执行。

## 当前基线

| 指标 | 整改前（2026-11-17） | 阶段 0-2 后 |
| --- | --- | --- |
| CSS 文件 | 101 个 | 101 个（删除 `auth.css`，新增 `auth.module.css`） |
| CSS 总行数 | 23,658 行 | 22,732 行 |
| `!important` | 582 处 | 493 处 |
| `.app-shell.app-shell-macos` 长前缀 | 164 处 | 163 处 |
| 重复规则体 | 约 446 组（历史审计口径） | 134 组（结构门禁口径：≥3 条声明且规则体 ≥40 字符） |
| 超过 C1 上限（600 行）的文件 | 7 个，合计 9,008 行，占 38% | 7 个，合计 8,528 行，占 37.5% |
| `App.css` feature 导入 | 5 个 | 4 个 |

历史审计的重复规则体口径更宽，不与结构门禁计数直接比较；后续 ratchet 只使用结构门禁口径。

体量不是唯一问题。`src/App.css` 仍聚合 API `overview.css`、UI `index.css`、API `detail.css`、base-services `index.css`；`auth.css` 已在阶段 2 删除。`overview.css`、`detail.css` 的 `.api-filter-*`、`.api-collection-*`、`json-editor-*`、`api-case-nav-*` 等类被多个 feature 共用。直接把这些文件搬到名义页面会孤儿化真实样式，因此必须先做所有权拆分。

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
| 3 | 整改 | 跨 feature 所有权拆分 | 拆 `overview.css` / `detail.css` / UI/base-services 共享部分；App.css 只剩 shell/tokens | 待执行 |
| 4 | 迁移 | 共享原语 + Shell/Projects | `EntityCard`、`ListSurface`、`PageToolbar`、`FilterBar`；`workbench.css`、`page-frame.css` 收口 | 待执行 |
| 5 | 迁移 | 列表/工作台 | Bugs、Base Services、Admin、Test Cases、Test Orders、TestingPage 包装层 | 待执行 |
| 6 | 迁移 | 接口库 | 树、列表、编辑器、导入弹窗 | 待执行 |
| 7 | 迁移 | API/UI 自动化详情 | 列表 → 详情壳/检查器 → 编辑器/React Flow/CodeMirror | 待执行 |
| 8 | 迁移 | AI 测试/生成链 | 普通视图 → 生成链壳/优化侧栏 → 画布/图谱/UI 可视化 | 待执行 |
| 9 | 整改 | 收口 | 删除 `App.css` 聚合；legacy token 清理；预算归零；文档收口 | 待执行 |

### 阶段 0：门禁

- 新增 `scripts/check-css-structure.mjs` 与 `scripts/css-structure-budget.json`。
- 检查新增全局 CSS、`App.css` feature 导入、跨 feature CSS 导入、孤儿 CSS、每文件 rules/declarations/selectors、重复规则体、共享 Module 私有选择器、Tailwind layer 声明。
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

- `overview.css`：拆出共享 list/toolbar/card 样式与 API 页面专用样式。
- `detail.css`：拆出 `json-editor-*`、`api-env-var-picker-*`、`api-environment-*`、`api-collection-run-*`、`api-case-run-result-*`、`api-case-nav-*`、`api-case-import-*` 的共享部分。
- UI/base-services：把 `.api-case-sidebar*`、`.project-settings-*` 等跨 feature 类迁到实际消费方。
- 完成后从 `App.css` 移除对应导入，App.css 只保留 shell 与共享基础层。

### 阶段 4：共享原语与 Shell

- 升级 `EntityCard`，承接多 feature 的卡片皮肤。
- 新增/收敛 `ListSurface`、`PageToolbar`、`FilterBar`、`DetailSplit`。
- 拆分 `workbench.css`：shell / project / button / AntD override / 死选择器。
- 迁移 `ProjectsPage`、`SprintBoard`、`SprintDetailPage`、`RequirementCards`，吸收 `page-frame.css`。
- 统一 `@layer` 契约，移除依赖 `!important` 的按钮反向压制。

### 阶段 5-8：页面族迁移

按“列表/表单 → 接口库 → API/UI 自动化 → AI 测试/生成链”的顺序。每个页面族必须同时完成：

- 旧 CSS 文件删除；
- 共享原语复用；
- 浅色/深色、1280/900/760 浏览器验收；
- 文档实现位置更新；
- 预算下降或不变。

### 阶段 9：收口

- `App.css` 不再聚合 feature CSS。
- feature 级 `!important` 清零，长前缀清零。
- 7 个 C1 超标文件清零。
- 重复规则体（结构门禁口径）降到 60 组以内。
- 更新 ADR、STRUCTURE、UI-GUIDELINES 与本文基线。

## 目标指标

| 指标 | 阶段 0-2 后 | 阶段 4 后 | 结束目标 |
| --- | --- | --- | --- |
| CSS 文件 | 101 | ≤ 80 | ≤ 45 |
| CSS 行数 | 22,732 | ≤ 21,000 | ≤ 9,000 |
| `!important` | 493 | ≤ 300 | ≤ 100（仅 AntD Module） |
| 长前缀 | 163 | ≤ 20 | 0 |
| C1 超标文件 | 7 | 4 | 0 |
| `App.css` feature 导入 | 4 | 0 | 0 |
| 重复规则体（结构门禁口径） | 134 | ≤ 100 | ≤ 60 |

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
- 当前没有浏览器 E2E；阶段 4 前建议补核心路由截图基线。
- 若 CSS WIP 尚未稳定，先确认工作树再 ratchet baseline。
