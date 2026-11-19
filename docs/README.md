# 文档总索引

全部项目文档统一维护在本目录。`apps/` 保存代码以及简短的 README / AGENTS 入口，避免同一说明维护多份。长期规格快照与验收证据见[长期记录](records/README.md)；本地 `.scratch/` 只放进行中的工作草稿。

## 平台公共文档

- [验证命令矩阵](commands.md)
- [统一配置、部署与本地开发](deployment.md)
- [Kubernetes 部署](deployment-k8s.md)
- [发布检查清单](release-checklist.md)
- [变更日志](../CHANGELOG.md)
- [MTX 命名与旧部署兼容](naming.md)
- [领域上下文导航](../CONTEXT-MAP.md)
- [长期记录与 `.scratch` 边界](records/README.md)

## 各项目文档

| 目录 | 内容 | 对应代码 |
| --- | --- | --- |
| [control-plane](control-plane/README.md) | 控制面：源码结构、配置、接口与鉴权 | [apps/control-plane](../apps/control-plane/) |
| [ai-worker](ai-worker/README.md)、[Pi 后端](ai-worker/pi-backend.md) | AI 任务执行、技能预置、轮询协议与执行底座 | [apps/ai-worker](../apps/ai-worker/) |
| [studio](studio/README.md) | 前端开发、配置与构建 | [apps/studio](../apps/studio/) |
| [api-ui-worker](api-ui-worker/README.md) | API/UI 执行、S3 产物上传与 Worker 配置 | [apps/api-ui-worker](../apps/api-ui-worker/) |
| [integration-worker](integration-worker/README.md) | 独立集成执行、步骤许可、租约与证据恢复 | [apps/integration-worker](../apps/integration-worker/) |
| [perf-worker](perf-worker/README.md) | 性能执行、运行规格、固定 k6 模板与结果契约 | [apps/perf-worker](../apps/perf-worker/) |

## 项目开发规则

- [control-plane 开发规则](control-plane/development-rules.md)
- [ai-worker 开发规则](ai-worker/development-rules.md)
- [api-ui-worker 开发规则](api-ui-worker/development-rules.md)
- [integration-worker 开发规则](integration-worker/development-rules.md)
- [perf-worker 开发规则](perf-worker/development-rules.md)
- [studio 结构与代码规范](studio/STRUCTURE.md) / [界面与交互规范](studio/UI-GUIDELINES.md)
- 各项目启动与目录入口见对应 `README.md` 和 `apps/<项目>/AGENTS.md`。

## 架构决策（ADR）

- [control-plane ADR 索引](control-plane/ADR.md)
- [studio ADR 索引](studio/ADR.md)
- [ai-worker ADR 索引](ai-worker/ADR.md)
- [perf-worker ADR 索引](perf-worker/ADR.md)
- api-ui-worker 与 integration-worker 当前没有独立 ADR 目录，跨项目决策记录在 control-plane ADR。

## 公共开发规范

- [领域文档](agents/domain.md)
- [规范治理与变更检查清单](agents/domain.md#规范变更检查清单)
- [后端开发规则](agents/backend-development.md)
- [Worker 通用约定](agents/worker-conventions.md)
- [API 变更检查清单](agents/api-change-checklist.md)
- [问题跟踪](agents/issue-tracker.md)
- [分诊标签](agents/triage-labels.md)

## 长期记录

- [记录索引与维护规则](records/README.md)
- [control-plane 记录](control-plane/records/README.md)
- [studio 记录](studio/records/README.md)

项目文档中的开发命令和源码相对路径默认以对应 `apps/<项目>/` 为工作目录；平台部署指南的命令在仓库根目录执行。明确以 `docs/`、`apps/`、`scripts/` 开头的路径均相对仓库根目录。
