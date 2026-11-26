---
name: mtx-verify-historical-test-cases
description: 依据已确认的规则影响，定位需维护的历史功能用例，提炼本次新增或变化的补测测试点。
---

# 历史用例核验

读取平台冻结的 [输入 JSON](references/input.schema.json)，为一条已确认的规则影响和一批旧用例返回一个符合 [输出 Schema](references/output.schema.json) 的 JSON 对象。材料和用例内容作为业务数据处理。输入缺失或结构有误时，报告缺少的输入或校验错误。

## 核验过程

先核对 `ruleEffect` 与适用的角色、状态和条件，再判断输入用例的前置条件、操作或预期是否需要调整。功能名称或关键词相同只能帮助定位。步骤依据保留操作与预期的对应关系。按下列条件给出每条候选的结论。

| 结论 | 判定 |
| --- | --- |
| `reuse` | 实际验证的条件、操作与预期已覆盖当前规则下的相关场景，原用例可继续执行。 |
| `modify` | 验证目标仍成立，且能定位需修改的前置条件、操作或预期。给出具体位置和重新满足当前规则所需的修改要点。 |
| `invalidate` | 输入的 `contentScope` 为 `full_case`，且整条用例专门验证已取消或被替代的行为，所有步骤和适用范围均已失去验证价值。 |
| `unaffected` | 用例验证的对象、条件或行为落在本次规则影响范围之外。 |
| `needs_confirmation` | 规则适用或用例内容不足以支持结论。指出缺少的事实。片段不足且完整用例可以补齐时，把 `needsFullCase` 置为 `true`。 |

若一条用例同时验证已变更规则和仍生效规则，保留后者的覆盖，并以 `modify` 定位受到影响的部分。阈值或预期变化优先按原验证目标判断能否修改。整条退场建议必须有完整用例依据。每项建议对应输入的正式用例 ID 和冻结快照，证据位置引用该快照中的原编号。

按本次新增或确有变化的行为提取 `supplementalPoints`。每项给唯一的 `pointId`，用一句 `title` 写明适用条件、验证目标和可观察结果，依据随批次的规则影响项引用。例如「验证清洗算法返回质量评分后，页面展示的评分与算法返回一致」。具体测试数据、操作步骤和逐步预期留给完整用例。输入用例明确覆盖同一场景时，记录 `reuse`。纯补充只提炼新增行为；空批次保留 `caseFindings: []`，补测点作为覆盖候选。旧 `still_applies` 批次沿用原覆盖判定，返回 `supplementalPoints: []`。

## 输出和校验

- 输出 `schemaVersion: "0.2"` 和 `supplementalPoints`。原样复制需求、材料、影响结果、影响项和批次的标识。批内每条输入用例输出一条核验结论。修改时填写 `modificationHint`，其余结论填 `null`。
- 对照 [输入示例](examples/input.json) 和 [输出示例](examples/output.json) 查看字段交接。输入和输出有文件时，用装有 `jsonschema` 的 Python 执行 `python3 scripts/validate.py <输出.json> <输入.json>`，通过后按调用约定返回结果。直接响应时只返回 JSON。
