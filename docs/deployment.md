# 统一配置、部署与本地开发

以下命令均在仓库根目录执行。各应用的命令和专项检查见 [文档总索引](README.md)。

## 统一配置

管理脚本要求 Python 3.11+，本地运行 AI Worker 要求 Python 3.13（uv 根据各项目的版本文件管理解释器）。

```sh
python3 scripts/manage.py init
```

编辑 `config/platform.toml`。首次初始化会生成随机数据库密码、JWT 密钥、集成密钥和 Worker 令牌，重复执行不会覆盖。该文件以及生成的运行配置均被 Git 忽略。提交示例文件 `config/platform.example.toml`，不要提交实际配置。

已有部署接入独立集成 Worker 的配置准备：

```sh
python3 scripts/manage.py upgrade-config
```

该命令只补齐专属令牌、共享运行代次和执行开关缺项，保留已有密钥、自定义配置值及配置文件权限；重复执行保持文件原样。`init` 继续不修改已有文件。配置补齐不代表拆分已经上线，`control_plane.integration_execution.enabled` 默认关闭。实施进度见[集成 Worker 实施记录](control-plane/integration-worker-implementation.md)。

`shared` 统一定义服务地址、发布端口及认证密钥；`database.url` 指定已有数据库，留空时使用下方的内置数据库字段。`control_plane`、`ai_worker`、`api_ui_worker`、`integration_worker` 区块递归覆盖各项目示例配置中的同名字段。地址、令牌、监听端口和存储路径最终由管理脚本按运行模式统一设置。

默认只允许本机访问。服务器部署时将 `shared.public_host` 改为浏览器能访问的服务器 IP/域名，将 `shared.bind_host` 改为 `0.0.0.0`。当前编排提供 HTTP；域名 HTTPS 可由部署环境的反向代理提供。S3 Endpoint 必须能被浏览器和 Worker 访问，并为前端配置 CORS。

## Docker 整体启动

当前 Compose 项目名是 `mtx`。从旧 `testing-agent` 部署升级时，先阅读 [旧数据卷兼容说明](naming.md#已有-docker-部署的数据卷)，避免创建另一套空卷。

要求 Docker Engine 和支持健康检查依赖的 Docker Compose v2+。

```sh
python3 scripts/manage.py compose up -d --build
python3 scripts/manage.py compose ps
python3 scripts/manage.py compose logs -f
```

默认前端地址：http://127.0.0.1:8081 。控制面对外 19000（容器内 9000），MySQL 映射到 13306。

内置数据库模式的启动顺序：MySQL 就绪 → migrate 执行 `alembic upgrade head` → 控制面就绪 → 前端与 Worker。数据库使用独立持久卷，业务文件使用私有 S3；AI 会话、日志及 Worker 临时产物仍使用运行目录或卷。控制面旧 storage 卷仅保留历史文件供恢复，不参与业务文件读取。第一次部署初始化空数据库，原备份目录中的数据库及运行数据不会自动导入。

AI 任务需要先配置平台中的模型服务及个人授权，并通过控制面的 [默认技能同步命令](control-plane/skills.md) 将技能源文件上传到 S3。Worker 按任务／阶段拉取当前默认技能到任务独立目录，不再按项目手工预置技能。代码部署不等于默认技能源文件及业务数据迁移。

停止服务并保留数据：

如集成 Worker 仍有未回传结果，先按 [Worker 运维说明](integration-worker/README.md#停止与结果日志)停止并导出对应副本证据；down 后重新 up 不会自动挂回旧匿名运行卷。普通 Worker 维护可使用 stop/start 保留容器和运行卷。

```sh
python3 scripts/manage.py compose down
```

已有 MySQL 卷初始化后，修改统一配置中的数据库密码不会自动更改数据库内的账号密码，需要配合数据库账号管理操作。

内置 MySQL 默认启用慢查询日志，`database.slow_query_log = true`、`database.long_query_time = 0.5` 由管理脚本生成 Compose 配置。日志写入 MySQL 数据卷中的 `/var/lib/mysql/slow-queries.log`，不进入 Git。修改后运行 `python3 scripts/manage.py configure --mode docker`，在下次重建 MySQL 服务时生效。已有外部 MySQL 不受 Compose 参数控制，需要数据库管理员配置同等选项；MySQL 8.4 可使用 `SET PERSIST slow_query_log = ON`、`SET PERSIST long_query_time = 0.5`，阈值对新连接生效，旧连接需要重连。日志轮转后使用 `FLUSH SLOW LOGS` 重新打开文件。

## 单独构建和更新

```sh
# 构建单个项目
python3 scripts/manage.py compose build ai-worker
# 首次启动指定服务及其必要依赖
python3 scripts/manage.py compose up -d ai-worker
# 后端已运行时，只更新 AI Worker
python3 scripts/manage.py compose up -d --build --no-deps ai-worker
```

更改 `shared.worker_token` 后需要重启控制面、AI Worker 和 API/UI Worker；更改 `shared.integration_worker_token` 后需要重启控制面和 integration-worker。更改数据库结构后需要重新执行迁移。每个子目录仍可按自己的 README 单独构建镜像。

独立集成 Worker 的启动、扩容、排空和结果日志说明见 [integration-worker 运维](integration-worker/README.md)。执行开关默认关闭，启动该进程不会自动切换现有项目。

## 本地独立启动

先按项目安装依赖：四个 Python 项目在各自目录执行 `uv sync --locked`；前端执行 `npm ci`；API/UI Worker 另执行 `uv run playwright install chromium`（Linux 首次安装可使用 `--with-deps`）。Python 开发测试按项目 README 安装开发依赖。

使用已有数据库时，按下一节填写 `database.url`，跳过内置 MySQL 启动。如果使用内置的空数据库，先执行：

```sh
python3 scripts/manage.py compose up -d mysql
python3 scripts/manage.py migrate
```

然后在不同终端分别执行所需服务：

```sh
python3 scripts/manage.py run control-plane
python3 scripts/manage.py run ai-worker
python3 scripts/manage.py run api-ui-worker
python3 scripts/manage.py run integration-worker
python3 scripts/manage.py run studio
```

前端本地开发使用 Vite 默认端口（通常 5173），`studio_port` 是 Docker 对外端口。三个 Worker 可分别启动，但轮询模式需要可用的控制面。

也可先生成配置，再进入各子项目用原命令启动：

```sh
python3 scripts/manage.py configure --mode local
```

本地模式写入各项目被忽略的运行配置和前端 `.env.local`。Docker 模式只写 `.runtime/docker/` 和 `.runtime/compose.env`，不覆盖本地模式文件。生成文件不要手工维护，下次生成会覆盖；修改统一主配置即可。单独复制某个子项目使用时，仍可从该项目的示例文件生成配置。

脚本不会修改已经设置的进程环境变量。AI Worker 原有 `TESTING_AGENT_*` 环境变量仍可覆盖 TOML；统一配置未生效时应检查终端或服务管理器中的旧变量。

## 连接已有 MySQL

在 `config/platform.toml` 的现有 `[database]` 区块填写 URL（不要重复添加区块）：

```toml
[database]
url = "mysql+asyncmy://用户名:密码@127.0.0.1:3306/数据库名?charset=utf8mb4"
```

非空 URL 在本地与 Docker 模式下均优先使用，此时 `database.name/user/password/root_password` 和 `shared.mysql_port` 不再用于连接。支持 `mysql+asyncmy://`，也会将 `mysql://` 自动转换。用户名、密码中的特殊字符需 URL 编码，例如 `@` 写为 `%40`、`#` 写为 `%23`、`%` 写为 `%25`。数据库地址独立于 `shared.local_host`，无需更改其他服务地址。

本地运行 `python3 scripts/manage.py run control-plane` 会自动生成并加载配置。也可以只执行 `python3 scripts/manage.py configure --mode local` 检查生成文件，然后按上一节分别启动服务。

Docker 下使用容器可访问的数据库地址；`127.0.0.1` 指向容器自身。连接宿主机 MySQL 可使用 `host.docker.internal`，编排已为控制面和迁移服务添加宿主机映射，MySQL 需允许来自容器网络的连接。远程数据库则填写对应主机地址。脚本不会自动改写 URL 的主机名。

设置 URL 后，`manage.py compose` 自动加载 `deploy/compose.external-db.yaml`（需要支持 `!reset` 的 Docker Compose）。普通 `compose up` 不启动内置 MySQL，也不自动执行数据库迁移；控制面使用已有表结构。若明确需要初始化一个空数据库，可手动运行：

```sh
# 本地
python3 scripts/manage.py migrate
# 或通过 Docker
python3 scripts/manage.py compose run --rm migrate
```

迁移基线面向空数据库；历史数据库不能直接视为兼容。将 URL 留空可恢复内置数据库模式。

## 检查

```sh
python3 -m unittest discover -s tests -v
python3 scripts/manage.py compose config --quiet
```

各子项目的完整检查见各自 README。

## 禅道连接器退出（2026-10-03）

平台已改为直接调用项目配置的禅道 MCP，默认编排不再启动 connector-zentao，管理脚本不再生成其配置或提供 run zentao。
旧 platform.toml 的 shared.zentao_port、zentao 区块可删除；未删除也不会启用连接器。已有业务数据、旧绑定和凭据不自动删除。

升级控制面和 Studio 后，通过 `python3 scripts/manage.py compose up -d --build --remove-orphans` 清理同一 Compose 项目中残留的旧连接器容器。
执行前确认使用原部署的 Compose 项目及数据卷配置；这条命令不删除数据卷。手动运行的旧连接器应在升级完成后停止。
connector-zentao 的源码、专属文档及独立启动入口已删除；平台仅保留 MCP 集成。

保留并单独运维 Zentao MCP Server 和禅道实例，不能把它们当作旧连接器停止。配置的 MCP 端点必须能被控制面所在环境访问；容器里的 127.0.0.1 指向容器自己。
用例推送的契约修正、异常结果和验收限制见 [用例 MCP 推送](control-plane/zentao-mcp-case-push.md)。

## ZenTao-MCP 手动部署模板

平台默认编排不启动 MCP。仓库的 `deploy/zentao-mcp/` 只保存 Compose、无凭据配置示例和启动入口，直接使用 `xiaoming-x/zentao-mcp:2026-10-04` 的已发布镜像。用户复制并编辑配置后，在独立部署目录执行 `docker compose pull` 和 `docker compose up -d`；不通过 `manage.py` 生成 MCP 配置，也不依赖平台 TOML。项目所有者填写各自可达的 MCP 地址，成员各自授权。配置、多容器、端口、网络与排障见 [完整指南](control-plane/zentao-mcp-deployment.md)。
