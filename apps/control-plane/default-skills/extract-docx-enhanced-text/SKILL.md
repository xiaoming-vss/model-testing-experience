---
name: extract-docx-enhanced-text
description: 从需求 Word（DOCX）材料中提取正文、表格和有意义图片的业务事实、来源及识别缺口，输出固定文档提取 JSON；用于需求分析第一阶段，不生成最终模块使用理解或测试用例。
---

# Word 需求材料提取与整理

先读取 [输出契约](references/output-contract.md) 和 [schema](references/output-schema.json)，按材料原有顺序和层级提取信息。正式产物必须是一个符合 `document_extraction` 1.0 契约的标准 JSON 对象。平台提供本次产物交接路径时，将完整产物写入该路径，最终仅返回指定文件回执；没有提供交接路径时直接返回完整 JSON。

## 输入

- 需求主文档为本地 Word（DOCX）文件（documentType 为 word/docx），可附用户提供的补充材料或说明；不处理 TXT 主文档。
- DOCX 同时处理正文、列表、表格及有业务含义的图片。富文本需求（documentType 为 richtext）使用 extract-richtext-enhanced-text。

## 提取过程

读取 [事实与来源核对](references/fact-review.md)，用于首次提取及修订的事实判定与交付检查。

1. 检查输入存在且属于支持类型；读取业务内容，并为每个来源登记真实名称、稳定位置和已提供版本。平台提供 sourceName/sourceLocation 时使用该原文件身份，私有 sourcePath 仅用于读取。
2. 先完成事实与来源核对中的“来源预审”，保存内部 extraction-review.json，再整理正式事实。
3. 用 contentBlocks 保留材料层级、段落、列表、表格单元格和有意义图片。表格保留行列和合并跨度；图片说明限于可靠可见信息。
4. 按独立业务判断整理 extractedFacts，保留主体、适用范围、前提、结果和例外。同一判断在概述、流程和验收中重复出现时合并为一条事实，关联各处来源；不同确认状态或独立变化的规则分别记录。控件、选项、默认值、联动、校验及反馈应能被单独引用。
5. 将不可识别、冲突或缺失且影响后续理解的内容记录为 questions，并保留已知部分。确认补充登记为 user_confirmation 来源，并补入对应 extractedFacts；示例保持 example 状态。
6. 逐项完成事实与来源核对，确认原文块与材料相符、每个结论均有足够依据、未解决差异进入 questions。将唯一正式产物 document-extraction.json 保存到平台指定路径，完成结构校验后按本次交接方式返回；修复时修改同一文件，保留未受影响内容。原文层和事实层均保存在该文件中，不为缩短响应生成另一份精简产物。

截图可以证明静态展示，动态行为需要文字说明或明确答复。控件存在不证明自动刷新、重置、条件保留或权限。未知用 null/[] 表达，不补造示例值；需要依据明确不适用时使用 not_applicable。

## 修订

同时使用原材料、当前完整产物和修改指令，生成修订后的完整 JSON 产物，按本次交接方式返回。指定局部修改时保留其他内容；请求全量质量优化或事实去重时，从原材料与答复重建事实分组，当前产物只用于复用有效 ID 和查找来源，不限制需要纠正、拆分、合并的事实范围。保留未受影响的内容、稳定 ID 与未答复问题。明确答复先补入对应 extractedFacts，更新 value、confirmationStatus、sourceReferences；补充来源登记 user_confirmation。原材料 contentBlocks 保持原文，补充材料可新增对应块。

核对问题影响的事实均已补齐后，从 questions 删除已解决问题，清理产物内所有指向该问题的 relatedQuestionIds；不得只删除问题而留下对应未知或冲突事实。部分答复先合并已确认内容，原问题仅描述剩余缺口，status 保持 open，affectedRefs 与 impacts 只保留剩余影响。全部解决时 questions=[]，不保留 resolved 条目或另建问答历史。格式修订、重新提取、阶段审核不等于业务事实确认。
