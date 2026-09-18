# Zentao Service

> 文档统一维护于此；以下项目命令在仓库根目录的 `apps/connector-zentao/` 中执行。整套平台的配置与部署见 [统一部署指南](../deployment.md)。

`Zentao Service` 是一个基于 `FastAPI` 的后端适配服务。提供项目、执行、需求、缺陷、测试单和测试用例查询，以及测试用例批量创建和同名更新能力。

## 已提供 API

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`
- `GET /api/v1/zentao/projects`
- `GET /api/v1/zentao/projects/{project_id}`
- `GET /api/v1/zentao/projects/{project_id}/executions`
- `GET /api/v1/zentao/executions/{execution_id}`
- `GET /api/v1/zentao/executions/{execution_id}/stories`
- `GET /api/v1/zentao/executions/{execution_id}/bugs`
- `GET /api/v1/zentao/executions/{execution_id}/cases`
- `POST /api/v1/zentao/testcases`
- `GET /api/v1/zentao/executions/{execution_id}/testtasks`
- `GET /api/v1/zentao/testtasks/{testtask_id}`

业务接口都必须传 `Authorization: Bearer <token>`，并且必须在 query 中显式传 `base_url`。分页列表接口只支持 `base_url`、`page`、`page_size`；需求列表、详情与创建接口只支持 `base_url`。

`POST /api/v1/zentao/testcases` 会先检查对应 `execution` 下是否已有同名用例，命中则自动改为更新，不再重复创建。

批量创建测试用例请求示例：

```json
{
  "productID": 1,
  "project": 2,
  "execution": 3,
  "cases": [
    {
      "title": "测试压敏模块显示是否正常",
      "module": 0,
      "story": 0,
      "pri": 3,
      "precondition": "已进入压敏模块页面",
      "steps": ["步骤1", "步骤2"],
      "expects": ["期望1", "期望2"]
    }
  ]
}
```

## 配置

项目统一使用 `config/zentao.toml`。首次启动前复制示例配置并按需调整：

```bash
cp config/zentao.example.toml config/zentao.toml
```

```toml
[service]
app_name = "zentao-service"
app_env = "local"
api_v1_prefix = "/api/v1"
host = "127.0.0.1"
port = 8010
enable_docs = true
log_level = "INFO"
log_json = false

[zentao]
timeout_seconds = 15
verify_ssl = true
```

`base_url` 仅通过每次业务请求的 query 参数传入，不再从配置文件读取。配置文件保留 `timeout_seconds` 和 `verify_ssl`；如需自定义 CA，可在 `[zentao]` 下添加 `ca_file = "/path/to/ca.pem"`，该设置优先于 `verify_ssl`。项目不再保存账号密码，也不提供登录换 token 能力。

## 统一响应

成功响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

失败响应：

```json
{
  "code": 50000,
  "message": "Internal server error.",
  "data": {},
  "errors": null
}
```

## 常用命令

### Docker 部署

在项目根目录构建镜像：

```bash
docker build -t mtx/zentao:local .
```

启动容器：

```bash
docker run -d --name zentao-service \
  --restart unless-stopped \
  -p 8010:8010 \
  mtx/zentao:local
```

镜像使用 Python 3.12，按照 `uv.lock` 安装生产依赖，以非 root 用户运行。
内置配置基于示例文件，将 `app_env` 设为 `production`（关闭自动重载），
`host` 设为 `0.0.0.0`，端口为 `8010`。可访问
`http://localhost:8010/docs` 查看接口文档，或检查存活状态：

```bash
curl http://localhost:8010/api/v1/health/live
```

需要自定义配置时，先复制 `config/zentao.example.toml` 为 `config/zentao.toml`，
将 `[service]` 中的 `host` 改为 `0.0.0.0`、`app_env` 改为 `production`，再挂载启动：

```bash
docker run -d --name zentao-service \
  --restart unless-stopped \
  -p 8010:8010 \
  --mount type=bind,src="$(pwd)/config/zentao.toml",dst=/app/config/zentao.toml,readonly \
  mtx/zentao:local
```

以上两种启动方式任选其一。配置文件需允许容器用户（UID `10001`）读取。
如果修改配置中的端口，需同步调整 `-p` 的容器端口；例如容器端口为 `8020` 时，
使用 `-p 8010:8020`。本地配置文件不会打包进镜像。
请求中的禅道 `base_url` 必须是容器可访问的地址；容器内 `127.0.0.1` 指向容器自身。
如使用自定义 CA 证书，也需将证书挂载到容器，并将 `ca_file` 设置为容器内路径。

### 本地开发

安装依赖：

```bash
uv sync
```

启动服务：

```bash
uv run python main.py
```

运行测试（测试使用仓库内的示例配置，不依赖本地 `config/zentao.toml`）：

```bash
uv run pytest
```

运行检查：

```bash
uv run ruff check .
uv run ruff format --check .
```

## 文档目录

- [架构说明](architecture.md)
- [开发约定](development.md)
- [错误码规范](error-codes.md)
