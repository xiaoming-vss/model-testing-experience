# 2026-11-23 完整用例正式导入入口核对

- 日期：2026-11-23
- 状态：已验证
- 负责人：studio maintainers
- 来源：本地 Studio 开发服务器、控制面真实数据、深色主题
- 关联：[界面规范](../UI-GUIDELINES.md)、[候选工作区](../../../apps/studio/src/features/ai-testing/components/CandidateStageWorkspace.tsx)、[导入弹窗](../../../apps/studio/src/features/ai-testing/components/CandidateImportModal.tsx)

在 `Zata-Platform / 1.2.1 / 视频处理语义切片与深度开关调整` 的实际需求页打开「完整用例」阅读态，核对最终阶段当前采用内容的正式导入入口。此前用于比较放法的本地原型已删除，本记录只采用实际页面截图。

- [实际页面：导入入口固定在右侧栏底部](assets/2026-11-23-import-sidebar/final-cases-import-entry.png)
- [实际页面：预览弹窗与同名冲突对比](assets/2026-11-23-import-sidebar/import-preview-modal.png)

核对结果：

- 阅读态正文底部不再出现导入条；图谱和左侧用例索引完整占用原底部区域。
- 画布顶部不再保留标题、搜索和计数工具栏；「全部展开／收起全部」「适应画布」「保存图谱」浮动在画布右上角，窄屏把用例索引入口并入同一工具组。
- 右侧栏底部在查看当前采用内容时显示「导入正式用例 / 最终阶段 / 按模块归入功能测试集」和「预览并导入」；查看候选时仍由候选阶段操作占用，不显示导入入口。
- 点击入口打开 880px 弹窗，显示最终阶段、当前采用标识、功能测试集目标和预览状态；真实数据返回 1 个同名冲突，弹窗并排展示已有用例与将导入用例。
- 未点击「确认覆盖并导入」，未写入正式用例库。
- 验证视口 1718×1076，深色主题；浅色主题复核入口与按钮可见；1100×900 复核窄屏浮动工具组和用例索引抽屉。
- 自动检查：`npm run verify` 全部通过（含 `type-check`、`lint`、主题／CSS／边界／Tailwind 检查、构建、bundle 预算；208 个测试文件、1069 项测试）。
