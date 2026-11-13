# 关系判断：完整输入输出示例

这些是虚构、可校验的完整样例，不是当前产品规则。输入中的用例 ID 只属于对应样例。边界有疑问时选读对应分支；不要求实际需求采用相同数量或图形。

## 1. 后续、分支、次级分支及汇合

完整输入：[材料](example-material.json) + [八条完整用例](example-cases.json)。一种有依据的最小图谱见 [输出](example-relations.json)。

| 关系 | 完整输入提供的依据 |
| --- | --- |
| C001 next C002 | 提交产生待处理任务；C002 从待处理状态启动处理，主要目标是处理完成 |
| C002 next C003 | C002 生成正常结果但不查看详情；C003 以正常处理完成为起点验证详情展示 |
| C003 next C007 | 结果详情已打开，后续在详情执行导出，验证独立的导出能力 |
| C002 branch C004 | 同一任务处理的正常路径与失败恢复变化；C004 从可解除的故障开始，实际重试并断言成功，不是从正常成功状态自然接续 |
| C004 next C005 | C004 明确验证重试成功；C005 从这个结果状态验证详情展示 |
| C004 branch C006 | 同一重试操作，将故障解除改为故障持续，结果改为再次失败；本例明确成功恢复为代表场景 |
| C005 next C007 | 重试成功的结果详情也可导出，与正常路径汇合到同一用例 |

主骨为 C001 → C002 → C003 → C007；C004—C005 是分支及其后续，C006 是次级分支。C008 是无业务联系的个人资料检查，由消费者从原 cases 独立展示，不出现在关系 JSON 中。图不要求先执行前一条测试，也不要求 C007 等待两个前序测试完成。

本例对重试结果作了明确区分：若某输入用例只写“重试”而没有成功结果，不能直接假设它 next “查看成功结果”。同一正常路径的其他数据实例也不自动成为补充分支。只保留直接关系，不因为可达就补 C001 → C003 等传递边。

## 2. 只有并列失败场景，没有基础用例

完整输入：[两条历史用例](parallel-cases.json)，明确使用历史模式。对应 [输出](parallel-relations.json) 为合法空图。

H01 的解析故障持续，H02 的写入故障持续；两者分别从独立失败状态开始。正常业务中的解析、写入顺序不能证明 H01 next H02。输入也没有共同处理用例或已确认的代表恢复场景，不能任选 H01 作 H02 的 branch 父节点。两个原用例仍独立显示。

如果另有实际输入用例验证共同的正常处理场景，再核对是否能从该基础分别建立异常分支；不能为了连图补造该节点。

## 3. 综合覆盖与局部覆盖重叠

完整输入：[两条历史用例](overlap-cases.json)，对应 [输出](overlap-relations.json) 为合法空图。

O01 已经验证提交、处理及完整结果；O02 验证其中同样的处理结果，没有新的后续阶段、条件变化或独立补充目标。因此既不依据包含关系建立 next，也不因“更细”建立 branch。关系分析不负责删除重复覆盖或拆分 O01。

若另有用例以处理完成为前提验证尚未覆盖的结果导出，可以继续判断为 next；关键在主要目标与状态衔接，而不是用例长短。

## 4. 配置与业务消费的边界

- A 只修改并保存策略，B 从已生效策略出发提交任务并验证策略被采用：有明确规则支持时可 A next B。
- A 已提交任务并验证策略被采用，B 再验证同一采用行为：覆盖交叠本身不产生 next。
- 只检查未修改时默认值的 A，不能作为升级保留任意历史值 B 的基础；二者没有直接条件派生依据时独立。

## 复现结构校验

从 skill 目录执行：

```bash
python3 scripts/validate.py references/example-relations.json --cases references/example-cases.json --material references/example-material.json --mode canvas
python3 scripts/validate.py references/parallel-relations.json --cases references/parallel-cases.json --mode history
python3 scripts/validate.py references/overlap-relations.json --cases references/overlap-cases.json --mode history
```

脚本检验输入、ID 和图结构；表中的业务理由仍需人工或模型语义复核。主骨 ID、边 ID 及等价展示顺序不是唯一答案，不把示例当作所有需求必须复刻的标准形状。
