# ADR 0028：历史需求关联阶段

- 状态：已接受
- 日期：2026-11-25
- 取代：—
- 被取代：—
- 关联：[生成链](../generation-chain.md)、[ADR 0025](0025-independent-stage-adoption.md)

材料整理采用后，可以从 `requirement_analysis` 链派发 `historical_requirement_relations` 阶段。历史关联与功能测试范围分析分别使用材料整理的采用结果、各自的尝试和模型会话。阶段产物沿用候选和采用流程。

控制面按项目读取可用的历史材料整理条目，按功能检索和排序。历史材料中不符合可读说明契约的条目跳过，不阻断本次派发。条目只取「功能使用与业务规则」和「完整业务流程」两个章节；功能存在这两个章节时，其他章节不进入输入。每次尝试冻结本次材料来源、命中的历史条目，以及由这些快照支持的已确认关系。AI Worker 以 `run.sourceContent` 读取冻结的 `historical_requirement_relation_input` 0.1 JSON，通过默认 Skill `mtx-analyze-historical-requirement-relations` 生成 `historical_requirement_relation_analysis` 0.1 JSON。空历史输入可以直接形成空关联结果。控制面按本次输入校验回传中的材料、条目和影响项引用。

候选与当前内容读取通过 `materialContent` 向 Studio 返回与 Worker 相同的冻结输入，用于还原历史条目和本次条目的原文。该输入只含条目文本，不含材料原文块；历史用例核验同样返回冻结输入，见 [ADR 0029](0029-historical-test-case-verification-stage.md)，其他阶段的冻结输入仍不返回 Studio。历史需求的名称和迭代不在输入里，由 Studio 按需求 ID 查找。

现有 `requirement_analysis` 任务类型承载新增阶段。材料整理和历史关联各自使用终态回传并保存候选。旧生成链在首次派发前展示空状态，派发事务分配阶段和空槽。Studio 将历史需求关联、测试范围风险分析和仓库画像直接连接到材料整理。本次接入同时包含历史用例核验阶段，见 [ADR 0029](0029-historical-test-case-verification-stage.md)。发布时需同步默认 Skill 并部署识别新阶段的 Worker。
