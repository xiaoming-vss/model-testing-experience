# 控制面（control-plane）

平台唯一的后端服务。组织测试资产、AI 生成任务、人工审核与导入、执行调度、权限、外部集成凭据与报告，并向浏览器提供 `/v1/*`、向 Worker 提供 `/internal/*`。

这是 Go 控制面的 Python 重写版本，保留原 `/v1` 与 `/internal/*` 契约。领域术语见 [CONTEXT](CONTEXT.md)。

## 运行时与依赖

- Python 3.12（`.python-version`），包管理使用 uv（`uv.lock`）
- FastAPI + uvicorn、SQLAlchemy 2 async + Alembic、MySQL（`asyncmy`）、Pydantic v2
- 认证与授权：PyJWT、bcrypt、PyCasbin；报告输出使用 reportlab
- 开发依赖在 `[project.optional-dependencies] dev`，需要 `--extra dev` 才会装入

## 源码结构

`apps/control-plane/src/testing_agent/`：

| 路径 | 作用 |
| --- | --- |
| `main.py` | 启动入口，调用 uvicorn 加载 `app.py` 的工厂函数 |
| `app.py` | 应用装配、异常处理、OpenAPI 契约改写 |
| `routers/` | 27 个路由模块，全部由 `app.py` 挂载 |
| `handlers/` | 薄 HTTP 处理层，被 router 调用 |
| `services/`、`services/ai_execution/` | 业务服务与 AI 任务编排 |
| `repositories/` | 数据访问 |
| `models/`、`schemas/` | ORM 模型与请求/响应模型 |
| `core/` | `config.py`、`security.py`、`enums.py`、`errors.py`、`sid.py` |
| `db/`、`domain/` | 会话与基础层、领域值对象 |

调用层次为 router → handler → service → repository → model。注意 `api/` 目录下只有依赖注入与鉴权校验（`deps.py`），业务路由不在此处。

## 配置

启动时按 `--config/-c` 参数、`APP_CONF` 环境变量、`config/local.toml` 的顺序确定配置文件路径。本地独立启动由 `scripts/manage.py` 生成 `config/local.toml` 并注入 `APP_CONF`；容器内为 `/app/config/local.toml`。

顶层配置段：

```toml
env = "local"                     # local 时开启 uvicorn reload
[http]                            # host、port
[security.jwt]                    # key、expire_hours
[security.integration]            # key，用于集成凭据加解密
[security.worker]                 # key，Worker 调用内部接口的令牌
[data.db.user]                    # driver、dsn
[storage]                         # uploads_dir
[integrations.zentao_service]     # base_url
[code_overview]                   # cache_ttl_seconds
```

## 命令

在 `apps/control-plane/` 下执行：

```sh
uv sync --locked --extra dev                      # 安装依赖（含开发依赖）
uv run mtx-control-plane                          # 启动
uv run --extra dev pytest                         # 测试
uv run --extra dev ruff check .                   # Lint
uv run --extra dev mypy                           # 类型检查
uv run --extra dev alembic upgrade head           # 数据库迁移
```

也可在仓库根目录用 `python3 scripts/manage.py run control-plane` 和 `python3 scripts/manage.py migrate`，由统一配置生成 `config/local.toml`。

`sql/` 存放一次性的数据订正脚本，需人工对着目标库执行，默认干跑、执行前自动备份受影响行。已有的脚本见下表。

| 脚本 | 用途 |
| --- | --- |
| `backfill_function_case_ids.sql` | 给历史功能用例候选结果补 `case_id`（审核页编号与导入沿用的编号） |

## 对外接口

默认监听 9000（Dockerfile `EXPOSE 9000`）。注意代码内兜底常量是 8000，与示例配置和镜像不一致。

- `GET /v1/health`：健康检查
- `/v1/*` 业务接口：24 个路由模块挂在 `/v1` 前缀下，覆盖登录注册、项目与成员、迭代、需求、功能/API/UI 测试资产与运行、各类 AI 任务、禅道与 GitLab 与 LLM 集成、共享服务、资源绑定与项目技能
- `/internal/ai-worker/*`、`/internal/ui-worker/*`、`/internal/api-worker/*`：3 个 Worker 面路由模块
- `GET /swagger/index.html` 返回 `{"url": "/docs"}`，兼容原 Go 契约

## 鉴权

- 浏览器请求使用 `Authorization: Bearer <JWT>`，HS256，载荷键为 `userId`
- Worker 请求使用 `X-Worker-Token` 头，值等于 `security.worker.key`

## 外部调用

- 禅道：经连接服务转发，地址取 `integrations.zentao_service.base_url`；凭据由操作人透传
- GitLab：直连 `/api/v4/*`，使用操作人的个人访问令牌
- LLM：按任务向 AI Worker 下发 `/internal/ai-worker/tasks/{id}/llm-credentials`

## 测试

`uv run --extra dev pytest`，当前收集 737 项（702 通过、4 失败、31 跳过）。4 项失败集中在 `tests/test_project_membership_api.py::test_function_stage_reexecution_uses_current_actor` 的参数化用例：测试直接生成功能用例，而当前业务规则要求先完成需求分析并导入增强文本，因而返回 HTTP 400。这是测试未跟上业务规则，尚未修复。
