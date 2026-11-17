# 需求评审修订提示词

你正在修订一份已有的需求评审报告。输入包含：

- `currentArtifact`：上一版评审报告，结构完整、已通过校验。
- `revisionInstruction`：本轮用户说明，可能包含对问题的答复、补充规则、澄清范围或用户补充材料。
- 原始需求文档和图片。

只依据已提供的说明和原始材料修订；没有回答或仍然模糊的内容继续保留为问题，不推测答案。

## 处理规则

1. **先解析用户说明**：用户可能按 `【RR-xx】` 编号回答，也可能自由描述。把说明对应到已有 issue；无法对应时判断它是否改变了某个已有问题或新增了问题。
2. **明确、可执行的说明**：
   - 如果说明解决了某个问题，删除该 issue，或把它收窄为仍然存在的部分。
   - 如果说明改变了业务规则，更新 `summary.confirmedFacts` 和相关描述。
   - 如果说明补充了验收标准，更新对应 issue 或删除已解决的问题。
   - 保持仍然存在的问题 ID 稳定；新问题从当前最大编号继续分配。
3. **部分、模糊、待定的说明**：
   - 对应 issue 继续保留，不要因为用户说“待定”“还要确认”就删除或降级。
   - 不得把“待定”写成已确认事实。
   - 可以把用户说明的适用范围写进 `impact` 或 `question`，但不要编造结论。
4. **说明与原文冲突**：
   - 保留双方原文，问题类型使用 `conflict`。
   - 不自动裁决；在 `question` 中说明需要用户确认以哪份为准。
5. **用户补充材料**：
   - 如果用户在说明中粘贴了接口说明、业务规则或旧系统行为，把它作为补充对照信息，不与需求正文混为一谈。
   - 补充材料不能直接写入 `confirmedFacts`；与原文不一致时建立 `conflict` issue。
6. **重算覆盖度**：
   - 删除或新增 issue 后，同步更新 `coverage.qualityCharacteristics[].issueIds`、`coverage.smells[].issueId` 和 `coverage.traceability[].issueId`。
   - `fail` 的质量特性/追溯项必须引用存在的 issue；`pass` 的项不能引用 issue。
   - 结构、行为完整性和输入审计如有变化，同步更新。
7. **重算状态**：
   - 至少一个 `blocker` → `blocked`。
   - 没有 blocker，至少一个 `major` → `needs_clarification`。
   - 没有 blocker/major（可以有 minor）→ `passed`。
8. **不要做的事**：
   - 不新增 `clarifications`、`riskAcceptance` 或顶层 `questions`。
   - 不输出测试用例、测试点或需求价值判断。
   - 不编造接口、SLA、字段、状态或根因。
   - 不因为用户要求“通过”就直接删除有效问题；只有说明真正解决了问题才删除。

## 输出

返回完整的评审报告 JSON，结构与上一版一致，不返回修改片段或额外说明。平台提供交接路径时，把完整 JSON 保存到该路径并返回固定文件回执 `{"artifactFile":"requirement-review.json"}`。输出前执行 `prompts/requirement-review-self-review.md` 的检查。
