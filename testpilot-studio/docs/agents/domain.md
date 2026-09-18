# 领域文档

本文件定义工程技能在探索代码库时应如何读取和使用本仓库的领域文档。

## 探索代码前应读取

- 仓库根目录的 **`CONTEXT.md`**；或者
- 如果仓库根目录存在 **`CONTEXT-MAP.md`**，则按照其中的指引查找各上下文对应的 `CONTEXT.md`，并读取与当前任务有关的文件。
- **`docs/adr/`** 中与当前工作范围有关的 ADR。在 multi-context 仓库中，还应检查 `src/<context>/docs/adr/` 下对应上下文的决策记录。

如果这些文件不存在，**直接继续，不要提示**。不要报告文件缺失，也不要预先建议创建它们。`/domain-modeling` 技能会在术语或架构决策真正确定后按需创建这些文件；该技能通常通过 `/grill-with-docs` 或 `/improve-codebase-architecture` 调用。

## 文件结构

本仓库采用 single-context 布局：

```text
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

如果未来演变为 multi-context 仓库，则在根目录增加 `CONTEXT-MAP.md`：

```text
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← 系统级决策
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← 上下文专属决策
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## 使用领域词汇表中的术语

当输出内容需要命名领域概念时，例如 Issue 标题、重构建议、假设或测试名称，应使用 `CONTEXT.md` 中定义的术语，不要改用词汇表明确排除的同义词。

如果所需概念尚未出现在词汇表中，这通常意味着两种情况之一：正在引入项目并未使用的语言，此时应重新考虑；或者领域模型确实存在缺口，此时应记录并交由 `/domain-modeling` 处理。

## 标明与 ADR 的冲突

如果输出内容与已有 ADR 冲突，应明确指出，而不是静默覆盖原有决策：

> _与 ADR-0007（订单采用事件溯源）冲突——但值得重新讨论，因为……_
