# studio 开发指引

> 状态：现行｜负责人：studio maintainer｜最近复核：2026-11-19｜复核周期：每季度
>
> 适用范围：`apps/studio/`。变更/废弃：按[规范变更检查清单](../../docs/agents/domain.md#规范变更检查清单)执行；影响跨项目契约时先记录 ADR 并通知消费方。

本目录遵循根目录 [AGENTS.md](../../AGENTS.md)。文档统一维护于 [docs/studio](../../docs/studio/README.md)。

- 业务上下文：[CONTEXT.md](../../docs/studio/CONTEXT.md)。
- 结构与代码规范：[STRUCTURE.md](../../docs/studio/STRUCTURE.md)（分层与依赖方向、feature 边界、样式归属、目录契约、代码体积）。
- 新增或改版 UI 的样式必须遵循 [STRUCTURE.md 的 S16](../../docs/studio/STRUCTURE.md#新代码样式策略2026-11-17) 与 [ADR 0004](../../docs/studio/adr/0004-tailwind-v4-new-code-styles.md)：布局/间距/排版用 Tailwind CSS v4 utility，复杂皮肤用 CSS Modules；不得新增非 `*.module.css` 的全局 CSS 文件、`!important` 或 `.app-shell.app-shell-macos` 长前缀；重复结构抽到 `shared/`。存量 CSS 冻结，改到哪个页面迁哪个页面。
- 迁移样式时按 [STRUCTURE.md 的 S16](../../docs/studio/STRUCTURE.md#新代码样式策略2026-11-17) 同步收尾：删除原 CSS 与 module 中 0 引用的类（S13）；共享 `*.module.css` 不得包含 feature 私有选择器，宿主适配写在自己的 `styles/*.module.css`；重复字号、断点使用 `tailwind.css` 的 `@theme` token；同一改动内更新 `docs/studio/UI-GUIDELINES.md` 的实现位置。
- 新增列表／卡片页或修改布局、背景、边距、工具栏时，必须先读 [界面规范](../../docs/studio/UI-GUIDELINES.md)，采用“外置 Tab + 单一外框内工具栏、16px 内收内容、底部分页”的公共布局，接入 `tp-list-panel` / `tp-list-body` / `tp-list-scroll`；具体结构、例外及验证要求以该规范为准。
- 新增或修改数据列表（含详情、弹窗表格）时，沿用公共 1px 横向行分隔线；实现、主题与验证入口见 [界面规范·表格](../../docs/studio/UI-GUIDELINES.md#表格名称和操作列)。
- 新增或修改运行产物预览弹窗时，必须遵循 [产物预览弹窗](../../docs/studio/UI-GUIDELINES.md#产物预览弹窗)，复用统一尺寸与内部滚动规则。
- 架构决策：[ADR](../../docs/studio/adr/)。
- 公共规范：[领域文档](../../docs/agents/domain.md)、[问题跟踪](../../docs/agents/issue-tracker.md)、[分诊标签](../../docs/agents/triage-labels.md)。

问题跟踪路径 `.scratch/` 相对单仓库根目录；应用代码与测试路径相对本目录。修改业务代码前先阅读对应上下文和相关 ADR。
