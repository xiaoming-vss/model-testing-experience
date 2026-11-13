# 功能测试范围分析

功能测试生成链的“测试范围风险分析”阶段读取已审核的材料整理 JSON（`readable_requirement_material` 0.2），生成 `test_scope_impact_risk` 1.0：`testObjects`、`impactAreas`、`risks` 和 `openQuestions`。分析识别业务对象、影响与风险，不独立确立业务规则；接口对象及技术调用链不在该阶段范围内。测试点和详细用例生成仍须以材料和明确用户答复核对业务条件与预期。

条目用 `sourceBlockIds` 关联材料块，问题可用 `sourceQuestionIds` 关联原有问题；`basisStatus` 区分 `confirmed`、`inferred` 和 `unconfirmed`。Worker 校验新输出结构、内部 ID 以及可取得的输入材料引用。控制面在保存和审核新版产物时校验同一结构和可取得的冻结材料引用。结构和引用校验不能证明模型判断的语义正确。

分析阶段的新增业务答复需要先补充到材料整理并审核，再作为已确认事实；分析修订不能把不在材料中的答复当成已确认依据。旧格式分析结果不再受支持，使用下游阶段前需要重新生成并审核测试范围风险分析。系统默认技能从控制面技能库按需下载，技能更新按[技能同步流程](../control-plane/skills.md)执行。
