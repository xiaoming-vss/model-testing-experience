# 单执行条目图解任务

`test_order_case_visualization` 是单阶段、无需审核导入的辅助阅读任务。控制面读取执行条目冻结正文，Worker 通过默认技能 `mtx-analyze-case-visualization` 返回 `ready`、`partial` 或 `unsupported`。不生成真实执行结果，不修改原始用例。

## 实现与契约

- [执行器](../../apps/ai-worker/src/testing_agent_ai_worker/tasks/case_visualization/executor.py) 读取 `configJson.visualizationInput`；校验平台来源目录与快照哈希后，只调用一次模型。
- [默认技能](../../apps/control-plane/default-skills/mtx-analyze-case-visualization/SKILL.md) 包含规范及机器 Schema；Worker 校验下载的 Schema 与自身打包版本一致。实际使用的技能文件摘要与模型标识由运行代码记录，不要求模型输出。
- [Schema](../../apps/control-plane/default-skills/mtx-analyze-case-visualization/references/output.schema.json) 和 [contract.py](../../apps/control-plane/default-skills/mtx-analyze-case-visualization/references/contract.py) 为唯一维护源。控制面和 Worker 拥有独立打包副本；从仓库根目录运行 `python3 scripts/sync_case_visualization_contract.py --check` 检查漂移，去掉 `--check` 更新副本及 Studio 测试样例。
- 四种业务图块为 `options/interval/state/quantity`。确定性步骤流程由 Studio 读取快照生成。全部图解文字按普通文本显示；数值范围、条件、否定、数量、归属和引用通过受限字段表达。
- 格式错误、非法引用或不完整模型输出均失败，不自动语义重试；合法 `unsupported` 是任务成功完成，但不会成为可用图解。回传失败按现有 Worker 结果上报语义记录错误，不重跑模型；瞬时回传失败需重新生成。

## 无工具执行

执行器通过公共 `run_agent_prompt(tools=())` 调用模型，Skill 正文及 Schema 由代码直接提供。Pi 使用 `--no-tools`；Nanobot 适配器针对锁定的 SDK 0.3.5 清空工具注册表、禁用 MCP provider，并使用 ephemeral 运行。这些 SDK 细节仅在 adapter 内，其他任务的默认工具行为不变。更新 SDK 时需重跑适配器及无工具测试；不能静默降级为全工具运行。运行前校验 SDK 工具注册表与 MCP provider 存在，运行后再次确认为空；空 `SKILL.md` 直接失败且不调用模型。

上限：输入 256 KiB、输出 512 KiB、图块 8、实体 100、关系 200、断言 100、嵌套深度 12；超限明确失败或由模型输出有依据的 partial/unsupported，不能截断原文或改写断言。并发复用现有 Worker 配置，后端超时和租约沿用现有机制。

## 部署顺序

以下为部署说明，本次没有操作业务库或发布默认技能：

1. 从仓库运行同步资源检查，构建控制面与 Worker。两个 wheel 均须包含 `output.schema.json`。
2. 在目标环境按既有流程应用 Alembic `20261114_0003` 迁移。它接在接口库 `20261113_0002` 后；不得覆盖 baseline。
3. 在 `apps/control-plane` 使用目标环境已有配置执行 `uv run --locked python -m testing_agent.cli.skills default-skills` 发布系统默认技能（不使用 `--prune`）。前置是现有 S3 文件存储与技能发布授权环境可用。
4. 更新 Worker 后再开放控制面与 Studio 的生成入口，避免旧 Worker 领取新任务。回退到旧前端仍可文字执行；回退迁移会丢失图解绑定和批次回执，应先停止接收新图解任务并处理在途任务。
5. 不改变五个应用的依赖文件、锁文件、Dockerfile 或启动入口。本功能没有新增部署配置项。

## 语义质量门槛

[50 条候选样本](../../apps/ai-worker/tests/fixtures/case_visualization/evaluation-candidates.json) 均标为 `draft`。它们覆盖四类关系、否定、条件、缺失、歧义及不支持场景，不代表已经人工标注，也不代表已经过真实模型运行。

真实验收流程：选择测试项目及运行发起者本人的模型连接；人工确认样本适用性和关键事实；执行生成并保存各样本输出；评审摘要、标题、图形、断言与遗漏。每条 review 至少包含：

```json
{
  "id": "eval-001",
  "reviewer": "实际评审人",
  "suitable": true,
  "usable": true,
  "severeErrorCount": 0,
  "evidence": "真实输出路径及关键事实核对记录"
}
```

以上只展示字段，不是已完成评审。将真实评审记录组成数组后，从根目录执行：

```sh
python3 scripts/evaluate_case_visualization.py \
  --samples apps/ai-worker/tests/fixtures/case_visualization/evaluation-candidates.json \
  --reviews /absolute/path/to/human-reviews.json \
  --output /absolute/path/to/quality-report.json
```

门槛：至少 50 条且全部有人工作证、严重错误 0、适用样本有效覆盖率 ≥80%。分母由人工适用性判定；partial 不能自动算可用。不完整评审、分母为 0 或门槛不满足时脚本退出 1。当前缺少真实模型输出和人工评审，不能宣称达到上线门槛。

## 检查入口

在 `apps/ai-worker` 执行 `uv run --locked --group dev python -m unittest discover -s tests -v`、Ruff 及格式检查。专项为 `tests/unit/test_case_visualization.py`，覆盖无工具模式与运行时工具注册、输出非法、状态实体与变化约束、非负数值、unsupported、技能缺失/为空和输入篡改。

控制面接口、权限、快照、批量、删除和真实 MySQL 检查，以及 Studio 浏览器证据见 [验收记录](../control-plane/test-order-case-visualization-validation.md)。

## 2026-11-14 验证焦点生成策略调整

前端按原型收敛为“场景流程 + 验证焦点”后，默认技能进一步调整为以整条用例的核心验证关系组织主图，而非按步骤或图形种类逐项生成。区间图可在同一图块中携带时长约束、独立产物及明确的产生关系；相同对应关系不再重复生成为数量图。普通保存、等待等操作仍由前端场景流程表达，只有是否触发或状态变化本身是验证目标时才增加状态图。

实体名称采用简短业务标签，数值、范围、数量和关系保留在结构字段。`sources/sourceIds` 继续用于内部校验与步骤高亮，生成文字不带“查看依据”等界面操作文案。常规登录前提、非比例示意没有具体坐标等通用说明不直接构成关键覆盖遗漏；真正缺失的预期、条件与不支持的关键关系仍须报告。

本次只调整 `SKILL.md` 的生成指导，1.0 Schema、校验器和 Worker 执行协议不变。已生成产物不会被自动改写；后续新生成或用户手动重新生成时获取当前已发布 Skill。独立代理试跑只能验证这次指令在有限样例上的行为，不替代运行环境实际模型的再生成，也不代表前述 50 条人工验收门槛已经通过。

调整后的独立代理试跑使用原运行产物对应的三段有效区间输入，以及选项集合、保存不触发切片两条输入：三条均通过 `validate_artifact`。区间样例生成 1 个 interval 主图、3 条核验断言、3 个步骤 action 短标签，保留 ≥3 秒、总量 3、一一对应、不拆分和不跨段合并；选项与否定触发样例各 1 个图块。输出保存在本地 `.scratch/test-order-case-visualization/skill-refinement/outputs-v2.json`，不属于运行环境模型的新产物。`test_case_visualization_contract.py` 与 `test_project_skill_space.py` 合计 37 项通过，Skill 元数据校验及协议副本同步检查通过。

已通过既有发布服务更新运行环境的单个系统默认技能，并同步到 `/home/xiaoming/下载/skills/default-skill-new-11-14/mtx-analyze-case-visualization/`。4 个文件均回读 S3 比对内容、大小与 SHA-256；其他技能不变。此次 `SKILL.md` SHA-256 为 `f8cee6e3e76304c7e9c27c591a3b45c6f4a3db3eb1f3a74179e7e1456cb12c5f`。未重新生成或覆盖既有业务图解。

### 状态保持实体与失败提示

`state.change=unchanged` 必须让前态与后态引用同一个非空实体 ID；`changed` 必须引用不同的非空状态实体；`unknown` 可留空。状态图的操作与前/后状态必须分别引用 `action` 和 `state` 实体。数值约束值不得为负。无法确认保持时使用 `unknown`。Worker 检测到状态保持的确定协议错误时回传固定安全提示；控制面只透传白名单提示，其他模型或外部异常仍使用通用错误，避免泄露模型输出或凭据。控制面自行校验成功回传时也识别同一错误。无需迁移或更改协议字段。
