# 生成提示词

## 工作流

输入包含 `apiDesign` 时，先按 [设计驱动模式](../references/field-rules.md#12-设计驱动模式) 逐条落实设计，再返回 YAML；以下提取模式步骤不适用。继续优化时以 `currentYaml` 为基线，只修改 `revisionInstruction` 要求的内容。

提取模式（输入没有 `apiDesign`）：

1. 从配置 JSON 读取每个目标接口。
2. 按调用方给出的接口顺序确定执行顺序；调用方未给出时按源配置顺序。
3. 为每个目标接口生成一个正向、全参数用例。
4. 按执行顺序为每个用例分配 `orderNo`，从 `1` 开始逐次加 `1`。
5. 将 method、path、headers、query 和请求体映射到目标用例 schema。
6. 示例值缺失时，按字段类型和约束生成合法正向 mock 值。
7. 扫描响应定义中的提取标记或明确的串联字段，在确有需要时生成 `extractRules`。
8. 只在断言目标可由配置可靠确定，或调用方明确要求更强默认值时生成 `assertRules`。
9. 返回前将 `cases` 按 `orderNo` 升序排序。
10. 只返回最终 YAML 对象。

## 核心规则

字段、排序、请求体、mock 数据、提取规则和断言规则的详细约束统一见 [字段规则](../references/field-rules.md)。

## 行为约束

- 不输出 `request`、`extract`、`validate` 等关键字驱动段落。
- 不把 `{{variable}}` 模板转成硬编码值。
- 不超出调用方提供的 schema 编造目标字段。
- 除非调用方明确要求，不生成负向用例。
- 不遗漏调用方明确要求转换的接口。
