# 统一配置、部署与本地开发

以下命令均在仓库根目录执行。各应用的命令和专项检查见 [文档总索引](README.md)。

## 统一配置

管理脚本要求 Python 3.11+，本地运行 AI Worker 要求 Python 3.13（uv 根据各项目的版本文件管理解释器）。

```sh
python3 scripts/manage.py init
```

编辑 `config/platform.toml`。首次初始化会生成随机数据库密码、JWT 密钥、集成密钥和 Worker 令牌，重复执行不会覆盖。该文件以及生成的运行配置均被 Git 忽略。提交示例文件 `config/platform.example.toml`，不要提交实际配置。

`shared` 统一定义服务地址、发布端口及认证密钥；`database` 定义数据库用户和密码。`control_plane`、`ai_worker`、`api_ui_worker`、`zentao` 区块递归覆盖各项目示例配置中的同名字段。地址、令牌、监听端口和存储路径最终由管理脚本按运行模式统一设置。

默认只允许本机访问。服务器部署时将 `shared.public_host` 改为浏览器能访问的服务器 IP/域名，将 `shared.bind_host` 改为 `0.0.0.0`。当前编排提供 HTTP；域名 HTTPS 可由部署环境的反向代理提供。UI 截图地址也需要浏览器能访问。

## Docker 整体启动

要求 Docker Engine 和支持健康检查依赖的 Docker Compose v2+。

```sh
python3 scripts/manage.py compose up -d --build
python3 scripts/manage.py compose ps
python3 scripts/manage.py compose logs -f
```

默认前端地址：http://127.0.0.1:8081 。控制面对外 19000（容器内 9000），禅道 8010，截图服务 9010，MySQL 映射到 13306。

启动顺序：MySQL 就绪 → migrate 执行 `alembic upgrade head` → 控制面就绪 → 前端与 Worker。数据库使用独立持久卷，控制面文件、AI 会话、日志和截图也使用持久卷。第一次部署初始化空数据库，原备份目录中的数据库及运行数据不会自动导入。

AI 任务需要先配置平台中的模型服务及个人授权，并按项目预置 Skill 包。遵循 AI Worker 的 ADR-0002，在 `ai-runtime` 卷的 `/data/runtime/workspaces/project-<项目ID>/skills/` 下放置技能目录（包含 `SKILL.md`）；本地对应 AI Worker 项目下的 `runtime/workspaces/`。代码迁移不等于模型、技能和业务数据迁移。

停止服务并保留数据：

```sh
python3 scripts/manage.py compose down
```

已有 MySQL 卷初始化后，修改统一配置中的数据库密码不会自动更改数据库内的账号密码，需要配合数据库账号管理操作。

## 单独构建和更新

```sh
# 构建单个项目
python3 scripts/manage.py compose build ai-worker
# 首次启动指定服务及其必要依赖
python3 scripts/manage.py compose up -d ai-worker
# 后端已运行时，只更新 AI Worker
python3 scripts/manage.py compose up -d --build --no-deps ai-worker
```

更改公共令牌后需要重启控制面和两个 Worker；更改数据库结构后需要重新执行迁移。每个子目录仍可按自己的 README 单独构建镜像。

## 本地独立启动

先按项目安装依赖：四个 Python 项目在各自目录执行 `uv sync --locked`；前端执行 `npm ci`；API/UI Worker 另执行 `uv run playwright install chromium`（Linux 首次安装可使用 `--with-deps`）。Python 开发测试按项目 README 安装开发依赖。

先启动数据库（也可在统一配置中将 `local_host`、`mysql_port` 指向自备的开发数据库）：

```sh
python3 scripts/manage.py compose up -d mysql
python3 scripts/manage.py migrate
```

然后在不同终端分别执行所需服务：

```sh
python3 scripts/manage.py run zentao
python3 scripts/manage.py run control-plane
python3 scripts/manage.py run ai-worker
python3 scripts/manage.py run api-ui-worker
python3 scripts/manage.py run studio
```

前端本地开发使用 Vite 默认端口（通常 5173），`studio_port` 是 Docker 对外端口。两个 Worker 可分别启动，但轮询模式需要可用的控制面。

也可先生成配置，再进入各子项目用原命令启动：

```sh
python3 scripts/manage.py configure --mode local
```

本地模式写入各项目被忽略的运行配置和前端 `.env.local`。Docker 模式只写 `.runtime/docker/` 和 `.runtime/compose.env`，不覆盖本地模式文件。生成文件不要手工维护，下次生成会覆盖；修改统一主配置即可。单独复制某个子项目使用时，仍可从该项目的示例文件生成配置。

脚本不会修改已经设置的进程环境变量。AI Worker 原有 `TESTING_AGENT_*` 环境变量仍可覆盖 TOML；统一配置未生效时应检查终端或服务管理器中的旧变量。

## 检查

```sh
python3 -m unittest discover -s tests -v
python3 scripts/manage.py compose config --quiet
```

各子项目的完整检查见各自 README。迁移说明见 [迁移说明](monorepo-migration.md)。
