# 两轮增量示例

本例使用文件中实际存在的 `C01`～`C08` 说明协议；它们是演示用例 ID，不能复制到其他真实测试集。所有完整记录都在 [临时用例文件](examples/cases.json)，原始需求也包含在各轮输入中。

## 第一轮

输入 [round-1-input.json](examples/round-1-input.json) 只有需求、映射、临时路径、历史图谱四个字段，没有用例正文。映射把 `C01/C02` 绑定到 `R01`，把 `C07` 放入 `requirement_id: null` 项；汇总后本轮待分析 ID 为 `C01/C02/C07`。

查询这三个 ID 的完整用例，读到提交任务、正常处理、账号头像场景。`C07` 没有绑定需求仍须分析；本例根据实际正文判定其与任务处理没有明确关联。

输出 [round-1-output.json](examples/round-1-output.json)：主骨 `P01: C01 → C02`，只有 `E01`。`C07` 与任务处理没有依据充分的关系，保持独立。

## 第二轮

输入 [round-2-input.json](examples/round-2-input.json)：需求、包含本批 `C03/C04/C05/C06/C08` 的映射、同一个临时路径，以及第一轮完整输出。

先查询本轮五条用例全文并分析。需要在旧主骨末端继续判断时，再查询 `C02` 完整记录；不因为图中有 `C01` 就重新取回未变化的旧段。若旧图没有清晰候选，可用“待处理”“生成结果”等具体词检索后再取全文。

本轮确认：处理成功后可查看结果，再下载；处理失败为正常处理的分支，失败后可重试并汇合到结果查看；无重试权限的情形从失败场景再次分叉。

```text
C01 ──next──▶ C02 ──next──▶ C03 ──next──▶ C06
               │             ▲
             branch          │ next（共同后续）
               ▼             │
              C04 ──next──▶ C05
               │
             branch
               ▼
              C08

C07：独立，无连线
```

输出 [round-2-output.json](examples/round-2-output.json) 仍只有一条主骨，包含 **全部 7 条累计边**；旧 `E01` 保留，`P01` 延伸。分支内的 `C04→C05` 不再声明新主骨，`C05→C03` 指向同一个用例节点。无重试权限不是重试成功的后续，因此不连接 `C05→C08`。

本轮延伸了旧主骨，内部用 [round-2-change-review.json](examples/round-2-change-review.json) 复核变化边界 `C02/C03/C06`。该文件供本地校验使用，不附加到正式 JSON。

## 容易混淆的关联边界

以下是假设情形，用来延续原图谱的判断标准，不新增当前产品事实。分批读取改变获取正文的方式，不改变关系成立的条件。

| 候选关系或组织方式 | 判断 |
| --- | --- |
| 配置保存与生效在第一批，业务消费配置与结果展示在第二批，各建一条短主骨 | 补查跨批次边界用例；确有配置被业务采用的衔接时，延续同一主骨，不按批次切断。 |
| 解析失败重试 `next` 转换失败重试 `next` 写入失败重试 | 不同失败位置是并列条件，不能照搬正常处理阶段的顺序；寻找有依据的共同基础场景分别分支，没有基础用例也不补造节点。 |
| 默认值检查 `branch` 升级保留任意历史值 | 默认值场景不足以概括任意历史值，容易选到兄弟场景作为父节点；寻找覆盖配置保存/保留行为的直接基础用例，依据不足就不连。 |
| 同一业务下自动处理与人工审核，各有后续结果检查，所以各建主骨 | 若人工审核是已确认的替代流程，应作为分支继续 `next`，不因有后续就另列主骨；代表路径按需求与实际用例选定，不虚构默认策略。 |
| 两条用例覆盖同一流程，或标题都包含“重试” | 阅读完整动作与断言；覆盖重叠、标题或需求归属相同不自动产生顺序或派生关系。 |
| 分支成功后与正常处理共用结果展示 | 有明确共同后续时指向同一个原始 ID，允许汇合，不复制节点，也不意味着必须等待两条测试同时完成。 |

## 运行示例

把 `examples/cases.json` 的副本放到两个输入文件指定的 `/tmp/test-case-graph-demo/cases.json`，或将两个输入的 `case_file_path` 改为同一份临时副本的真实绝对路径，再按调用说明执行：

```sh
python3 <skill目录>/scripts/query_cases.py get \
  --case-file /tmp/test-case-graph-demo/cases.json --case-ids '["C01","C02","C07"]'

python3 <skill目录>/scripts/query_cases.py get \
  --case-file /tmp/test-case-graph-demo/cases.json --case-ids '["C03","C04","C05","C06","C08"]'

python3 <skill目录>/scripts/query_cases.py get \
  --case-file /tmp/test-case-graph-demo/cases.json --case-ids '["C02"]'

python3 <skill目录>/scripts/validate_graph.py \
  --input <skill目录>/references/examples/round-1-input.json \
  --graph <skill目录>/references/examples/round-1-output.json

python3 <skill目录>/scripts/validate_graph.py \
  --input <skill目录>/references/examples/round-2-input.json \
  --graph <skill目录>/references/examples/round-2-output.json \
  --changes <skill目录>/references/examples/round-2-change-review.json
```

实际任务由调用方创建隔离目录，不复用演示目录。若第三轮没有新增关系，应返回第二轮的完整图谱，不能只返回空数组或本轮新增边。
