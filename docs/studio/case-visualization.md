# 测试单用例执行可视化：局部扩展记录

记录日期：2026-11-14。本记录描述既有 Studio 执行工作台的普通局部扩展，不创建或变更全局设计系统；主题、字体和公共布局继续以 [界面规范](UI-GUIDELINES.md) 为准。需求依据为[测试单用例执行可视化需求](/home/xiaoming/data/文档/test-agent/需求/测试单用例执行可视化需求.md)，采用已取消“图解有误反馈”的最新版范围。

## 既有系统一致性

| 方面 | 已核对的实现 |
| --- | --- |
| 配色与主题 | 沿用 [ThemeProvider](../../apps/studio/src/app/providers/ThemeProvider.tsx)；局部样式消费 `--srf-text`、`--srf-text-secondary`、`--srf-card`、`--srf-card-border`、`--srf-accent`、`--srf-accent-soft`，不建立独立色盘。 |
| 字体与字阶 | 继承公共字体栈和 13px 基础字号；局部小标题 15px、600 字重，次级标题 13px，辅助信息 12px。原文保留换行并允许长内容断行。 |
| 控件 | 阅读方式使用 Ant Design Segmented；生成和原文入口使用 Button；状态、加载、警告和空态分别复用 Tag、Spin、Alert、Empty。 |
| 空间与边界 | 桌面正文内收 16px，以 1px 主题分隔线组织信息；步骤和实体使用 6px 圆角。局部样式未新增阴影。 |
| 响应式与焦点 | 图解与详情桌面分栏；1100px 以下上下排列，640px 以下正文内收 12px、数量图改单列。区间在自身区域内横向滚动；步骤、实体和原文区提供主题色焦点轮廓。 |

以上尺寸仅记录本扩展的实现，不提升为所有 Studio 页面必须遵循的新规则。样式来源：[case-visualization.css](../../apps/studio/src/features/test-orders/styles/case-visualization.css)。

## 阅读与生成行为

[工作台](../../apps/studio/src/features/test-orders/pages/TestOrderWorkspacePage.tsx)默认文字模式，按当前测试单保存本次浏览的阅读偏好。选择其他条目时，有有效图解才恢复可视化偏好；没有有效图解时回退原文，保留偏好供后续可用条目恢复。跨测试单默认文字。

[CaseVisualizationPanel](../../apps/studio/src/features/test-orders/components/visualization/CaseVisualizationPanel.tsx)检查图解版本、执行条目标识和支持的图块类型。可视化在当前有效图解存在时开放，运行状态与可用产物分别呈现；重新生成期间或失败时可继续阅读已有有效图解。查询失败、不可用及缺失内容通过提示和原文回退表达。

前置条件在上方；场景流程按快照步骤顺序排列，选择步骤后显示完整操作和预期。图解标明辅助阅读性质，选中态不代表执行通过。部分覆盖显示“部分内容未图解”及遗漏说明。依据字段保留在生成协议内部用于校验与步骤关联，不在执行界面提供依据入口或依据详情。

[BusinessDiagram](../../apps/studio/src/features/test-orders/components/visualization/BusinessDiagram.tsx)与[类型契约](../../apps/studio/src/features/test-orders/visualizationTypes.ts)支持选项集合、区间、状态和数量四类图块，保留来源、约束及示意标记。类型定义本身不能证明模型语义正确。

具有执行权限时提供当前单条生成、重试或重新生成，以及[生成所选图解](../../apps/studio/src/features/test-orders/components/visualization/VisualizationBatchButton.tsx)。批量点击时冻结勾选集合，最多 100 条，呈现逐条状态、已有图解跳过提示及条目定位入口。未增加整个测试单生成或图解有误反馈入口。

## 验证入口与证据边界

已有真实浏览器组件夹具：[预览源码](../../.scratch/test-order-case-visualization/browser/preview.tsx)、[检查脚本](../../.scratch/test-order-case-visualization/browser/check.py)、[结果记录](../../.scratch/test-order-case-visualization/browser/results.json)。脚本以模拟接口返回四类图解，检查预期原文定位、页面横向溢出及页面错误。结果记录包含 1440×1000 桌面、390×844 窄屏和 1440×1000 深色三种视口，均记录来源定位成功、无页面横向溢出及空错误列表。

| 图块 | 桌面 | 窄屏 | 深色 |
| --- | --- | --- | --- |
| 选项集合 | [截图](../../.scratch/test-order-case-visualization/browser/desktop-0.png) | [截图](../../.scratch/test-order-case-visualization/browser/mobile-0.png) | [截图](../../.scratch/test-order-case-visualization/browser/dark-0.png) |
| 区间拆分 | [截图](../../.scratch/test-order-case-visualization/browser/desktop-1.png) | [截图](../../.scratch/test-order-case-visualization/browser/mobile-1.png) | [截图](../../.scratch/test-order-case-visualization/browser/dark-1.png) |
| 状态变化 | [截图](../../.scratch/test-order-case-visualization/browser/desktop-2.png) | [截图](../../.scratch/test-order-case-visualization/browser/mobile-2.png) | [截图](../../.scratch/test-order-case-visualization/browser/dark-2.png) |
| 数量归属 | [截图](../../.scratch/test-order-case-visualization/browser/desktop-3.png) | [截图](../../.scratch/test-order-case-visualization/browser/mobile-3.png) | [截图](../../.scratch/test-order-case-visualization/browser/dark-3.png) |

独立 reviewer 已将深色链接对比度修复判为 resolved：正常约 6.85:1、点击后约 5.64:1；其 ship 结论仅针对该修复。该结论由本次工作交接提供，本记录未重新测量，不能扩大解释为完整功能验收。

可复用的单元检查入口为 [面板测试](../../apps/studio/src/features/test-orders/components/visualization/CaseVisualizationPanel.test.tsx)、[图块测试](../../apps/studio/src/features/test-orders/components/visualization/BusinessDiagram.test.tsx)、[工作台测试](../../apps/studio/src/features/test-orders/pages/TestOrderWorkspacePage.test.tsx)及[主题测试](../../apps/studio/src/app/providers/ThemeProvider.palette.test.tsx)。在 `apps/studio` 下使用 `npm test -- <测试文件路径>`；类型、lint、主题及构建入口见 [package.json](../../apps/studio/package.json) 的 `verify`。本次文档整理仅核对源码和已有证据，未运行这些检查，不在此记录其通过状态。

组件夹具不是实际登录后的端到端测试，不能证明真实账户权限、任务派发、Worker 回传、批量持久化或真实模型输出质量。真实模型验收仍须按需求的独立门槛完成；当前截图和结构化契约不能替代该验收。`.scratch` 证据是本地工作材料，发布文档时需另行保留对应产物。

本记录未将缺陷或潜在既有偏差固化为设计规范，也未修改既有规范；仅记录当前局部扩展与证据边界。

## 2026-11-14 Demo 对齐

按原型的“场景流程 + 验证焦点 + 右侧详情”组织图解。步骤节点优先使用关联的单个 action 实体标签，否则显示冻结操作正文；长文只在节点中折行截显，右侧保留完整操作和预期。上一步／下一步与节点选择共用阅读位置，窄屏自动将当前节点滚入流程条。该位置不是执行进度，不新增步骤通过／失败；整条用例仍使用工作台原有判定入口。

主图区域固定为“场景流程”和一个“验证焦点”区域；验证焦点内按最早关联步骤排列图形，切换步骤只更新详情与关联高亮，保持整个用例的验证内容可见。区间使用连续保留／剔除色带，等宽仅为示意，不推断实际时长。数量与其他关系按明确的 relation 画连接，否定使用断开的虚线和禁止标识，条件保留在连线上；不能按数组位置或相同数量猜测对应关系。实体和关系为静态图形，不再表现为可点击的依据入口；右侧只展示当前步骤的完整操作和预期。窄屏按前置条件、流程、步骤详情、图解排列，流程与区间只在内部横向滚动。

本次用运行环境中已成功生成的“三段互不相连、每段不小于 3 秒的有效区间，各自产出 1 个 Segment，共 3 个”用例进行同输入、同产物的前后对比，未重新调用模型或写入执行结论。保留／剔除顺序、时长下限及三组产生关系都已存在于原产物，因此本次未修改 Skill 或 1.0 协议。该单例仍有标签较长的问题，可作为后续简化标签措辞的依据，不能据此宣称所有真实生成质量均已验收。

本地对比材料位于 `.scratch/test-order-case-visualization/demo-alignment/`；冻结输入与原产物只作本地验证材料，不作为仓库测试 fixture。浏览器检查覆盖深浅色桌面、390px 窄屏、步骤联动、来源定位与否定关系；未在真实工作台提交执行结果。回归新增多步骤切换、条件／否定关系来源和“数量相等也不推断连接”的行为验证。

2026-11-14 后续按用户确认精简展示：移除依据按钮、链接图标、依据详情，以及“当前步骤图解／其他步骤图解”分组；验证焦点统一为单一区域。上述早期来源定位截图与验收记录仅为历史证据，当前行为由更新后的组件测试覆盖。

## 确认的工作台布局

可视化模式的前置条件放在图解布局上方，桌面左侧展示场景流程与完整验证焦点，右侧展示当前用例标题及所选步骤的完整操作和预期。窄屏按前置条件、流程、详情、图解排列。区间图仅在存在完整、明确、无条件的一对一产生关系时，将产物放在对应保留段下方；不完整或存在条件时保留原有关系展示，不能按数组位置推断。工作台原有用例级判定、权限和保存流程继续使用。历史产物仍按既有协议显示，需要重新生成才会使用新版技能。
