# 测试点与覆盖缺口示例

在边界推导、未知处置或字段组合不清楚时读取。以下是假设输入，不得将其中模块、数值、ID 用作真实需求。

## 已知规则与未知规则分开

假设已审核材料包含：

- 材料块 `b-quantity`：“提交数量只允许 1 到 99 的整数，含端点；合法数量允许提交，非法数量拒绝提交。”
- 材料块 `b-edit`：“本次需验证多用户并发编辑同一记录时的冲突处理”，问题 `q-edit` 尚未确认采用拒绝后写、覆盖还是其他策略。
- 配套范围分析未另列对象、影响、风险或问题；这不表示实际没有风险。

可以为数量的已知边界设计确定目标；并发冲突的具体预期记为缺口，不能自选一种策略。以下为展示两种条目结构的片段式覆盖示例，不声称覆盖了数量规则的所有边界与非法输入。

```json
{
  "schemaVersion": "1.0",
  "artifactType": "traceable_test_points",
  "reviewStatus": "self_review_only",
  "testPoints": [
    {
      "id": "tp-1",
      "module": "数量提交",
      "dimension": "边界场景",
      "name": "【数量提交】验证提交数量为1时允许提交",
      "basis": "derived",
      "materialBlockIds": ["b-quantity"],
      "testObjectIds": [],
      "impactAreaIds": [],
      "riskIds": [],
      "materialQuestionIds": [],
      "scopeQuestionIds": []
    }
  ],
  "coverageGaps": [
    {
      "id": "gap-1",
      "description": "并发编辑同一记录时的冲突处理策略尚未确认。",
      "blockedCoverage": "暂缓判断并发编辑发生冲突时各次写入的受理结果及最终记录内容。",
      "materialBlockIds": ["b-edit"],
      "testObjectIds": [],
      "impactAreaIds": [],
      "riskIds": [],
      "materialQuestionIds": ["q-edit"],
      "scopeQuestionIds": []
    }
  ]
}
```

`derived` 表示从明确范围推出端点实例；若直接复述材料明确列出的行为则用 `direct`。缺口必须说明暂缓什么判断，而非只写“并发规则待确认”。已知数量目标不因并发问题被一起暂缓。

## 独立目标与无效条件

假设只有账户有效且权限开关开启时允许访问报告，停用账户始终拒绝。

- 验证开关：用有效账户，分别设计开关状态对应的访问目标。
- 验证账户资格：用停用账户，验证其拒绝规则。
- 错误设计：仅用停用账户证明开关生效。开关实现错误时账户也可能因停用而被拒绝，观察无法区分目标错误。

这不意味着否定场景没有价值；应让它验证实际能判断的规则。跨对象一致性本身是目标时，仍可保留一个不可拆分的关系目标。
