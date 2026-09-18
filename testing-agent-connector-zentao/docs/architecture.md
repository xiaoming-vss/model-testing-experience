# 架构说明

## 定位

本项目是在禅道 API 之上加一层纯后端服务适配层，目标是：

- 屏蔽禅道原始接口细节
- 对外提供统一、稳定的 HTTP API
- 收口错误码、日志和响应格式
- 对外提供项目、执行、需求、缺陷、测试单、测试用例查询，以及测试用例批量创建和同名更新接口

## 当前结构

```text
HTTP Request
  -> app/api/v1/*
  -> app/services/zentao/*
  -> app/clients/zentao/*
  -> Zentao API
  -> services 做字段归一
  -> schemas 输出统一响应
```

## 目录职责

### `app/api`

职责：

- 定义路由
- 接收参数
- 输出统一响应
- 注册全局异常处理和中间件

约束：

- 不直接写禅道请求
- 不直接堆业务逻辑

### `app/schemas`

职责：

- 定义请求/响应模型
- 定义统一 `Response` / `ErrorResponse`

说明：

- `schemas/zentao/imports.py` 放阶段一导入 DTO 与字段标准化 helper
- `schemas/response.py` 只放通用响应协议

### `app/services/zentao`

职责：

- 把禅道原始动作组织成对外服务能力
- 做必要的数据归一
- 承接资源级业务封装

例如：

- 项目列表查询
- 项目详情查询
- 执行列表与详情查询
- 测试单列表与详情查询

### `app/clients/zentao`

职责：

- 只负责和禅道通信
- 封装请求路径、参数传递和错误转换
- 通过 `token_manager.py` 统一读取调用方传入的 token

说明：

- `project_client.py`：项目接口
- `execution_client.py`：执行接口
- `testtask_client.py`：测试单接口
- `bug_client.py`：缺陷接口
- `testcase_client.py`：测试用例查询、创建与更新接口
- `base.py`：共享 HTTP 和统一鉴权请求入口
- `token_manager.py`：管理当前请求上下文里的 token 读取

### `app/core`

职责：

- `app/config.py`（位于 `app/`）：读取 `config/zentao.toml`
- `exceptions.py`：统一错误码和 `AppError`
- `logging.py`：日志配置
- `http_client.py`：公共 `httpx` 封装
- `zentao_toml.py`：禅道配置解析

## 架构风格判断

当前更适合定义为：

- 分层架构 `Layered Architecture`
- 按资源模块拆分
- 带共享基础设施的轻量服务化结构

它不是严格 MVC，也不是完整 DDD。

原因：

- 没有 View 层，不符合 MVC
- 还没有聚合根、仓储、领域对象边界，不是完整 DDD
- 当前核心诉求是稳定封装禅道并对外提供服务，这种结构更轻、更直接

## 为什么保留 Token Manager

现在的 token 不再由本项目获取，而是由外部认证服务提供。

所以当前方案是：

- 调用方在每次业务请求里传 `Authorization: Bearer <token>`
- `token_manager.py` 只负责统一读取和分发这个 token
- 各资源 client 继续通过共享鉴权请求基类复用 token 传递逻辑
- token 刷新职责留在外部认证服务，不再由本项目承担

这样可以保持客户端代码结构稳定，同时把认证边界划分得更清楚。
