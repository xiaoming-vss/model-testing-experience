# 2026-11-22 阶段采用改为独立指针

- 状态：已实施
- 负责人：platform maintainers
- 来源：2026-11-22 需求生成链采用语义讨论与实施计划
- 关联：[ADR 0025](../control-plane/adr/0025-independent-stage-adoption.md)、[生成链现状](../control-plane/generation-chain.md)、[ADR 0024](../control-plane/adr/0024-generation-candidates-current.md)

## 结论

`ai_generation_stage_contents.source_candidate_id` 是阶段本地采用指针。上游换采用不会改变或阻塞下游当前内容、候选采用和正式导入；采用和导入只校验该内容自身的冻结来源闭包、根输入、目标与并发令牌。需求原文件或 API/UI 根资源变化仍会使依赖内容失效。

## 实施内容

- 删除采用、生成、导入和仓库画像读取中的祖先当前采用比对；删除 `upstreamAlignment`、对齐查询服务和 `SourceClosure.adoption_blocks`。
- 采用预检只报告目标槽位/候选并发变化；`AdoptionBlockReason` 收缩为 `source_stale`、`source_unknown`、`source_conflict`、`concurrent_change`。
- 普通生成仍读取必需上游的阶段当前内容，并重新锁定槽位确认读取期间未切换；多上游分支冲突继续返回 `source_conflict`，提示用试生成选择一致来源。
- 导入使用叶子内容自身冻结的闭包和 `upstream_outputs`，并校验槽位内容、格式与内容/依据/血缘摘要同候选一致。
- 仓库画像采用/读取校验画像候选自己记录的 `requirementMaterialCurrent`、需求正文、内容/依据/血缘摘要和当前文档根哈希，不再依赖当前材料槽位；材料槽位自身仍需自洽。
- 当前内容与候选详情新增 `basisSources`，从冻结 manifest 投影阶段、候选、快照、直接选择和来源种类；Studio 用“依据”替代“上游对齐”，当前内容不再显示生成方式。
- 无数据库迁移；共享冻结输入契约不变。

## 契约与兼容

- 删除 `GET /stages/{stage}/current` 的 `upstreamAlignment`；新增 `basisSources`。Studio 同步读取，字段缺失时显示“依据未记录”。
- 采用预检不再返回 `pending_upstream` 或 `source_mismatch` 作为阶段采用阻塞；`source_conflict` 文案引导用户用试生成选择同一分支。
- Control-plane、Studio 与 AI Worker 的冻结输入夹具保持一致；AI Worker 消费的 `FrozenCandidateInput` 结构未变。

## 验证

- Control-plane：`uv run --locked --extra dev python scripts/check.py` 通过 Ruff、格式、mypy 和全量 SQLite 测试，结果为 `1813 passed, 148 skipped, 3 subtests passed`（148 项为未提供一次性 MySQL/存储环境的跳过项）。
- 生成链 MySQL 专项：在一次性空库上运行采用、派发、导入、来源解析、根输入、文档失效、完成、存储和链初始化等 14 个文件，`23 passed`。
- Studio：`npm run verify` 通过 type-check、lint、主题、CSS、边界、Tailwind、构建、bundle 和单测，`201 passed` 测试文件、`1006 passed` 用例。
- AI Worker：`uv run --locked --group dev python -m unittest discover -s tests -v`，`547` 项通过，`5` 项跳过。
- 文档：`python3 scripts/check_docs.py` 通过（141 个 Markdown、95 个 skill 文件链接检查）。
- 本地浏览器验收：需求 `f6ae9a81-05e8-42f1-bbfb-6121581306d4` 的“测试点”仍显示“已采用”，侧栏“来源与依据”为“测试范围风险分析 367c3908 · 材料整理 c56c732f”，而当时材料整理当前采用是 `457ade72`；界面无“上游对齐”。API 设计当前依据为 `b0f861c2`，接口配置提取当前已是 `7a390487`，阶段仍保持采用。接口库根快照已变化，因此另一候选的采用预检返回 `source_stale`，证明根输入失效规则仍在，而不是上游指针变化导致阻塞。详细视觉记录见 [Studio 候选工作区视觉验收](../studio/records/2026-11-22-independent-adoption-visual-check.md)。

## 边界

- 多上游不属于同一完整分支时仍拒绝生成；本次不实现自动修复分支或一键对齐。
- 旧生成历史和已在途请求不迁移；历史 ADR 与记录保持原结论，仅标注被取代。
- 真实模型、GitLab 和对象存储未在本记录中重新执行；本地浏览器验收使用已有开发库数据，不代表生产部署验收。
