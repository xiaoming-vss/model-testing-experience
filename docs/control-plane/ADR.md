# Control-plane ADR 索引

- 状态：现行
- 负责人：control-plane maintainers
- 最近复核：2026-11-20
- 复核周期：每季度
- 适用范围：`docs/control-plane/adr/`
- 变更/废弃：按[规范变更检查清单](../agents/domain.md#规范变更检查清单)执行。

仓库级导航见[文档总索引](../README.md)，跨项目长期记录见[长期记录](../records/README.md)。

## 决策列表

- [0001 功能测试的执行结果由平台拥有](adr/0001-platform-owns-functional-test-execution-results.md)
- [0002 测试单不带轮次，多轮执行即多张测试单](adr/0002-test-order-has-no-rounds.md)
- [0003 候选生成结果可以删除，已导入的也不阻止](adr/0003-candidate-run-deletion.md)
- [0004 平台内置 Bug 资源与禅道缺陷并存](adr/0004-native-bug-resource.md)
- [0005 Bug 生命周期对齐禅道](adr/0005-bug-zentao-lifecycle.md)
- [0006 独立集成执行与持久化写入意图](adr/0006-independent-integration-execution.md)
- [0007 正文漂移按平台内容覆盖禅道](adr/0007-description-drift-overwrite.md)
- [0008 裁剪只写留痕列并单源化 LLM 凭据](adr/0008-trim-writeonly-columns-and-single-source-llm-credentials.md)
- [0009 测试报告与测试单图谱支持逐条删除](adr/0009-auxiliary-ai-history-deletion.md)
- [0010 统一 AI 执行模型](adr/0010-unified-ai-execution.md)
- [0011 UI 生成改用仓库画像版本作为源码来源](adr/0011-ui-generation-repository-source.md)
- [0012 接口库作为项目级测试生成输入](adr/0012-project-interface-library.md)
- [0013 软件仓库作为代码上下文，API 生成改用接口库](adr/0013-software-repository-and-interface-library-api-generation.md)
- [0014 预发布阶段单一基线](adr/0014-pre-release-single-baseline.md)
- [0015 软件仓库直接绑定 GitLab 仓库](adr/0015-software-repository-direct-gitlab-binding.md)
- [0016 接口库标签分组与导入标签归属](adr/0016-interface-library-tag-groups.md)
- [0017 API 生成先设计后生成](adr/0017-api-design-before-generation.md)
- [0018 需求评审作为提示性首阶段](adr/0018-requirement-review-advisory.md)
- [0019 性能运行冻结监控接入快照，首期只提供 Grafana 入口](adr/0019-performance-monitoring-snapshot.md)
- [0020 性能测试首期只保留 Remote Write 监控接入](adr/0020-performance-remote-write-only.md)
- [0021 性能测试集按顺序串行执行用例](adr/0021-performance-suite-serial-execution.md)
- [0022 移除性能测试集与用例的启用状态](adr/0022-remove-performance-enabled-state.md)
- [0023 禅道/GitLab 连接的传输安全策略](adr/0023-external-connection-transport-security.md)
- [0024 生成链多候选与唯一当前结果](adr/0024-generation-candidates-current.md)
- [0025 阶段采用是独立指针](adr/0025-independent-stage-adoption.md)
- [0026 用例失效是独立的生命周期标记](adr/0026-case-invalidation-marker.md)
- [0027 API/UI 测试集归项目所有，需求仅作可选关联](adr/0027-project-owned-api-ui-test-suites.md)
