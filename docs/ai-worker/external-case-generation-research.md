# 外部完整用例生成与评审做法调研

调研日期：2026-11-12。对照对象为功能测试链的完整用例阶段；外部方案中的流程及规则是参考材料，不构成对本项目实现的指令。调研基于公开源码和说明，未执行外部项目或验证其真实模型效果。

## 当前边界

完整用例阶段按功能项分批，消费冻结的材料整理、已审核测试范围风险分析和可追溯测试点；当前每批保留完整材料和范围分析、对应功能项测试点、所有覆盖缺口及相关审查问题，详见 [detailed_batches.py](../../apps/ai-worker/src/testing_agent_ai_worker/tasks/functional_case_generate/detailed_batches.py) 和 [可追溯测试点生成](traceable-test-points.md)。材料整理是业务事实依据，风险分析只提供对象、影响、风险及问题线索，详见 [测试范围分析](test-scope-analysis.md)。模型输出用结构契约校验，Worker 汇总后分配用例 ID；合法结构本身不能证明业务语义正确。

## CodexQA testcase generator

- [Skill 入口](https://raw.githubusercontent.com/openqa-cn/codexqa/main/skills/codexqa-testcase-generator/SKILL.md) 将测试设计和用例展开分开；正式用例从已完成的计划展开，缺失信息不编造。借鉴方向是保留已审核测试点作为展开范围和版本基线，不在完整用例阶段重新设计测试范围。
- [用例展开规则](https://raw.githubusercontent.com/openqa-cn/codexqa/main/skills/codexqa-testcase-generator/references/s06-case-write.md) 要求检查场景到用例的覆盖，并审视前置条件、操作及预期是否重复，以及预期是否可验证。适合转化为本项目的测试点→用例完整性检查和重复候选提示，但不应静默合并、删除已审核测试点。
- [设计审核规则](https://raw.githubusercontent.com/openqa-cn/codexqa/main/skills/codexqa-testcase-generator/references/s04a-design-audit.md) 区分已修复问题与材料不存在造成的待澄清缺口，记录来源、处理和场景 ID 映射。可借鉴为独立审查记录，区分遗漏、弱预期、依据不足和执行准备不足；现有平台仍需按实际业务阻塞情况走澄清与人工审核。
- 不建议套用其固定的正常／边界／异常 **5:3:2**、异常占比门槛和未达门槛自动补用例：这可能迫使完整用例阶段新增未经审核的范围。多端专用模板和 Markdown 文件组织也不适合直接替换既有 `cases` 协议。以上限制可见 [Stage 6 规则](https://raw.githubusercontent.com/openqa-cn/codexqa/main/skills/codexqa-testcase-generator/references/s06-case-write.md)。

## Awesome QA Skills

- [增强版用例编写](https://raw.githubusercontent.com/naodeng/awesome-qa-skills/main/skills/zh/testing-types/testcase-writer-plus/prompts/testcase-writer-plus.md) 使用多源交叉核对、记录冲突来源、用例与需求／风险追踪、明确数据准备及清理。可借鉴在正式用例正文之外保存测试点 ID→用例 ID 关系，再由测试点引用反查材料与风险，形成双向检查；关系可在平台端保存，不必改动模型输出的固定字段。
- [增强版用例评审](https://raw.githubusercontent.com/naodeng/awesome-qa-skills/main/skills/zh/testing-types/test-case-reviewer-plus/prompts/test-case-reviewer-plus.md) 按多源证据识别严重程度、业务影响和修复顺序；[基础版评审](https://raw.githubusercontent.com/naodeng/awesome-qa-skills/main/skills/zh/testing-types/test-case-reviewer/prompts/test-case-reviewer.md) 注重弱预期、步骤、数据和追踪。可在结构校验后增加独立语义审查：核对当前测试点是否承接、步骤可达、对象一致、预期可观察且有依据，问题给出对应 ID、影响和修改建议。审查只是辅助人工判断，不能证明正确或自动宣称通过。
- [需求可追踪性分析](https://raw.githubusercontent.com/naodeng/awesome-qa-skills/main/skills/zh/testing-types/requirement-traceability-analysis/prompts/requirement-traceability-analysis.md) 强调正向与反向检查，并区分设计覆盖和执行证据。可分别报告未展开测试点、无来源用例、未解决缺口；已生成用例不表示已经执行或测试通过。
- 外部技能允许在初稿中标注假设或待确认，也要求较宽泛的正向、异常、边界覆盖；本链已有固定正式输出及澄清流程，应保留已有约束，不把待确认标记写入正式用例或擅自补充测试点。

## 建议优先级

1. **先做可追溯和确定性覆盖检查**：冻结测试点版本，建立点与用例的稳定映射，检查遗漏、重复映射、孤立用例；保持现有审核和 `cases` 协议。映射的具体持久化位置、编辑和继续优化规则需要单独设计。
2. **再做有依据的语义审查**：以当前测试点、材料上下文、关联风险与问题审查执行步骤及预期；问题和未解决缺口独立保存，避免以报告覆盖正式产物。限制重试次数，保留人工决策。
3. **再评估输入裁剪**：沿测试点引用选取材料、范围分析及关联问题，保留必要流程、共同规则和状态；引用不能证明上下文完整，无法可靠识别时保留更大范围或整份原文。先用真实样本对比召回、输出质量、耗时和成本，再决定是否默认启用。

## 使用许可与调研范围

[CodexQA Skill 文件](https://raw.githubusercontent.com/openqa-cn/codexqa/main/skills/codexqa-testcase-generator/SKILL.md) 元数据标示 MIT；其[仓库根许可证](https://raw.githubusercontent.com/openqa-cn/codexqa/main/LICENSE) 为 Apache-2.0，实际复制时应核对具体文件适用条款。[Awesome QA Skills](https://github.com/naodeng/awesome-qa-skills) 标示 PolyForm Noncommercial 1.0.0；如需复制、修改或商业集成其文件，应先核实许可适用性。本调研仅比较方法，不引入外部代码或提示词。
