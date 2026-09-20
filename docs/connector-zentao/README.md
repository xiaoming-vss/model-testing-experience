# 禅道适配服务（connector-zentao）

屏蔽禅道原始接口，向控制面提供统一的禅道数据访问：项目、执行、需求、缺陷、测试单与用例的查询，以及用例的批量创建与同名更新。

分层架构与请求约定见 [architecture](architecture.md)，错误码契约见 [错误码规范](error-codes.md)。

## 运行时与依赖

- Python 3.12（`requires-python`，Dockerfile 使用 `python:3.12-slim-bookworm`）；这是五个应用中唯一没有 `.python-version` 文件的项目
- 包管理使用 uv（`uv.lock`），构建后端 hatchling，打包 `app` 包
- 依赖：`fastapi`、`httpx`、`uvicorn`
- 开发依赖在 `[dependency-groups] dev`，uv 默认装入

## 源码结构

| 路径 | 作用 |
| --- | --- |
| `main.py` | 启动入口，调用 uvicorn 加载 `app.main:app` |
| `app/main.py` | 应用装配（`create_app()` 与模块级 `app`） |
| `app/config.py` | 配置加载 |
| `app/dependencies.py` | 从请求中提取禅道凭据 |
| `app/api/v1/` | 路由：`health.py` 与 `zentao/` 下的项目、执行、缺陷、测试单、用例 |
| `app/services/zentao/` | 业务服务层 |
| `app/clients/zentao/` | 禅道 HTTP 客户端层 |
| `app/core/` | 异常、HTTP 客户端、日志、禅道地址规范化 |
| `app/schemas/` | 响应模型与禅道请求/响应模型 |

注意该项目**没有** `[project.scripts]` 段，入口是仓库根级的 `main.py`，启动命令与其他四个服务不同。

## 配置

读取 `config/zentao.toml`（基于应用根目录计算）。**没有环境变量覆盖机制**；文件缺失时启动报错并提示从 `config/zentao.example.toml` 创建。

```toml
[service]     # app_name、app_env、api_v1_prefix、host、port、
              # enable_docs、log_level、log_json
[zentao]      # timeout_seconds、verify_ssl、ca_file
```

`[zentao]` 段只提供超时与 SSL 参数，**禅道地址不从配置文件读取**，由调用方每次请求传入。代码内兜底端口是 8000，示例配置与 Dockerfile 均为 8010。

## 命令

在 `apps/connector-zentao/` 下执行：

```sh
uv sync --locked             # 安装依赖
uv run python main.py        # 启动
uv run pytest                # 测试（62 项）
uv run ruff check .          # Lint
```

也可在仓库根目录执行 `python3 scripts/manage.py run zentao`。

## 接口

默认监听 8010：

- `GET /api/v1/health/live`、`GET /api/v1/health/ready`
- `/api/v1/zentao/` 下 10 个端点：项目列表与详情、项目下执行、执行详情、执行下需求/缺陷/测试单/用例、测试单详情、批量创建用例

`/docs` 与 `/redoc` 由 `enable_docs` 控制。
