# 文档提取 JSON 契约

字段、类型和层级以 [output-schema.json](output-schema.json) 为准；[output-example.json](output-example.json) 演示结构，其中的业务内容全部是 example，不是当前产品事实。

顶层包含 schemaVersion、artifactType、documentTitle、sources、contentBlocks、extractedFacts、questions。固定 schemaVersion 为 "1.0"、artifactType 为 "document_extraction"。所有对象保留全部必填字段，数组没有实际条目时为 []，不生成占位记录。

## 内容与来源

contentBlocks 的 kind 为 section/paragraph/list/table/image，parentId 关联父块，同级按数组顺序展示。只填当前类型对应的 text/items/table/image，其它字段为 null 或 []。table 的 cells 保存真实单元格文本、行列和跨度；识别不出的内容为 null，不伪造行列。整表不可读时 rowCount/columnCount 为 null、cells 为 []，parseStatus 为 unreadable，并关联问题。

extractedFacts 使用 scope/actor/entry/operation/control/option/default/trigger/dependency/result/pagination/sorting/validation/business_rule/other 分类，fact 关联 sourceReferences 和 relatedQuestionIds。relatedBlockIds 指向当前产物的材料块。

sources 的 type 区分原文 document/text、prototype/screenshot/design、用户确认 user_confirmation 及示例 example。location 使用真实稳定定位；临时签名 URL、凭据和私有运行临时路径不进入产物，无法确定稳定位置时为 null。version 没提供时为 null，不把产物 schemaVersion 当需求版本。

## 事实与问题

fact 包含 value、confirmationStatus、sourceReferences、relatedQuestionIds。value 支持标量、标量数组或 null。confirmed 为有明确可定位依据的事实，unconfirmed 保留未知或部分已知，conflicting 保留冲突并引用 open 问题，example 为演示信息，not_applicable 有范围依据且 value=null。confirmed/example/not_applicable/conflicting 至少引用一个来源；完全未知内容使用 unconfirmed。

questions 包含 id、question、status、affectedRefs、impacts、sourceReferences、answer。affectedRefs 指向 block 或 extracted_fact。impacts 区分影响的阶段与是否阻塞。questions 仅包含 status=open 的剩余缺口。明确答复先写入受影响 extractedFacts，更新状态和来源，再删除已解决问题及其全部 relatedQuestionIds；不输出 resolved 条目或问答历史。部分解决时问题文案、affectedRefs 与 impacts 收窄到剩余缺口，answer 为 null 或理解该缺口仍必需的部分信息，已确认业务结论以事实正文为准。全部解决时 questions=[]。提取完成与审核通过不自动解决问题。

正式产物只包含一个标准 JSON 对象；无围栏、说明或 JSON 外问题清单。平台指定产物文件路径时，完整 JSON 写入指定文件，最终响应仅返回平台要求的文件回执；否则直接返回完整 JSON。文件回执不是业务产物，不进入页面或下游分析。层级、字段类型、ID 唯一、来源及问题引用均需自查。技能只整理业务材料，不提前编写完整模块使用理解。
