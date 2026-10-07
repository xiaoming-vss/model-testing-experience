# AI Worker 开发规则

开发和审查 `apps/ai-worker/` 前，必须阅读[通用后端规则](../agents/backend-development.md)、[领域上下文](CONTEXT.md)及相关 ADR。本文件补充模型执行与产物回传的要求，源码和命令默认相对该应用目录。

## 模块与运行边界

- 沿用本项目 Python 3.13、独立 `pyproject.toml`、`uv.lock` 及启动入口；不引入控制面 ORM、Web 服务或直接数据库访问。
- `app/` 装配执行依赖，`worker/` 管理轮询、领取、心跳和运行，`tasks/` 管理各类任务，`platform/` 封装控制面协议，`nanobot/` 及 `nanobot_runtime/` 负责现有模型运行时。
- 新任务类型必须同时更新分派、任务载荷、执行器、结果解析与控制面消费方；不能只在提示词中添加名称就视为支持新任务。
- 调整并发、停止或中断策略时，必须保留独立任务 workspace 和任务关联身份，并验证心跳及结果回传，不套用其他 Worker 的排空期限。

## 输入 产物与回传

任务通过控制面领取，权限材料按任务协议获取。技能执行前按当前任务或阶段从控制面取得默认技能，验证下载大小与 SHA-256；失败按既有契约报告，不静默退回旧技能或复用其他运行输入。默认技能和项目自定义技能的参与范围以领域规格为准。

模型输出必须经过对应任务的格式、Schema 和业务校验后回传，不能仅凭可解析 JSON/YAML 或模型自述判定成功。需求分析沿用已确认的材料提取、需求理解两阶段及结构化 JSON；其他任务各自保留契约，不能统一替换成一种输出格式。

功能用例编号复用平台分配和修订认回规则，不信任模型生成的同名值。模型调用恢复、阶段重新执行和结果回传重试必须分别定义；回传失败不能自动重新调用模型。运行日志按通用规则记录任务与阶段标识，不记录完整提示词、输入材料、模型输出或凭据。

## 验证入口

本项目使用 unittest 和 `dev` 依赖组，当前未配置 mypy；公共接口类型按通用规则通过审查和现有契约验证。

```sh
uv sync --locked --group dev
uv run --locked --group dev python -m unittest discover -s tests -v
uv run --locked --group dev ruff check .
uv run --locked --group dev ruff format --check <修改的源码及测试路径>
```

| 变更 | 必须检查的入口 |
| --- | --- |
| 领取、分派、运行及回传 | `tests/unit/test_task_source.py`、`test_worker_dispatcher.py`、`test_worker_runner.py`、`test_result_sink.py` 及 `test_worker_main.py` |
| 控制面通信与凭据 | `tests/unit/test_http_client.py`，加控制面 `test_worker_contract.py` 和相应任务协议验证 |
| 需求分析 | `tests/unit/tasks/requirement_analysis/test_executor.py`、`test_two_stage.py`，加控制面的需求分析专项 |
| 功能用例校验与编号 | `tests/unit/tasks/functional_case_generate/test_validation.py`、`test_case_ids.py`、`test_revision.py` |
| 技能或签名下载 | `tests/unit/platform/test_skills.py`、`test_signed_download.py`，真实存储变化追加显式验收 |
| 其他模型任务 | 对应 `tests/unit/tasks/` 专项，报告和图谱使用各自执行器回归 |

同一单元格中的短文件名相对首个路径所在目录。新增任务必须添加其行为专项；变更模型运行时同时检查 `test_nanobot_chain_runner.py` 等实际受影响入口。模拟模型回归不代表真实模型、GitLab 或 S3 已完成验收。
