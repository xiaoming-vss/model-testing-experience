# Issue 跟踪器：本地 Markdown

本仓库的需求、规格与问题均以 `.scratch/` 下的 Markdown 文件管理，不依赖外部服务。

## 约定

- 每个 feature 一个目录：`.scratch/<feature-slug>/`
- feature 级文档（总览、模块需求、决策记录）直接放该目录下，如 `00-overview.md`、`03-testpilot-studio.md`
- 实施 ticket 按票单文件存放：`.scratch/<feature-slug>/issues/<NN>-<slug>.md`，从 `01` 按依赖顺序编号（阻塞者在前），绝不合并成单个文件
- triage 状态记录在每个 issue 文件顶部附近的 `Status:` 行（角色字符串见 `docs/agents/triage-labels.md`）
- 评论与对话历史追加到文件底部 `## Comments` 标题下

## 当技能要求“发布到 issue tracker”时

在 `.scratch/<feature-slug>/` 下新建文件（目录不存在则创建）。

## 当技能要求“获取相关 ticket”时

读取引用的文件路径。用户通常会直接传文件路径或编号。

## Wayfinding 操作

供 `/wayfinder` 使用。一个 **map** 对应一个主文件，其 **child ticket** 对应一个子文件。

- **Map**：`.scratch/<effort>/map.md`，正文包含 Notes、Decisions-so-far 和 Fog。
- **Child ticket**：`.scratch/<effort>/issues/NN-<slug>.md`，从 `01` 编号，问题写在正文。`Type:` 行记录 ticket 类型（`research`/`prototype`/`grilling`/`task`）；`Status:` 行记录 `claimed`/`resolved`。
- **阻塞关系**：顶部 `Blocked by: NN, NN` 行。所有列出的文件都已 `resolved` 时，ticket 才视为解除阻塞。
- **查询可执行 ticket**：扫描 `.scratch/<effort>/issues/` 中未关闭、未阻塞且未认领的文件，按编号取第一个。
- **认领**：先把 `Status: claimed` 写入文件并保存。
- **完成**：先在 `## Answer` 标题下追加答案并置 `Status: resolved`，再向 map 的 Decisions-so-far 追加上下文指针（指向该 ticket 文件路径的链接）。
