# 需求富文本正文

新增 `documentType=richtext`，对应经服务端清理的 `requirement.html`，元数据仍使用 `documentFileId`、`documentFilename`、`documentHash`。原有 text/docx 读取及 Word 上传继续兼容；不迁移历史数据。`documentContent` 仍用于现有增强文本，不保存富文本正文。

Studio 使用统一上传管线提交 HTML：申请上传、直传 S3、完成校验、关联需求。HTML 上传上限为 1 MiB（同时受平台文件上限约束）。完成阶段先验证原始上传大小和 SHA-256，再用共享白名单清理 HTML，把清理后的字节写入已验证对象，更新文件大小及摘要，最后标记 ready。只有 ready 的文件可以关联或获取下载授权。临时上传失败或需求关联失败沿用已有过期清理；已经关联的旧版本继续保留。

HTML 支持标题、段落、列表、引用、代码、基本表格与 PNG/JPEG 图片。图片只保存 `data-file-id`，不保存临时 URL。需求关联正文时，把其中图片按 attachment 用途关联到同一需求；统一文件服务验证项目、上传者、状态及归属。同一需求已关联图片允许其他有写权限的项目成员继续引用。正文和图片关联与需求更新同一数据库事务提交；关联失败时必须回滚。图片下载验证项目读取权限及需求仍然存在，需求删除后不能申请新下载授权。

AI 分析第一阶段按文档类型选择提取技能：Word/DOCX 使用 `extract-docx-enhanced-text`，richtext 使用 `extract-richtext-enhanced-text`。富文本以原始 HTML 与关联图片输入模型，保留原有 `document_extraction` 1.0 输出及两阶段审核流程。历史 TXT 可继续查看、使用已审核提取产物进行第二阶段理解；重新提取时需替换为 Word 或富文本。

图片通过 `GET /internal/ai-worker/tasks/{task_id}/requirement-images/{file_id}?workerId=...` 获取短期下载票据。接口复用当前运行授权与原始文档身份检查，校验 Worker、有效租约、项目与需求归属，以及图片仍在正文中被引用；票据响应 no-store。任务快照不新增签名 URL。Worker 下载时沿用大小与 SHA-256 校验，图片引用重复时仅下载一次，正文保留所有出现位置。下载失败中止本次准备，不静默丢图。

验证入口：`tests/test_requirement_rich_text.py`、`test_requirement_files.py`、`test_stored_files.py`、`test_stored_file_access.py`。测试使用 SQLite 与 moto，不替代部署环境的 MySQL/S3 验收。

2026-10-08 验证记录：在控制面目录执行以下检查。

```bash
uv run --locked --extra dev python -m pytest tests/test_requirement_rich_text.py tests/test_requirement_files.py tests/test_stored_files.py tests/test_stored_file_access.py tests/test_app_contract.py tests/test_go_field_contracts.py tests/test_auth_contract.py tests/test_project_membership_api.py tests/test_developer_access.py tests/test_bug_api.py -q
```

122 项通过。修改的 6 个业务模块（`core/object_storage.py`、`domain/rich_text.py`、`schemas/requirement.py`、`services/requirement.py`、`services/stored_file.py`、`services/stored_file_access.py`）及 2 个后端测试通过 Ruff check 和 format --check。

同一业务模块范围执行 `uv run --locked --extra dev mypy --python-version 3.12 --check-untyped-defs ...` 仍有 1 个存量错误：`core/object_storage.py:59` 的 `Config(s3=...)` 对 addressing_style 的字符串类型与 boto3 stub 不匹配，该行本次未改。类型检查不能报告为通过。`uv run --locked --extra dev python -m pytest tests/test_storage_live.py -q` 因未设置真实存储显式启用变量跳过 9 项；真实 MySQL/S3 和浏览器跨域上传仍未验收。
