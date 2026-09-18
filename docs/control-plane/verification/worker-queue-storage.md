# Worker 队列存储与验证

队列只存调度、执行身份、状态、租约和时间；用例、套件、集合、生成任务等接口字段从实际执行记录推导。AI 模型连接保存在执行输入快照中，优化与重试继续使用对应快照。

新库初始化见 [ADR-0006](../adr/0006-fresh-database-baseline.md)。开发期间的队列字段归档表与旧库回填逻辑已移除。

验证入口：`tests/test_worker_queue_storage.py`，覆盖重新加载、租约超时、阶段重试、模型连接保留及监控任务退出。数据库初始化与约束使用 `tests/test_mysql_initialization.py` 在独立空库验证。
