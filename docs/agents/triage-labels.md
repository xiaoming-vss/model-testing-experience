# 分流标签

- 状态：现行
- 负责人：platform maintainers
- 最近复核：2026-11-19
- 复核周期：每季度
- 适用范围：分流工单的 `Status:` 词表
- 变更/废弃：按[规范变更检查清单](domain.md#规范变更检查清单)执行；影响跨项目契约时先记录 ADR 并通知消费方。

工程技能使用五种标准分流角色。本仓库的分流工单为本地 markdown 文件，分流状态记录在工单文件顶部的 `Status:` 行中。下表将标准角色映射到 `Status:` 的取值。

| 标准角色          | `Status:` 取值      | 含义                         |
| ----------------- | ------------------- | ---------------------------- |
| `needs-triage`    | `needs-triage`      | 等待维护者评估和分流         |
| `needs-info`      | `needs-info`        | 信息不足，等待提交者补充     |
| `ready-for-agent` | `ready-for-agent`   | 信息完整，可由 AI Agent 处理 |
| `ready-for-human` | `ready-for-human`   | 需要人工实现或判断           |
| `wontfix`         | `wontfix`           | 已决定不处理                 |

当技能提到某种标准角色时，使用表中对应的 `Status:` 值写入分流工单。

本表不适用于实现/决策 backlog 工单和 Wayfinder 子工单：前者使用 `Status: ready-for-agent | needs-triage | resolved`，后者使用 `Workflow: ready | claimed | resolved`；见[问题跟踪](issue-tracker.md#工单字段与状态)。

如果仓库以后采用其他命名，只需修改“`Status:` 取值”这一列。
