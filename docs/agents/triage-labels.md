# 分流标签

工程技能使用五种标准分流角色。本仓库工单为本地 markdown 文件，分流状态记录在工单文件顶部的 `Status:` 行中。下表将标准角色映射到 `Status:` 的取值。

| 标准角色          | `Status:` 取值      | 含义                         |
| ----------------- | ------------------- | ---------------------------- |
| `needs-triage`    | `needs-triage`      | 等待维护者评估和分流         |
| `needs-info`      | `needs-info`        | 信息不足，等待提交者补充     |
| `ready-for-agent` | `ready-for-agent`   | 信息完整，可由 AI Agent 处理 |
| `ready-for-human` | `ready-for-human`   | 需要人工实现或判断           |
| `wontfix`         | `wontfix`           | 已决定不处理                 |

当技能提到某种标准角色时，使用表中对应的 `Status:` 值写入工单文件。

如果仓库以后采用其他命名，只需修改“`Status:` 取值”这一列。
