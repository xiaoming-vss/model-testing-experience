# 命名对齐与代码工程化收敛

## 背景

第二轮工程化审查(迁移 `20260831_0006` + 代码重构)解决两类问题:

1. **命名遗留**:`api_case_generate_task_runs` 挂在 `api_case_` 前缀下,实为 AI 生成域的任务运行表(与 `ai_generate_tasks` 同域);`project_skill_spaces.size` 与 `ai_generate_task_source_archives.size_bytes` 同义不同名不同型;`dump_connection` 输出模型不存在的 `tokenExpiresAt`(恒 null 死字段);`users.email` 无唯一约束且创建不查重。
2. **代码样板**:18 个状态值散落 8 个文件 100+ 处字面量;521 处手写 `Field(alias=...)` 与 `to_camel` 生成结果完全一致;24 个 repository 重复 add/commit/refresh 转发;`worker_tasks` 两个单列索引无查询支撑。

## 决策

- **表/类改名**:`api_case_generate_task_runs` → `ai_generate_task_runs`(物理表名 + 模型类名 `AiGenerateTaskRun` 同步,56 处引用机械替换)。API 路由函数名(`list_api_case_generate_task_runs`)保留——它是 API 领域命名,与表名解耦。
- **列改名且 API 契约不变**:`size` → `size_bytes`(BIGINT),但 `dump_skill`/worker payload 的输出键保持 `"size"`——数据库层统一命名,Go 侧契约零变化。
- **状态枚举**:`core/enums.py` 按实体分 6 个 `StrEnum`(`RunStatus`/`SprintStatus`/`ConnectionStatus`/`BindingStatus`/`ReviewStatus`/`ImportStatus`/`StageStatus`),值字符串与历史/Go worker 契约逐字一致;兼容集合 `SUCCESS_STATUSES`(`{"success","passed","completed"}`)保留,不改历史成功语义。
- **alias 生成器**:全部 schema 统一 `ConfigDict(alias_generator=to_camel, populate_by_name=True)`,删除 520 处与生成一致的冗余 alias;16 处 `AliasChoices`(兼容旧响应名)保留。AST 比对确认 521 处手写 alias 与生成结果零差异,契约测试兜底。
- **repository 基类**:`repositories/base.py` 提供 `BaseRepository`(session 转发 add/add_all/commit/refresh/flush)与 `SoftDeleteRepositoryMixin`(get_active_by_id + soft_delete,子类声明 `model`/`id_column`),删除 24 个 repository 中 64 处重复方法。
- **email 唯一**:空串统一转 NULL(MySQL 唯一索引 NULL 可重复,语义"未提供邮箱"),加 `uq_users_email` 唯一约束,注册时非空邮箱查重(`ErrEmailAlreadyUse`);存量 2 用户无重复。
- **死索引**:删 `ix_worker_tasks_status`/`ix_worker_tasks_worker_id`(claim 走 domain+status 复合,worker_id 校验为应用层比较)。

**Considered Options**: 表改名不动仅改类名(表名继续误导域归属,放弃);alias 保留手写仅加生成器(存量 520 处样板仍在,放弃);repository 样板保留(24 文件重复,放弃);email 强制必填(破坏现有可选邮箱语义,放弃)。若未来引入 ZenTao token 刷新链路,`tokenExpiresAt` 应有真实数据来源时再补列。
