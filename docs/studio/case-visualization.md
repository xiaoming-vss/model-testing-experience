# 测试单用例执行可视化：局部扩展记录

本文描述既有 Studio 执行工作台的普通局部扩展，不创建或变更全局设计系统；主题、字体和公共布局继续以 [界面规范](UI-GUIDELINES.md) 为准。

## 既有系统一致性

| 方面 | 已核对的实现 |
| --- | --- |
| 配色与主题 | 沿用 [ThemeProvider](../../apps/studio/src/app/providers/ThemeProvider.tsx)；局部样式消费 `--srf-text`、`--srf-text-secondary`、`--srf-card`、`--srf-card-border`、`--srf-accent`、`--srf-accent-soft`，不建立独立色盘。 |
| 字体与字阶 | 继承公共字体栈和 13px 基础字号；局部小标题 15px、600 字重，次级标题 13px，辅助信息 12px。原文保留换行并允许长内容断行。 |
| 控件 | 阅读方式使用 Ant Design Segmented；生成和原文入口使用 Button；状态、加载、警告和空态分别复用 Tag、Spin、Alert、Empty。 |
| 空间与边界 | 桌面正文内收 16px，以 1px 主题分隔线组织信息；步骤和实体使用 6px 圆角。局部样式未新增阴影。 |
| 响应式与焦点 | 图解与详情桌面分栏；1100px 以下上下排列，640px 以下正文内收 12px、数量图改单列。区间在自身区域内横向滚动；步骤、实体和原文区提供主题色焦点轮廓。 |

以上尺寸仅记录本扩展的实现，不提升为所有 Studio 页面必须遵循的新规则。样式来源：[visualizationClasses.ts](../../apps/studio/src/features/test-orders/components/visualization/visualizationClasses.ts) 与 [CaseVisualizationPanel.tsx](../../apps/studio/src/features/test-orders/components/visualization/CaseVisualizationPanel.tsx)。

## 阅读与生成行为

[工作台](../../apps/studio/src/features/test-orders/pages/TestOrderWorkspacePage.tsx)默认文字模式，按当前测试单保存本次浏览的阅读偏好。选择其他条目时，有有效图解才恢复可视化偏好；没有有效图解时回退原文，保留偏好供后续可用条目恢复。跨测试单默认文字。

[CaseVisualizationPanel](../../apps/studio/src/features/test-orders/components/visualization/CaseVisualizationPanel.tsx)检查图解版本、执行条目标识和支持的图块类型。可视化在当前有效图解存在时开放，运行状态与可用产物分别呈现；重新生成期间或失败时可继续阅读已有有效图解。查询失败、不可用及缺失内容通过提示和原文回退表达。

前置条件在上方；场景流程按快照步骤顺序排列，选择步骤后显示完整操作和预期。图解标明辅助阅读性质，选中态不代表执行通过。部分覆盖显示“部分内容未图解”及遗漏说明。依据字段保留在生成协议内部用于校验与步骤关联，不在执行界面提供依据入口或依据详情。

[BusinessDiagram](../../apps/studio/src/features/test-orders/components/visualization/BusinessDiagram.tsx)与[类型契约](../../apps/studio/src/features/test-orders/visualizationTypes.ts)支持选项集合、区间、状态和数量四类图块，保留来源、约束及示意标记。类型定义本身不能证明模型语义正确。

具有执行权限时提供当前单条生成、重试或重新生成，以及[生成所选图解](../../apps/studio/src/features/test-orders/components/visualization/VisualizationBatchButton.tsx)。批量点击时冻结勾选集合，最多 100 条，呈现逐条状态、已有图解跳过提示及条目定位入口。未增加整个测试单生成或图解有误反馈入口。

## 确认的工作台布局

可视化模式的前置条件放在图解布局上方，桌面左侧展示场景流程与完整验证焦点，右侧展示当前用例标题及所选步骤的完整操作和预期。窄屏按前置条件、流程、详情、图解排列。区间图仅在存在完整、明确、无条件的一对一产生关系时，将产物放在对应保留段下方；不完整或存在条件时保留原有关系展示，不能按数组位置推断。工作台原有用例级判定、权限和保存流程继续使用。历史产物仍按既有协议显示，需要重新生成才会使用新版技能。
