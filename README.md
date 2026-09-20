# Model Testing Experience（MTX）

Model Testing Experience（简称 MTX）是面向测试协作的平台，包含前端、控制面、AI Worker、API/UI Worker 和禅道连接服务。各项目保留自己的依赖、锁文件、Dockerfile、测试和独立启动入口。

| Compose/脚本名称 | 项目目录 | 作用 |
| --- | --- | --- |
| studio | `apps/studio` | React 前端 |
| control-plane | `apps/control-plane` | FastAPI 控制面 |
| ai-worker | `apps/ai-worker` | AI 测试生成 |
| api-ui-worker | `apps/api-ui-worker` | API / Playwright 测试执行 |
| zentao | `apps/connector-zentao` | 禅道适配 |
| mysql | — | MySQL 8.4 |
| migrate | `apps/control-plane` | 一次性数据库迁移 |

## 目录结构

```text
model-testing-experience/
├── apps/
│   ├── studio/
│   ├── control-plane/
│   ├── ai-worker/
│   ├── api-ui-worker/
│   └── connector-zentao/
├── deploy/         # 可选部署覆盖配置
├── config/          # 统一配置与示例
├── scripts/         # 配置生成与启动入口
├── tests/           # 仓库级配置、部署测试
├── docs/           # 全部项目文档与统一部署指南
└── compose.yaml
```

各应用的源码、依赖文件、锁文件、Dockerfile 和业务测试保留在各自目录内。包名和镜像统一使用 MTX 命名，旧启动命令保留兼容入口，详见 [命名与兼容说明](docs/naming.md)。根目录 README 提供快速入口，详细说明集中维护在 `docs/`。

## 快速启动

在仓库根目录执行：

```sh
python3 scripts/manage.py init
python3 scripts/manage.py compose up -d --build
```

前端默认访问 http://127.0.0.1:8081 。首次运行前按部署指南确认 `config/platform.toml` 中的地址与端口。

## 文档入口

- [文档总索引](docs/README.md)
- [统一配置、部署与本地开发](docs/deployment.md)
- [MTX 命名与旧部署兼容](docs/naming.md)
- [领域上下文导航](CONTEXT-MAP.md)
