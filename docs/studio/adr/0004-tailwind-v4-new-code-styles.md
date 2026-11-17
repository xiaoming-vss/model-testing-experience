# 新代码样式采用 Tailwind CSS v4 + CSS Modules，存量冻结

2026-11-17。

studio 当前有 106 个 CSS 文件、26,104 行、5,260 条规则、18,728 条声明。审计显示体量偏大的主因不是业务复杂度本身，而是新增页面持续复制同一套页面骨架：布局相关声明占 48.7%，约 1,025 条规则体与别处完全重复；旧工作台样式与 18 个 v2/v3 页面样式（7,209 行）并存，需要 737 处 `!important` 与 194 处 `.app-shell.app-shell-macos` 长前缀维持级联。如果新增页面继续按旧方式写页面级全局 CSS，存量会继续增长，而且每轮改版都会再叠一层覆盖。

决定：从本 ADR 起，新增或改版的 UI 采用以下样式策略：

- **布局、间距、排版**使用 Tailwind CSS v4 utility；不在页面级 CSS 中重复声明 flex/grid/gap/padding。
- **复杂皮肤**使用 CSS Modules；用于渐变、阴影、伪元素、动画、Ant Design 深层结构等 utility 不适合表达的部分。模块文件放在 `features/<f>/styles/` 或 `shared/styles/`，继续遵守 S6。
- **重复结构**出现三次以上（工具栏、列表面板、页签、分栏、滚动区、统计条）必须抽到 `shared/` 组件；不允许在多个页面复制同一串 utility 或同一条 CSS 规则。
- **颜色**只消费已登记 token。Tailwind 通过 `@theme` 映射 `--app-*` / `--srf-*` 等语义 token，禁用默认色盘；禁止 `bg-[#...]`、`text-[#...]` 等任意色值。
- **禁止新增**全局 CSS 文件（`app/styles/`、`shared/styles/` 下只允许 token 文件和既有公共层收缩）和 feature 级全局 CSS；禁止新增 `!important` 与 `.app-shell.app-shell-macos` 长前缀。
- **存量 CSS 冻结**，只允许删除或收缩。改到哪个页面就迁哪个页面，迁完删除原 CSS 文件；不得以“以后统一迁移”为由继续新增旧式 CSS。
- **Tailwind 工具链接入前**，新增样式只能使用 CSS Modules；不得以等待接入为由恢复页面级全局 CSS。

工具链接入要求：使用 `@tailwindcss/vite`；在 `src/shared/styles/tailwind.css` 声明 `@layer theme, base, antd, components, utilities;`；Ant Design 用 `<StyleProvider layer>` 包进 `@layer antd`，必要时启用 `cssVar`。初期不引入 preflight，或只作用域化引入，避免改掉 Ant Design 的基础样式。layer 只在生产入口开启；jsdom 无法完整解析 `@layer`，测试入口开启后 AntD 的关闭动画会挂起，因此测试使用普通的 `ThemeProvider`，layer 行为由浏览器验证。Tailwind 与旧 CSS 并存期间，未分层的旧规则仍可能压过 utility；新页面不得用 `!` 绕过，应按迁移规则把该页面的旧规则迁走或删除。

**实施补充（2026-11-17 首次迁移）**：迁移一个页面时，除删除原 CSS 文件外，还要清理 CSS Modules 中 0 引用的类、页面里重复的 Ant Design 深层规则和重复 utility 串；共享 `*.module.css` 不得包含 feature 私有选择器或 DOM 契约，宿主适配留在 feature 的 `styles/`；重复字号、断点登记到 `tailwind.css` 的 `@theme`；删除或改名样式文件时同步更新 `README.md`、`UI-GUIDELINES.md` 与 STRUCTURE 的实现位置。完整验收清单和检查命令见 [STRUCTURE.md 的迁移执行清单](../STRUCTURE.md#迁移执行清单2026-11-17-试点补充)。

存量整改顺序、阶段目标与预算 ratchet 见 [CSS 整改与迁移计划](../css-migration-plan.md)。

度量改用声明数、规则数、全局选择器数、`!important`/长前缀数、重复规则体，不以行数判断；行数会被压缩与展开格式严重扭曲。检查已落地：`scripts/check-css-structure.mjs` 统计规则体与重复体、约束全局/跨 feature 导入和共享 Module 私有选择器；`scripts/check-css-budget.mjs` 继续约束 `!important`/长前缀/未定义变量；`check-theme-colors.mjs` 识别 className 中的任意色值。三项均接入 `npm run verify`。

**已考虑的其他选项**：

- **全量重写为 Tailwind**：需要迁移 106 个文件、5,260 条规则，仓库没有 CI，视觉回归成本过高；不采用。
- **只用 CSS Modules**：成本最低，能解决作用域和长前缀，但不统一布局尺度，重复布局仍会留在每个页面；保留为 Tailwind 接入前的过渡方案和复杂皮肤层。
- **vanilla-extract / Panda CSS**：类型安全和主题契约更好，但迁移成本、构建复杂度和团队学习成本更高；暂不采用，若 Tailwind 试点失败再评估。
- **styled-components / Emotion**：与 Ant Design 6 的 cssinjs 运行时重叠，增加包体和样式注入竞争；不采用。
- **Bootstrap / MUI / Chakra**：等于替换 Ant Design 组件层，超出样式治理范围；不采用。
- **Sass / Less**：只改变语法，不解决重复和级联；不采用。

**后果**：迁移期会同时存在旧全局 CSS、Tailwind 和 CSS Modules 三套机制，必须按“新代码只用后两者、旧代码只减不增”的边界控制，不能出现第四套。Tailwind v4 要求 Safari 16.4+、Chrome 111+、Firefox 128+；若目标用户包含更旧的浏览器，退回 CSS Modules 方案。Tailwind 输出会增加少量 CSS 体积，但主要包体压力仍在 JS，不以“减包体”作为本次决策的主要收益。jsdom 不能完整模拟 CSS layer 的级联，涉及 layer 的改动必须在浏览器核对两种主题与各断点；依赖计算样式和类名的测试需随页面迁移同步更新。
