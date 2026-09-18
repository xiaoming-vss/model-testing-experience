# 开发约定

## 环境

- Python `3.12`
- 依赖管理：`uv`
- Web 框架：`FastAPI`

## 本地命令

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

## 代码组织约定

- `app/api/` 只处理 HTTP 协议层
- `app/schemas/` 只放请求/响应模型
- `app/services/` 只做业务编排
- `app/clients/` 只做上游调用
- `app/core/` 放配置、日志、异常、HTTP 基础设施

## 新增一个禅道接口的标准步骤

1. 在 `app/schemas/zentao/` 定义请求和响应模型
2. 在 `app/clients/zentao/` 增加禅道原始请求
3. 如依赖 token，优先复用 `token_manager.py` 里的请求头 token 读取逻辑
4. 在 `app/services/zentao/` 增加业务方法
5. 在 `app/api/v1/zentao/` 增加对外路由
6. 在 `tests/` 补充测试

## 响应与异常约定

- 成功响应统一走 `app/schemas/response.py`
- 异常统一走 `app/api/exception_handlers.py`
- 业务异常统一抛 `app/core/exceptions.py` 里的 `AppError`

## 错误码约定

- `0`：成功
- `42xxx`：参数错误
- `50xxx`：系统错误
- `51xxx`：禅道集成错误

详细定义见 [error-codes.md](error-codes.md)。

## 配置约定

统一使用 `config/zentao.toml`，首次启动前创建本地配置：

```bash
cp config/zentao.example.toml config/zentao.toml
```

配置内容：

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

建议：

- 配置文件只保留超时和 TLS 相关参数；`base_url` 必须通过每次业务请求的 query 参数传入
- 如需自定义 CA，在 `[zentao]` 下添加 `ca_file = "/path/to/ca.pem"`，该设置优先于 `verify_ssl`
- 调用方需要在每次业务请求里传 `Authorization: Bearer <token>`
- 非必要不要关闭 `verify_ssl`

## 测试建议

- `tests/api/`：接口契约、异常和统一响应测试
- `tests/services/`：字段归一和聚合逻辑测试
- `tests/clients/`：token 透传、上游失败和请求构造测试
