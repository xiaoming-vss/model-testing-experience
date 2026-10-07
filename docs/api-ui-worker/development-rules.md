# API/UI Worker 开发规则

开发和审查 `apps/api-ui-worker/` 前，必须阅读[通用后端规则](../agents/backend-development.md)和[项目说明](README.md)。本文件补充 API 与浏览器执行要求，源码和命令默认相对该应用目录。

## 模块与运行边界

- 沿用本项目 Python 3.12、独立依赖、锁文件、Dockerfile 和启动入口，保留 `requirements.txt` 的项目用途。升级 Playwright 时同步验证镜像及浏览器版本约束。
- `poller/` 管理领取、心跳与回传，`control_plane/` 封装控制面通信及文件授权，`api/` 执行请求、模板、提取与断言，`ui/` 管理浏览器、定位与步骤执行，`contracts/` 维护载荷和结果类型。
- 保留每个 Worker 同时执行一个任务及 API/UI 队列交替优先的已确认语义。修改调度时必须验证两类任务的公平性、心跳和停止，不直接沿用 AI Worker 的并发数量。
- 同步控制面调用和上传通过已有线程委托方式执行，不能阻塞异步 HTTP 或浏览器运行。业务数据仍由控制面通过协议管理。

## 执行与产物

新增 API 行为必须明确变量作用域、模板解析、提取、断言及失败后是否继续；新增 UI 步骤必须同时维护输入契约、规范化、执行器、超时和结果。运行快照与当前配置的覆盖关系必须保持明确，不把缺省、空字符串和 `null` 自动互换。

截图和 Trace 通过控制面短期授权上传私有 S3，完成核验后回传稳定文件引用。上传或最终回传失败按原流程保留排障材料；只有平台接受对应结果后按生命周期清理，不回退本地下载 URL。停止与取消必须处理在途任务、浏览器资源和心跳，并补清理及回传测试。

日志记录任务身份、状态和安全错误；不能输出完整步骤、运行变量、请求响应正文或含凭据的浏览器配置。离线 `once` 模式保留独立调试语义，不伪造平台任务归属或正式文件关联。

## 验证入口

```sh
uv sync --locked --extra dev
uv run --locked --extra dev python -m pytest
uv run --locked --extra dev ruff check <修改的源码及测试路径>
uv run --locked --extra dev ruff format --check <修改的源码及测试路径>
uv run --locked --extra dev mypy --python-version 3.12 --check-untyped-defs <修改的业务模块路径>
```

| 变更 | 必跑入口 |
| --- | --- |
| 调度、心跳及停止 | `tests/test_poller_regressions.py`、`test_shutdown.py` |
| 控制面通信与载荷 | `tests/test_control_plane_client.py`，加控制面 `test_worker_contract.py` |
| API 执行 | `tests/test_api_runner.py`，加受影响模板、变量和断言行为回归 |
| UI 步骤及浏览器选项 | `tests/test_ui_steps_contract.py`、`test_ui_step_executor.py`、`test_ui_browser_options.py` |
| 文件上传与清理 | `tests/test_artifact_upload.py`，加控制面文件授权与实际上传路径验收 |
| 配置加载 | `tests/test_config.py`；保留无环境变量覆盖的现有契约 |

同一单元格中的短文件名相对 `tests/`。源码修改执行对应专项与质量检查，共享运行层变化扩大到全量回归。需要真实浏览器的行为必须在项目规定的 Playwright 环境中验证，不能把模拟定位器或模拟上传作为完整端到端验收。
