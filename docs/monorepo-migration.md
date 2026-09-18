# 单仓库迁移说明

来源：`/home/xiaoming/GitCloneData-bak` 下五个项目的当前工作目录。
目标：`/home/xiaoming/testing-agent`。

以当前磁盘文件为准，保留未提交修改和未被忽略的新增源码，已删除文件不恢复。旧 `.git` 不复制，也不合并提交历史；原备份目录不修改。依赖缓存、虚拟环境、构建产物、被忽略的本机配置、运行数据以及个人 Agent/IDE 工具目录不迁移。复制清单记录在 `migration-files.json`。

整合保持各项目包名、内部目录、独立锁文件、Python 版本和原有业务代码。根目录加入管理脚本、统一配置示例、Compose 编排和管理脚本测试。

AI Worker 原 `config/worker.toml` 含本地凭据和机器路径，转为无凭据的 `worker.example.toml`；运行文件由统一配置生成并忽略。Dockerfile 默认使用示例，Docker 构建上下文排除实际 worker.toml，部署通过只读挂载注入运行配置。

没有复制原数据库、上传文件、Nanobot 会话或项目技能目录。原平台数据需要另行制定备份与迁移操作，本次新部署使用独立空数据库。

各子项目保留 `AGENTS.md` 入口；领域文档与 ADR 现统一存放于 `docs/<项目>/`，修改业务代码时继续遵守其中的约定。

## 当前目录映射

后续整理将应用统一移至 `apps/`，不改变包名、镜像名、Compose 服务名或启动命令：

| 原目录 / 复制清单中的仓库名称 | 当前目录 |
| --- | --- |
| `testing-agent-control-plane` | `apps/control-plane` |
| `testing-agent-ai-worker` | `apps/ai-worker` |
| `testing-agent-api-ui-worker` | `apps/api-ui-worker` |
| `testing-agent-connector-zentao` | `apps/connector-zentao` |
| `testpilot-studio` | `apps/studio` |

`migration-files.json` 保留原仓库名称，用于追溯第一次复制的来源；定位当前文件时按上表映射。统一主配置和持久化卷名称保持兼容，根目录管理命令不变。

## 文档集中管理

全部项目文档集中到根目录 `docs/`，入口为 [文档总索引](README.md)。

- `apps/<项目>/docs/*` 移至 `docs/<项目>/*`，保留项目专属 ADR、规格、接口和验证记录的分类。
- 原项目完整 README、CONTEXT、AI Worker PRD、前端 design-qa 和组件说明同样迁入对应文档目录。
- `apps/<项目>/README.md` 保留简短导航和启动入口，兼容项目独立阅读与 Python 包元数据；AGENTS 入口指向公共规范及该项目的上下文。
- 三套重复开发规范合并为 `docs/agents/`；整套平台的配置和部署集中于 [部署指南](deployment.md)。
- `migration-files.json` 是第一次复制时的历史清单，不是当前路径索引。历史清单中的 `docs/`、CONTEXT 等文档条目应按本节规则定位。

文档中的普通源码路径和命令仍相对对应应用目录；文档链接已按集中后的目录重新计算。未提交的历史 `.scratch` 规格不补造内容；已有失效链接改为历史说明并指向现有验证记录。
