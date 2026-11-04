# 需求维度的 AI 测试设计接口

需求工作台负责配置和概览。需求分析、功能、API、UI 的生成、编辑、审核及导入使用独立阶段链，详见 [generation-chain.md](generation-chain.md)。

| 接口 | 行为 |
| --- | --- |
| GET `/v1/requirements/{id}/design` | 返回配置摘要、旧运行计数及是否存在已审核的需求理解版本 |
| GET `/v1/requirements/{id}/design/{kind}/runs` | 分页读取同类历史任务的运行摘要 |
| POST `/v1/requirements/{id}/design/{kind}/configuration` | 复用或新增配置，自动填写项目、迭代、需求和名称 |
| POST `/v1/requirements/{id}/design/{kind}/run` | 返回提示，引导客户端使用独立阶段运行接口 |
| POST `/v1/requirements/{id}/generation/{kind}/stages/{stage}/run` | 校验权限和已审核上游，冻结输入并派发目标阶段 |

`kind` 为 `requirement_analysis`、`function`、`api` 或 `ui`。配置提交可带稳定 UUID `requestId`；缺省时在需求父行锁内复用默认配置，显式新增传 `newConfiguration`。API 输入须为有效 OpenAPI/Swagger 文档或 HTTP/HTTPS 文档地址，UI 源码包走统一对象存储接口。

阶段运行使用当前操作者的个人模型授权。请求中的 `requestId` 标识 Worker 派发；同一请求重试复用原派发和阶段尝试。功能阶段默认读取当前需求最新已审核的需求理解版本，也可显式选择，所选内容和版本在运行时冻结。每个阶段独立审核；是否继续派发下一阶段由审核请求决定。

配置操作在授权后按项目、迭代、需求顺序加锁，重查权限和现有配置。阶段派发在同一事务写入稳定阶段、尝试和 Worker 队列。功能用例、API 集合和 UI 套件属于独立正式资产，不随生成链历史清理而删除。

验证入口为 `test_requirement_design.py`、`test_requirement_design_api.py`、`test_requirement_design_mysql.py` 和独立阶段测试；MySQL 专项使用可丢弃测试库，验证并发配置与同一请求的阶段派发。

新建需求时，需求分析和功能测试的默认生成任务与需求在同一事务内创建；这只建立关联，不发起 AI 运行。历史需求由有写权限的成员打开工作台时调用既有幂等配置接口补齐，失败时可重试；只读访问不会写入。API 文档与 UI 源码仍由用户提供。
