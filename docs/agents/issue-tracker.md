# 问题跟踪器：本地 Markdown

本仓库的问题和规格统一以 Markdown 文件存放在仓库根目录的 `.scratch/` 中。以下路径均相对整个单仓库根目录；不再在各应用内新增独立问题目录。

## 操作约定

- 每个功能一个目录：`.scratch/<feature-slug>/`
- 规格文件：`.scratch/<feature-slug>/spec.md`；功能总览、模块需求和决策记录可放在同一功能目录下，例如 `00-overview.md`。
- 实现工单每张一个文件：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`，从 `01` 起编号，禁止把多张工单合并成一个文件
- 状态字段按工单类型使用 `Status:` 或 `Workflow:`；取值域见下方“工单字段与状态”
- 评论与对话记录追加到文件底部 `## Comments` 标题下

## 工单字段与状态

| 工单类型 | 识别方式 | 状态字段 | 允许值 |
| --- | --- | --- | --- |
| 分流工单 | 处于 triage 队列，尚未确定是否实现 | `Status:` | `needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`；见[分诊标签](triage-labels.md) |
| 实现/决策 backlog 工单 | `Type: task` 或 `Type: decision`，位于 `.scratch/<feature>/issues/` | `Status:` | `ready-for-agent`、`needs-triage`（决策型待定）、`resolved`；并行领取只写 Comments，不新增状态值 |
| Wayfinder 子工单 | 位于 Wayfinder effort 的 `issues/`，由 `map.md` 管理 | `Workflow:` | `ready`、`claimed`、`resolved`；需要分流时另写 `Status:` |

`Status:` 与 `Workflow:` 不得混用：分流状态只回答“是否需要补充信息、由谁实现”，`Workflow:` 只回答“是否已被领取、是否完成”。

## 当技能要求“发布到问题跟踪器”时

在 `.scratch/<feature-slug>/` 下新建文件（目录不存在时先创建）。

## 当技能要求“获取相关工单”时

读取引用路径处的文件。用户通常会直接给出路径或工单编号。

## Wayfinder 操作约定

`wayfinder` 使用一个地图文件作为地图，每张工单一个子文件。

- **地图**：`.scratch/<effort>/map.md`（包含笔记、已有决策和未知事项）。
- **子工单**：`.scratch/<effort>/issues/NN-<slug>.md`，从 `01` 编号，问题写在正文中。`Type:` 行记录工单类型（`research`/`prototype`/`grilling`/`task`）；`Workflow:` 行记录 `ready`/`claimed`/`resolved`。
- **阻塞关系**：文件顶部 `Blocked by: NN, NN` 行。当所列文件的 `Workflow:` 全部为 `resolved` 时，该工单解除阻塞。
- **查找可执行工单**：扫描 `.scratch/<effort>/issues/` 下未被阻塞、`Workflow: ready` 的文件；按编号取第一个。
- **认领工单**：先写入 `Workflow: claimed` 并保存，再开始任何工作。
- **完成工单**：在 `## Answer` 标题下追加答案，将 `Workflow:` 设为 `resolved`，然后在 `map.md` 的已有决策中追加上下文指针（摘要 + 链接）。
