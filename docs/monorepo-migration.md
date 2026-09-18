# 单仓库迁移说明

来源：`/home/xiaoming/GitCloneData-bak` 下五个项目的当前工作目录。
目标：`/home/xiaoming/testing-agent`。

以当前磁盘文件为准，保留未提交修改和未被忽略的新增源码，已删除文件不恢复。旧 `.git` 不复制，也不合并提交历史；原备份目录不修改。依赖缓存、虚拟环境、构建产物、被忽略的本机配置、运行数据以及个人 Agent/IDE 工具目录不迁移。复制清单记录在 `migration-files.json`。

整合保持各项目包名、内部目录、独立锁文件、Python 版本和原有业务代码。根目录加入管理脚本、统一配置示例、Compose 编排和管理脚本测试。

AI Worker 原 `config/worker.toml` 含本地凭据和机器路径，转为无凭据的 `worker.example.toml`；运行文件由统一配置生成并忽略。Dockerfile 默认使用示例，Docker 构建上下文排除实际 worker.toml，部署通过只读挂载注入运行配置。

没有复制原数据库、上传文件、Nanobot 会话或项目技能目录。原平台数据需要另行制定备份与迁移操作，本次新部署使用独立空数据库。

各子项目保留原 `AGENTS.md`、领域文档及 ADR；修改子项目业务代码时继续遵守其约定。

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
