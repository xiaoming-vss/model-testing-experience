# 验证命令矩阵

- 状态：现行
- 负责人：platform maintainers
- 最近复核：2026-11-20
- 复核周期：每季度
- 适用范围：全仓库检查、测试、构建与部署校验命令
- 变更/废弃：按[规范变更检查清单](agents/domain.md#规范变更检查清单)执行；影响跨项目契约时先记录 ADR 并通知消费方。

本文件是仓库检查、测试和构建命令的唯一事实来源。项目 README、开发规则和根 `AGENTS.md` 只说明何时执行哪些检查，不再复制完整命令列表。

## 使用约定

- 除非表格注明，命令均在仓库根目录执行；工作目录列写 `apps/<project>` 时，先进入该目录。
- Python 项目使用 uv。`uv run` 一律带 `--locked`，确保运行环境与 `uv.lock` 一致；安装使用 `uv sync --locked`。确需在锁文件之外临时安装工具时，必须在本文件登记原因和替代命令。
- 开发依赖按项目声明的依赖组安装：control-plane、api-ui-worker、integration-worker、perf-worker 使用 `--extra dev`，ai-worker 使用 `--group dev`。
- 默认命令不依赖真实外部服务。需要真实 MySQL、S3、禅道/GitLab、浏览器、LLM、k6 或 Prometheus 的验收单列在“外部验收”一节，不能由模拟测试代替。
- CI 由外部流水线负责；流水线应直接调用本文件的命令，不复制命令定义。
- 交付说明必须记录实际执行的命令、结果、跳过项和未验证范围。

## 根目录与部署编排

工作目录为仓库根目录。`scripts/manage.py` 要求 Python 3.11+。

| 用途 | 命令 | 前置条件 |
| --- | --- | --- |
| 初始化本地配置 | `python3 scripts/manage.py init` | 首次部署；生成被忽略的 `config/platform.toml`，不覆盖已有文件 |
| 补齐已有配置 | `python3 scripts/manage.py upgrade-config` | 已有 `config/platform.toml`；只补缺项，不轮换密钥 |
| 生成本地运行配置 | `python3 scripts/manage.py configure --mode local` | 已执行 `init`；写入各项目被忽略的运行配置和 studio `.env.local` |
| 生成 Docker 配置 | `python3 scripts/manage.py configure --mode docker` | 已执行 `init`；写入 `.runtime/docker/` 和 `.runtime/compose.env` |
| 根编排测试 | `python3 -m unittest discover -s tests -v` | Python 3.11+；需要容器的用例在缺少环境时显式跳过 |
| Compose 配置校验 | `python3 scripts/manage.py compose config --quiet` | 已执行 `init`；Docker Engine 与 Compose v2+ |
| 六镜像构建验证 | `scripts/build_images.sh [app ...]` | Docker BuildKit、uv、npm 和可访问的镜像仓库；先校验锁文件再构建 |
| 本地启动单个服务 | `python3 scripts/manage.py run <control-plane\|ai-worker\|api-ui-worker\|integration-worker\|perf-worker\|studio>` | 已安装对应项目依赖 |
| 数据库迁移 | `python3 scripts/manage.py migrate` | 数据库可达；迁移基线只支持空库初始化 |
| K8s chart 静态检查 | `for chart in deploy/helm/charts/*; do helm lint "$chart"; done` | 已安装 Helm；K8s 不是本地默认部署方式 |
| Helm chart 模板检查 | `python3 -m unittest tests.test_helm_charts -v` | 已安装 Helm；复制自检不依赖 Helm，渲染用例在未安装时跳过 |
| K8s values 模板一致性检查 | `python3 scripts/check_k8s_config.py` | Python 3.11+；对比 `config/platform.example.toml` 与 chart 默认 values，不访问集群 |
| K8s values 部署一致性检查 | `python3 scripts/check_k8s_config.py --platform-config config/platform.toml --values-dir .runtime/k8s` | 已执行 `init` 并填写实际 values；strict，关键字段缺失或漂移时非零 |
| 文档一致性检查 | `python3 scripts/check_docs.py` | 默认不访问外部网络；`--check-urls` 可选检查外部链接 |
| 文档检查脚本测试 | `python3 -m unittest tests.test_documents -v` | — |
| 契约副本一致性检查 | `python3 scripts/sync_contract_copies.py --check` | 逐字节比较规范源与各项目副本；漂移时非零 |
| 集成 Worker 容器隔离验收（opt-in） | `MTX_TEST_INTEGRATION_WORKER_RUNTIME=1 python3 -m unittest tests.test_integration_worker_runtime -v` | Docker Engine；先构建 `mtx/integration-worker:split-validation` 或用 `MTX_TEST_INTEGRATION_WORKER_IMAGE` 指定镜像；默认跳过 |
| 禅道 MCP 容器验收（opt-in） | `MTX_TEST_ZENTAO_MCP_RUNTIME=1 python3 -m unittest tests.test_zentao_mcp_runtime -v` | Docker Engine；创建一次性 MCP 容器，默认跳过 |
| 禅道 MCP 附件验收（opt-in） | `MTX_TEST_ZENTAO_MCP_ATTACHMENTS=1 python3 -m unittest tests.test_zentao_mcp_attachment_runtime -v` | Docker Engine 与附件容器依赖；默认跳过 |
| 禅道 MCP 选项验收（opt-in） | `MTX_TEST_ZENTAO_MCP_BUG_OPTIONS=1 python3 -m unittest tests.test_zentao_mcp_bug_options_runtime -v` | Docker Engine；创建一次性 MCP 容器，默认跳过 |

根编排变更至少执行“根编排测试”和“Compose 配置校验”。`init` 与 `configure` 的具体配置项见[统一配置、部署与本地开发](deployment.md)。

### 六镜像构建验证

外部 CI 调用 `scripts/build_images.sh`。不带参数时先校验五个 Python 项目的 `uv.lock` 和两个 `package-lock.json`，再按各应用目录构建六个镜像；也可以只传应用名：

```bash
scripts/build_images.sh
scripts/build_images.sh control-plane studio
```

脚本只封装锁文件检查和构建命令，不推送镜像，也不替代外部 CI。前置条件为 Docker Engine、BuildKit、`uv`、`npm` 和可访问镜像仓库。`studio` 默认不设置 `VITE_API_BASE_URL`，由 Nginx 同源代理；需要绝对 API 地址时设置同名环境变量，脚本会转成 `--build-arg`。

## control-plane

工作目录：`apps/control-plane`。Python 3.12；依赖组 `dev`。

| 用途 | 命令 | 前置条件 |
| --- | --- | --- |
| 安装依赖 | `uv sync --locked --extra dev` | 锁文件未变更 |
| 静态检查 + 全量测试 | `uv run --locked --extra dev python scripts/check.py` | 默认使用 SQLite；真实 MySQL/存储用例按环境变量启用后自动退回单进程 |
| 仅静态检查 | `uv run --locked --extra dev python scripts/check.py --static-only` | — |
| 全量测试（串行） | `uv run --locked --extra dev pytest -q` | 全量约 28 分钟；本仓库约定不与其它 pytest 并发执行 |
| 定向测试 | `uv run --locked --extra dev pytest tests/<相关测试文件>.py -q` | 按[控制面开发规则](control-plane/development-rules.md#验证与交付)选择入口 |
| 候选处置回归 | `uv run --locked --extra dev pytest tests/test_generation_candidate_api.py tests/test_hard_deletion.py -q` | 覆盖拒绝，以及删除未拒绝和已拒绝的候选 |
| 元素库回归 | `uv run --locked --extra dev pytest tests/test_ui_element_library.py -q` | 校验项目权限、分组、定位模板与版本冲突 |
| 默认技能自带测试 | `for skill in default-skills/*/; do (cd "$skill" && python3 -m unittest discover -s tests -t tests); done` | 在 `apps/control-plane/` 下执行；每个技能独立进程，避免同名脚本模块冲突 |
| Ruff 检查 | `uv run --locked --extra dev ruff check <修改的源码及测试路径>` | — |
| Ruff 格式检查 | `uv run --locked --extra dev ruff format --check <修改的源码及测试路径>` | — |
| mypy | `uv run --locked --extra dev mypy --python-version 3.12 --check-untyped-defs <修改的业务模块路径>` | — |
| 数据库迁移 | `uv run --locked --extra dev alembic upgrade head` | 数据库可达；空库或只含可丢弃测试表 |

真实 MySQL、对象存储和并发锁行为需要单独验收：

- `CONTROL_PLANE_TEST_DATABASE_URL`：指向可丢弃的 MySQL 测试库后运行对应专项。库名必须以 `_test` 结尾且为空；账号还需要创建数据库的权限，候选切换专项会另建一个临时库。
- `CONTROL_PLANE_STORAGE_LIVE`：启用真实对象存储验收后运行对应专项。
- 这两类用例共享一次性数据库或存储，`apps/control-plane/scripts/check.py` 会自动退回单进程。

## ai-worker

工作目录：`apps/ai-worker`。Python 3.13；依赖组 `dev`（仅 Ruff）；测试框架为 unittest。

| 用途 | 命令 | 前置条件 |
| --- | --- | --- |
| 安装 Python 依赖 | `uv sync --locked --group dev` | 锁文件未变更 |
| 安装 Pi 运行时 | `npm ci` | 使用 Pi 后端时需要固定版本 CLI |
| 测试 | `uv run --locked --group dev python -m unittest discover -s tests -v` | 部分用例按环境跳过 |
| Ruff 检查 | `uv run --locked --group dev ruff check .` | — |
| Ruff 格式检查 | `uv run --locked --group dev ruff format --check <修改的源码及测试路径>` | — |

本项目未配置 mypy；公共接口类型按[通用后端规则](agents/backend-development.md)通过审查和契约测试验证。模拟模型回归不代表真实 LLM、GitLab 或 S3 已完成验收。

## api-ui-worker

工作目录：`apps/api-ui-worker`。Python 3.12；依赖组 `dev`。

| 用途 | 命令 | 前置条件 |
| --- | --- | --- |
| 安装依赖 | `uv sync --locked --extra dev` | 锁文件未变更 |
| 安装浏览器 | `uv run --locked playwright install chromium` | Linux 首次安装可加 `--with-deps` |
| 测试 | `uv run --locked --extra dev python -m pytest -q` | 默认使用模拟执行器 |
| Ruff 检查 | `uv run --locked --extra dev ruff check <修改的源码及测试路径>` | — |
| Ruff 格式检查 | `uv run --locked --extra dev ruff format --check <修改的源码及测试路径>` | — |
| mypy | `uv run --locked --extra dev mypy --python-version 3.12 --check-untyped-defs <修改的业务模块路径>` | — |

真实浏览器行为和实际 S3 上传需要在项目 Playwright 环境及真实存储上另行验收；模拟定位器或模拟上传不能作为完整端到端验收。

## integration-worker

工作目录：`apps/integration-worker`。Python 3.12；依赖组 `dev`。

| 用途 | 命令 | 前置条件 |
| --- | --- | --- |
| 安装依赖 | `uv sync --locked --extra dev` | 锁文件未变更 |
| 测试 | `uv run --locked --extra dev python -m pytest -q` | — |
| Ruff 检查 | `uv run --locked --extra dev ruff check .` | — |
| Ruff 格式检查 | `uv run --locked --extra dev ruff format --check <修改的源码及测试路径>` | — |
| mypy | `uv run --locked --extra dev mypy` | 使用项目 `pyproject.toml` 的 `src` 范围配置 |
| 独立容器运行验收 | `docker build -t mtx/integration-worker:split-validation apps/integration-worker`，然后 `MTX_TEST_INTEGRATION_WORKER_RUNTIME=1 python3 -m unittest discover -s tests -p test_integration_worker_runtime.py -v` | 在仓库根目录执行；需要 Docker |
| 180 秒传输边界验收 | `MTX_INTEGRATION_LONG_UPLOAD=1 uv run --locked --extra dev python -m pytest tests/integration/test_long_upload.py -q` | 在本项目目录执行；需要控制面开发依赖；默认跳过 |

真实 MySQL 并发、真实禅道和真实 S3 验收另行执行，且不能把夹具通过当作真实写入或恢复证据。

## perf-worker

工作目录：`apps/perf-worker`。Python 3.12；依赖组 `dev`。

| 用途 | 命令 | 前置条件 |
| --- | --- | --- |
| 安装依赖 | `uv sync --locked --extra dev` | 锁文件未变更 |
| 测试 | `uv run --locked --extra dev python -m pytest -q` | 没有 `k6` 时真实模板链路用例跳过 |
| Ruff 检查 | `uv run --locked --extra dev ruff check .` | — |
| Ruff 格式检查 | `uv run --locked --extra dev ruff format --check .` | — |
| mypy | `uv run --locked --extra dev mypy` | 使用项目 `pyproject.toml` 的 `src` 范围配置 |

Remote Write 验收需要 Prometheus 开启接收能力（例如 `--web.enable-remote-write-receiver`），并确认 `run_id` 指标可查。假 k6 测试不能作为真实压测验收。

## studio

工作目录：`apps/studio`。Node 22.23.1（`.nvmrc`），使用 npm 与 `package-lock.json`。

| 用途 | 命令 | 前置条件 |
| --- | --- | --- |
| 安装依赖 | `npm ci` | Node 版本符合 `.nvmrc` |
| 类型检查 | `npm run type-check` | — |
| Lint | `npm run lint` | — |
| 测试 | `npm test` | jsdom 环境；重型页面可加 `--maxWorkers=1` 复跑 |
| 主题与色值检查 | `npm run check:theme` | — |
| CSS 预算检查 | `npm run check:css` | — |
| CSS 结构检查 | `npm run check:css:structure` | — |
| CSS 全部检查 | `npm run check:css:all` | 等价于 `check:css` + `check:css:structure` |
| feature 边界检查 | `npm run check:boundaries` | — |
| 首屏 bundle 预算 | `npm run check:bundle` | 先执行 `npm run build`；HTML 初始资源及登录、默认项目页预算见[结构规范](studio/STRUCTURE.md#已知验证盲区) |
| 体积基线收缩检查 | `npm run check:size` | 基线只能下降；文件缩短后需同步收紧 `apps/studio/scripts/size-budget.json` |
| Tailwind className 检查 | `npm run check:tailwind` | `!` 零容忍；重复 utility 串按 `apps/studio/scripts/tailwind-class-budget.json` ratchet |
| 构建 | `npm run build` | — |
| 完整静态验证 | `npm run verify` | 包含 type-check、lint、体积基线收缩、主题/CSS/边界/Tailwind 检查、build、首屏 bundle 预算和 `npm test` |

前端交付前执行一次 `npm run verify`，其中已包含 `npm test`。真实浏览器布局、窄屏、浅色/深色和列表表面观感仍需按[界面规范](studio/UI-GUIDELINES.md)人工核对；jsdom 不能替代真实布局验收。

## 按变更选择入口

| 变更范围 | 最小入口 |
| --- | --- |
| 根编排、Compose、部署脚本 | 根编排测试 + Compose 配置校验 |
| Helm chart | 根编排测试 + `helm lint` + `tests.test_helm_charts` |
| control-plane | `apps/control-plane/scripts/check.py`，再按[控制面开发规则](control-plane/development-rules.md#验证与交付)追加专项 |
| ai-worker | unittest 全量，再按[AI Worker 开发规则](ai-worker/development-rules.md#验证入口)追加专项 |
| api-ui-worker | pytest 全量，再按[API/UI Worker 开发规则](api-ui-worker/development-rules.md#验证入口)追加专项 |
| integration-worker | pytest 全量，再按[集成 Worker 开发规则](integration-worker/development-rules.md#验证入口)追加专项 |
| perf-worker | pytest 全量，再按[性能 Worker 开发规则](perf-worker/development-rules.md#验证入口)追加专项 |
| studio | `npm run verify`（含 `npm test`），再按改动范围执行对应页面/样式检查 |
| 纯文档 | 运行 `python3 scripts/check_docs.py`；涉及新增文档时再运行 `python3 -m unittest tests.test_documents -v` |

共享基础层、跨项目协议或权限/领取/回传/停止语义变更时扩大回归范围。实际执行少于本表要求时，必须在交付说明中写明原因和未验证范围。

## 本地工作区清理

以下命令只删除本地生成物或可重新获取的依赖，不改变版本库。执行前确认没有需要保留的调试结果；不要删除正在使用的数据库卷或未归档的恢复证据。

| 目标 | 命令 | 说明 |
| --- | --- | --- |
| `.scratch` 临时副本 | 按目录确认后 `rm -rf .scratch/<临时目录>` | 先按[`.scratch` 生命周期](agents/issue-tracker.md#scratch-生命周期与长期记录)把规格与验收证据提升到 `docs/<project>/records/`；未提升的本地工件不作为长期证据 |
| Studio 依赖 | `rm -rf apps/studio/node_modules` | 用 `npm ci` 重新安装 |
| API/UI 运行产物 | `rm -rf apps/api-ui-worker/artifacts` | 先确认没有待排查的截图或 Trace |
| Worker 运行状态 | `rm -rf apps/*/runtime` | 删除健康文件、证据日志和运行工作区；需要重新启动或恢复 |
| 本地生成配置 | `rm -rf .runtime` 及 `python3 scripts/manage.py configure` 生成的文件 | 重新执行 `init`/`upgrade-config` 和 `configure` 生成 |
| Python/Node 缓存 | `find . -name __pycache__ -prune -exec rm -rf {} +` 等 | 缓存可重新生成；不要用 `git clean` 代替逐项确认 |

`node_modules`、`runtime`、`artifacts`、日志和数据库文件不应提交；根 `.gitignore` 与应用级规则共同覆盖这些路径。

## 外部验收

以下验收不属于本地默认命令，发布前按对应文档在真实环境执行：

| 外部系统 | 说明 |
| --- | --- |
| MySQL | 字符集、排序规则、注释、默认值和并发锁行为；control-plane 迁移与并发专项 |
| S3 / 对象存储 | 文件上传、下载授权、签名 URL 和真实存储行为 |
| 禅道 / GitLab | 真实 MCP 写入、一次执行、附件归属和恢复证据 |
| Playwright 浏览器 | 真实页面定位、截图、Trace 和停止行为 |
| LLM 服务 | 真实模型调用、超时、截断和执行底座行为 |
| k6 / Prometheus | 真实压测、Remote Write 和 `run_id` 指标可查 |

每项验收必须记录使用的环境、命令、结果和未覆盖范围；模拟测试、夹具和跳过项不能写成真实验收通过。
