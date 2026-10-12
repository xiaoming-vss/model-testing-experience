# 需求维度的 AI 测试设计接口

旧任务与 Worker 协议保持不变。需求详情通过新的需求维度接口使用既有生成、审核、阶段推进和导入流程。

| 接口 | 行为 |
| --- | --- |
| GET `/v1/requirements/{id}/design` | 配置摘要、四类运行总数、执行中的配置 ID、是否已有可用于功能生成的增强文本 |
| GET `/v1/requirements/{id}/design/{kind}/runs` | 需求下所有同类任务的运行摘要，支持 page/pageSize/pipelineFilter |
| POST `/v1/requirements/{id}/design/{kind}/configuration` | 复用或新增配置，自动填写项目、迭代、需求和名称 |
| POST `/v1/requirements/{id}/design/{kind}/run` | 使用指定配置及本次操作人的个人模型授权发起运行 |

`kind` 为 requirement_analysis/function/api/ui。新请求拒绝未声明字段，分页上限 100，列表不返回正文和快照。非法分页/枚举沿用全站参数错误信封与 HTTP 400。跨需求配置/运行引用返回 404，项目权限按 read/write/execute 校验。

配置提交支持可选 requestId（UUID），缺省时在需求父行锁内复用默认配置；显式新增配置传 newConfiguration 和稳定 requestId。客户端重试同一请求不会创建新配置。已存在的多份历史配置均保留，不自动合并或删除。API 新输入校验 OpenAPI/Swagger 版本及 paths，兼容已有 HTTP/HTTPS 文档 URL；UI 文件上传仍走既有 S3 文件与源码包接口。

运行提交必须带 requestId、taskId、connectionId，可以设置功能检查点。requestId 对应 runId；响应丢失重试返回原运行，核对任务和发起者，不允许借同一 UUID 引用他人的运行。需求分析和功能测试在运行弹窗中选择是否启用阶段人工审核，默认开启。功能生成使用需求中已有的有效增强文本，兼容普通文本、Markdown 和结构化需求理解，不要求重新分析并导入；仅有原始附件、空白文本或损坏的结构化内容不能运行。概览保留兼容字段 `adoptedUnderstanding`，其含义调整为增强文本可用于功能生成，与运行快照使用同一解析规则；Worker 和新生成产物的契约保持不变。

配置和启动先结束只读授权准备事务，避免等待锁期间的撤权被旧会员快照掩盖。事务锁定顺序采用 project → sprint → requirement → task。首次配置发现及既有配置加载使用当前读取，防止 MySQL REPEATABLE READ 的旧快照漏掉并发创建。配置的既有 create/update 操作拥有提交；运行的既有 run 操作在准备快照后结束事务，再加锁核验权限和配置，幂等检查与运行/Worker 记录创建在同一提交内完成。运行中不能再次启动同一配置。运行列表筛选根据各任务真实最终阶段判断审核状态，需求范围查询还校验历史任务的项目和迭代关联，兼容未存迭代标识但需求关联有效的历史任务。

无需数据库迁移或 Worker 配置变更。

验证入口为 test_requirement_design.py、test_requirement_design_api.py、test_requirement_design_mysql.py，追加数据库读取、HTTP/字段/路由、架构与项目权限回归。MySQL 专项在独立、空的可丢弃测试库中验证三路配置和运行并发，以及准备阶段后的成员撤权，不使用业务数据库。
