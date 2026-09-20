# 架构说明

## 目标

禅道原始接口的字段、认证方式和错误形态都与控制面的期望不同。本服务把它们收敛成一套稳定的内部契约，让控制面只面对一种数据形态；禅道版本差异和地址差异都收敛在这一层。

## 分层

```text
app/api/v1/zentao/*     路由与请求校验
        ↓
app/services/zentao/*   业务服务
        ↓
app/clients/zentao/*    禅道 HTTP 客户端
        ↓
        禅道实例
```

- **路由层**：定义端点、校验查询参数、把请求级凭据交给下层。不含业务判断。
- **服务层**：组织调用、把禅道响应映射为对外模型、决定跨模块行为（例如用例批量创建时的同名更新）。
- **客户端层**：只负责与禅道通信，处理地址规范化、认证头、超时与 SSL 设置，并把上游失败转成统一的内部异常。

`app/schemas/` 同时承载对外响应模型（`response.py`、`health.py`）和禅道请求/响应模型（`zentao/`），两者不混用。

## 请求级凭据

这是本服务最重要的设计约束：**服务本身不保存也不校验任何身份**。

- 调用方每次请求通过 `Authorization: Bearer <token>` 传入禅道令牌，通过 `base_url` 查询参数传入禅道实例地址。
- 请求体校验使用 `extra="forbid"`，多传字段会直接失败，避免调用方误以为某个参数生效了。
- 列表端点另有 `page`（默认 1，最小 1）与 `page_size`（默认 100，范围 1–1000）。
- 服务不校验调用方身份（没有 Worker 令牌或集成密钥），凭据完全由调用方透传，可访问范围等同于该令牌在禅道中的权限。

因此控制面侧的权限边界由它自己保证：按项目绑定与操作人个人授权决定使用哪个令牌，本服务只做转发。`app/clients/zentao/token_manager.py` 只读取和分发令牌，不做缓存或续期。

## 地址规范化

`app/core/zentao_toml.py` 把调用方传入的 `base_url` 规范化为出站基地址：

- 基础路径不含 `/api.php` 时，追加 `/api.php/v2`
- 已以 `/api.php` 结尾时，追加 `/v2`
- 已包含 `/api.php/v2` 时原样使用

出站认证使用 `token: <token>` 请求头，而不是 `Authorization`。这是禅道侧的约定，也是本层最容易出错的地方。

出站 HTTP 客户端设置 `trust_env=False`（不读取代理环境变量）、`follow_redirects=True`，TLS 校验取 `ca_file`（若配置）否则取 `verify_ssl`。

## 出站端点

`/projects`、`/projects/{id}`、`/projects/{id}/executions`、`/executions/{id}`、`/executions/{id}/stories`、`/executions/{id}/bugs`、`/executions/{id}/testtasks`、`/testtasks/{id}`、`/testcases`、`/executions/{id}/testcases`、`/testcases/{id}`。

## 错误契约

统一的响应封装与错误码让调用方能按码分支，而不依赖错误文案。编号规则与当前已使用的错误码见 [错误码规范](error-codes.md)。上游返回内容不合法时归为禅道集成错误，而不是系统错误，便于区分「禅道变了」与「本服务坏了」。
