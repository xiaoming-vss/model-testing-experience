# Feature 目录例外登记（S11）

- 状态：已接受
- 日期：2026-11-19
- 取代：—
- 被取代：—
- 关联：[STRUCTURE S11](../STRUCTURE.md#四目录契约)

S11 规定 feature 目录固定为 `api/`、`components/`、`hooks/`、`pages/`、`styles/`、`utils/`，新增目录需 ADR。当前有六类目录承担了无法自然放入这六类的职责，另有 `ai-testing/__fixtures__` 只包含一个无引用 JSON 文件，已按 S13 删除。

决定保留以下目录，并限定用途：

| 目录 | 用途 | 约束 |
| --- | --- | --- |
| `ai-testing/workers/` | Web Worker 入口，负责关系图路由计算 | 只允许 Worker 入口和 Worker 专用协议；不得渲染 React 或直接请求 API |
| `api-automation/config/` | 集合表单、请求面板和运行报告的静态选项与展示映射 | 纯常量、类型和纯函数；不得发起请求或保存页面状态 |
| `ui-automation/config/` | 步骤能力矩阵、定位器/比较器/操作的静态配置 | 纯常量、类型和纯函数；不得依赖 React 组件 |
| `ui-automation/constants/` | UI 测试集默认运行配置和展示标签 | 只读常量；不得存放可变运行时状态 |
| `auth/store/` | 认证会话 store（token、用户、登出） | 只允许一个认证 store；其他状态放 feature hook 或服务端查询缓存 |
| `test-orders/fixtures/` | 可视化组件的测试 JSON 样例 | 只允许被 `*.test.tsx` 引用，不得进入生产代码路径 |

约束：

- 这些目录不扩大 S11 的通用许可。新增例外目录必须新增或更新 ADR，并在 `docs/studio/STRUCTURE.md` 的 S11 证据中登记。
- 例外目录中的代码仍受 feature 边界、依赖方向和样式规则约束，不能成为跨 feature 的公共出口。
- 测试专用目录（`fixtures/`）不得被生产代码 import；发现即删除或迁回测试文件。

**已考虑的其他选项**：

- **全部迁入允许目录**：`workers/` 的 `new URL(..., import.meta.url)` 入口语义会变得含糊，`config/` 与 `utils/` 混杂会让配置和运行时逻辑难以区分；迁移收益低于目录语义损失。
- **把 config/constants 合并进 `types.ts`**：会让类型文件携带运行时值，破坏 `types.ts` 只放类型的约定。
- **把 auth store 上提 shared**：认证是业务状态，会违反 shared 无业务语义的准入条件；改为 shared 请求层通过 `authBridge` 反向注入，见 S1 修复。

**后果**：S11 仍以六个标准目录为默认；ADR 例外是显式白名单，不通过扫描器自动放行。目录数量或职责变化时必须更新本 ADR 和 STRUCTURE。
