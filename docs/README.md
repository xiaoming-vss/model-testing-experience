# 文档总索引

全部项目文档统一维护在本目录。`apps/` 保存代码以及简短的 README / AGENTS 入口，避免同一说明维护多份。

## 平台公共文档

- [统一配置、部署与本地开发](deployment.md)
- [MTX 命名与旧部署兼容](naming.md)
- [领域上下文导航](../CONTEXT-MAP.md)

## 各项目文档

| 目录 | 内容 | 对应代码 |
| --- | --- | --- |
| [control-plane](control-plane/README.md) | 控制面：源码结构、配置、接口与鉴权 | [apps/control-plane](../apps/control-plane/) |
| [ai-worker-pi](ai-worker-pi/README.md) | Python + Pi RPC、部署选择与独立运行时 | [apps/ai-worker-pi](../apps/ai-worker-pi/) |
| [ai-worker](ai-worker/README.md) | AI 任务执行、技能预置与轮询协议 | [apps/ai-worker](../apps/ai-worker/) |
| [studio](studio/README.md) | 前端开发、配置与构建 | [apps/studio](../apps/studio/) |
| [api-ui-worker](api-ui-worker/README.md) | API/UI 执行、S3 产物上传与 Worker 配置 | [apps/api-ui-worker](../apps/api-ui-worker/) |
| [integration-worker](integration-worker/README.md) | 独立集成执行、步骤许可、租约与证据恢复 | [apps/integration-worker](../apps/integration-worker/) |

## 公共开发规范

- [领域文档](agents/domain.md)
- [问题跟踪](agents/issue-tracker.md)
- [分诊标签](agents/triage-labels.md)

项目文档中的开发命令和源码相对路径默认以对应 `apps/<项目>/` 为工作目录；平台部署指南的命令在仓库根目录执行。明确以 `docs/`、`apps/`、`scripts/` 开头的路径均相对仓库根目录。
