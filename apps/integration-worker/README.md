# integration-worker

独立执行禅道 Bug 创建、附件、正文图片和字段修改。项目说明、协议及恢复流程见 [docs/integration-worker](../../docs/integration-worker/README.md)。

```sh
uv sync --locked --extra dev
# 仓库根目录生成 config/local.toml
python3 ../../scripts/manage.py configure --mode local
uv run --locked mtx-integration-worker --config config/local.toml
```

配置优先级为 `--config/-c`、`APP_CONF`、`config/local.toml`。本服务没有公开监听端口。
