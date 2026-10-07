# ZenTao-MCP 手动部署入口

本目录只保存部署配置，直接使用已经发布的镜像。完整配置、多项目网络与排障见 [部署指南](../../docs/control-plane/zentao-mcp-deployment.md)。

在本目录或复制后的独立部署目录执行：

```sh
mkdir -p config
cp config.example.yaml config/config.yaml
# 编辑 config/config.yaml：base_url 与 instance_url 指向同一实际禅道。
# 编辑 compose.yaml：为每个项目设置独立名称与宿主机端口。
docker compose pull
python3 enable-bug-options.py
docker compose -f compose.yaml -f compose.bug-options.yaml up -d
docker compose ps
```

默认容器名 `mtx-zentao-project-a`，宿主机端口 9091。个人 Token 由成员在平台填写，不写入部署配置。

用户自行启停；平台默认编排不包含本服务。本仓库内的实际配置目录 `config/` 已被忽略。

版本分页、Bug 指派和已确认文件的元信息查询依赖 `compose.bug-options.yaml` 的接口定义挂载；后续启停也使用上述两个 `-f` 参数。生成脚本只读取镜像中已发布的接口定义，不使用个人 Token。旧部署需重新生成 schema；启用方式及禅道 22.6 图片归属修复前提见完整部署指南。
