# Model Testing Experience（MTX）命名与兼容

平台全称为 **Model Testing Experience**，简称 **MTX**。仓库目录为 `model-testing-experience`，应用目录继续使用职责名称。

| 对象 | 当前名称 |
| --- | --- |
| 前端 npm 包 | `@mtx/studio` |
| 控制面 Python 发行包与启动命令 | `mtx-control-plane` |
| AI Worker Python 发行包与启动命令 | `mtx-ai-worker` |
| API/UI Worker Python 发行包与启动命令 | `mtx-api-ui-worker` |
| 禅道 Python 发行包 | `mtx-connector-zentao`（启动仍使用 `uv run python main.py`） |
| Compose 项目 | `mtx` |
| Docker 镜像 | `mtx/studio:local`、`mtx/control-plane:local`、`mtx/ai-worker:local`、`mtx/api-ui-worker:local`、`mtx/zentao:local` |
| AI 示例命令 | `mtx-ai-demo`、`mtx-ai-chain-demo` |

## 保持兼容的标识

- `testing_agent`、`testing_agent_ai_worker`、`test_worker` 和禅道的 `app` 是 Python 内部模块名，保持不变。
- 原 `testing-agent-control-plane`、`testing-agent-ai-worker`、`testing-agent-api-ui-worker` 及 AI 示例命令作为别名继续安装。统一脚本和 Docker 使用新命令。
- `TESTING_AGENT_*`、`APP_CONF` 等环境变量继续有效。
- 数据库名、数据库账号、平台认证密钥和现有运行配置不因品牌改名而重置。
- 浏览器存储键 `testpilot_access_token`、`testpilot_theme_mode` 保留，避免改名导致已登录用户退出或主题偏好丢失。
- 历史迁移清单、历史路径、验证记录和稳定 Worker ID 中可能保留旧名称，它们不是当前页面品牌。

## 已有 Docker 部署的数据卷

新部署使用 `mtx_*` 数据卷。已有旧 Compose 项目默认使用 `testing-agent_*` 卷，直接用新项目名启动会创建另一套空卷。升级已有部署时，在新仓库根目录先停止旧项目（不要加 `--volumes` 或 `-v`）：

```sh
python3 scripts/manage.py compose -p testing-agent down
```

再通过旧数据卷覆盖文件启动：

```sh
python3 scripts/manage.py compose -f deploy/compose.legacy-data.yaml up -d --build
```

覆盖文件将五个持久卷标为 external，显式引用旧卷；缺少旧卷时会报错，不会悄悄创建空数据。原统一配置中的数据库名、用户名和密码必须保留。若旧部署曾用自定义 `-p` 项目名，应先把覆盖文件中的实际卷名调整为旧部署的名字。

之后管理该部署的 `up`、`down` 等命令也要带同一个覆盖文件。若是全新部署，不要使用这个覆盖文件，直接遵循 [部署指南](deployment.md)。

本次本机改名检查没有发现运行中的旧平台容器或旧平台卷；未对任何已有数据库或 Docker 卷执行迁移、改名或删除。
