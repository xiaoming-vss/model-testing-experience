# ZenTao-MCP 手动部署

平台仓库只保存部署配置，使用已经发布到用户镜像仓库的镜像。用户手动启动容器后，项目所有者在「基础服务 → MCP」填写完整地址，成员分别保存自己的 Token。推荐每个项目一个容器，镜像共用，配置、名称和端口独立。

## 部署材料与镜像

`deploy/zentao-mcp/` 保存以下部署材料：

- `compose.yaml`：引用固定镜像版本及摘要，定义容器、挂载、端口和健康检查。
- `config.example.yaml`：无凭据的 MCP 上游配置示例。
- `README.md`：启动入口和完整说明导航。
- `enable-bug-options.py`：从固定镜像生成版本分页、Bug 指派和文件元信息查询的 schema 及 Compose 挂载覆盖。
- `zentao-22.6-api-form-uid.patch`：隔离验收所用禅道 22.6 REST 编辑器 uid 修复，应用于禅道源码，不是 MCP 容器。

镜像：

```text
crpi-dkip02fuesikq3zy.cn-hangzhou.personal.cr.aliyuncs.com/xiaoming-x/zentao-mcp:2026-10-04-attachments
```

架构为 `linux/amd64`；模板固定摘要 `sha256:9b576d52c5bcb3fdfbd1c787ac3ce40b3cbf71ecae7b031fba794a8b8d3fd7ef`。镜像包含 OpenAPI schema、`get_zentao_instance`、`upload_bug_attachment`、`get_bug_attachment` 工具、对外 `instance_url` 配置、PM 类型兼容与 `module` 字段修正。上游源码固定于 `d5ea85fe609af9cb38baf7390fa092b02984dd78`，上游 MIT 许可证在镜像 `/licenses/zentao-mcp-LICENSE` 中。

镜像在平台项目外通过单个独立 Dockerfile 构建，必要补丁内嵌其中，不另行保存构建工程。部署无需源码、Go、Python 或平台的 `config/platform.toml`。部署环境需要 Docker、Docker Compose 以及对上述镜像仓库的拉取权限；私有仓库先在本机执行 `docker login crpi-dkip02fuesikq3zy.cn-hangzhou.personal.cr.aliyuncs.com`。

## 首次配置与启动

进入 `deploy/zentao-mcp/`，或将该目录的部署文件及 `enable-bug-options.py` 复制到一个独立目录，在该目录执行：

```sh
mkdir -p config
# 仅首次准备配置；已有实际配置时直接编辑，不重新覆盖。
cp config.example.yaml config/config.yaml
```

编辑 `config/config.yaml` 中的两个地址：

```yaml
base_url: "https://你的禅道地址/zentao/api.php/v2"
instance_url: "https://你的禅道地址/zentao"
```

`base_url` 是 MCP 容器实际可达的禅道 API v2 地址；`instance_url` 是浏览器访问同一禅道实例的地址。两者可因容器网络不同而使用不同主机名，但必须指向同一实例，并保留安装子路径。部署文件不填写个人 Token。

默认 Compose 项目名和容器名为 `mtx-zentao-project-a`，只在宿主机回环地址发布 9091；容器内部监听 9090。不同项目应修改 `compose.yaml` 中的名称默认值和宿主机端口默认值，也可通过部署目录的本地 `.env` 覆盖：

```dotenv
MCP_PROJECT_NAME=mtx-zentao-project-a
MCP_HOST_PORT=9091
MCP_BIND_HOST=127.0.0.1
```

配置准备好后直接运行：

```sh
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
docker compose logs --tail 100
```

实际配置目录以只读方式挂载，容器使用非 root 用户；配置目录和文件须分别可遍历、可读。仓库内的 `deploy/zentao-mcp/config/` 与 `.env` 已被忽略；复制到其他仓库时也应忽略实际配置。平台自己的配置仍沿用原有 TOML 和 `manage.py`，MCP 是独立部署例外。旧平台 TOML 中的 `zentao_mcp` 段不再使用。

## 多项目与访问地址

项目 B 复制一份到另一目录，分别编辑其 `config/config.yaml`，在该目录 `.env` 中配置：

```dotenv
MCP_PROJECT_NAME=mtx-zentao-project-b
MCP_HOST_PORT=9092
```

随后在 B 的目录执行 `docker compose up -d`。不要让两个目录使用相同的 Compose 项目名或容器名；同一宿主机发布端口也要不同。镜像和容器内的 9090 可以共用。

| 平台后端位置 | 项目 A 填写的 MCP 地址 | 项目 B 填写的 MCP 地址 |
| --- | --- | --- |
| 同一宿主机直接运行 | `http://127.0.0.1:9091/zentao/mcp` | `http://127.0.0.1:9092/zentao/mcp` |
| 同一 Docker 网络 | `http://mtx-zentao-project-a:9090/zentao/mcp` | `http://mtx-zentao-project-b:9090/zentao/mcp` |
| 另一台主机 | 部署主机可达地址加 A 发布端口 | 部署主机可达地址加 B 发布端口 |

后端在容器内时，`127.0.0.1` 指向后端自身。与后端使用已有 Docker 网络时，先用 `docker network ls` 确认网络，再在各部署目录的 `.env` 设置：

```dotenv
MCP_NETWORK=mtx_default
MCP_EXTERNAL_NETWORK=true
```

共享网络必须已存在。不需要发布宿主机端口时，删除 `compose.yaml` 的整个 `ports` 段；直接通过各自独立的容器名称访问。需要让另一主机访问时调整 `MCP_BIND_HOST` 并配置部署环境的网络访问控制。

如果禅道也在容器内，确保 MCP 可以访问其网络名称或宿主机地址。`http://zentao/api.php/v2` 仅适用于实际存在且同网络可达的 `zentao` 容器。

## 修改、重启和停止

MCP 启动时加载配置，没有热加载。编辑 `config/config.yaml` 后，在对应部署目录执行：

```sh
# 上游配置改变：重启这个项目容器。
docker compose restart
# 端口、名称、网络或镜像改变：重新创建这个项目部署。
docker compose up -d
# 停止并移除这个项目的容器及专用网络。
docker compose down
```

目录挂载支持编辑器通过原子替换保存配置，重启后读取新文件。普通绑定、推送和个人 Token 更新无需重启。平台删除项目 MCP 配置不会停止容器，部署负责人自行处理已不用的部署。

更换目标后，项目所有者在平台编辑 MCP 服务地址，勾选切换及旧绑定清理的确认复选框后保存，平台清除该项目的禅道绑定、测试单外部缺陷号、Bug 和附件推送关联，再按新目标重新绑定。旧推送信息保留在 Bug 动态，原禅道数据不删除；旧目标授权失效。同目标更换 MCP 端点保留关联和授权。实例信息读取成功仅表示 MCP 可连接和配置可读取，禅道业务权限在实际操作时验证。用例推送的现有限制见 [用例推送](zentao-mcp-case-push.md)。

## 排障与可选验收

- 拉取失败：核对仓库登录状态、拉取权限及镜像地址。无需现场构建镜像。
- 端口或名称冲突：Docker 启动时报告冲突；修改对应部署的名称或端口后重新创建，平台不分配端口。
- 配置加载失败：确认 `config/config.yaml` 存在且容器用户可读；不要将整个配置目录设为仅本人可访问。
- 容器不健康：查看状态与日志。健康检查访问容器内部 `http://127.0.0.1:8080/healthz`，不代表禅道业务权限有效。
- 平台连接失败：核对后端所在环境、网络及完整 `/zentao/mcp` 路径；浏览器可达不等于后端可达。
- 目标变化或混杂历史：确认 API 地址与对外地址映射；确实要切换时，由项目所有者在平台确认清除旧绑定，再重新绑定。普通刷新不会清理数据。
- 禅道 401／403：成员更新本人的 Token 或向禅道管理员确认权限，不借用其他成员凭据。

## 禅道 22.6 图片归属检查

本次隔离环境的 `framework/api/router.class.php::setFormData()` 固定设置 `$_POST['uid'] = '1'`。同一 Token 会话随后创建另一个 Bug 时，文件处理沿用前一次的编辑器图片 album，已上传图片的 objectID 被更新到新 Bug。MCP 或 Worker 仅检查上传成功无法阻止这个上游行为；不能通过放宽附件归属校验绕过。

当前验收在自建禅道容器中应用上述 patch，使每次 REST 请求获得新的 uid，重启 PHP/Apache 后连续创建 Bug，分别通过 API 和数据库确认原图片归属没有变化。已有错误归属不会由该 patch 自动修复。本次只对自建夹具中明确创建的两条文件记录作了条件修复；这不是生产修复工具或通用 SQL 操作指引。

启用集成写入之前，禅道部署负责人需确认其实际版本是否存在固定 uid；若存在，采用经测试的上游修复或版本升级。仓库 patch 只针对本次验证的 22.6 源码，应用前核对目标文件与版本、保存回退材料；重新加载 PHP 运行环境后验证“带图片 Bug A → 创建 Bug B → 回读 A 图片”，要求 API 归属、文件字节及 A 的原生图片链接都保持一致。本仓库的 MCP schema 生成脚本不会修改禅道源码。未通过该项时保持集成执行开关关闭。

当前本地环境的镜像替换还验证了两项部署细节：保留禅道原来的全部 Docker 网络及 `zentao` 别名，否则 MCP 的容器内地址可能无法访问新容器；迁移原 `/apps/zentao/tmp/session` 和 `apisession`，保留文件权限与所有者，否则即使 `/data` 数据卷保留，原 Web 会话和个人 REST Token 仍可能失效。这些会话文件包含秘密，只能在受控备份目录保存，不提交或公开。MCP 附件来源 relay 使用 `network_mode: service:zentao-mcp` 时，重建 MCP 必须同时重建 relay，以进入同一新网络命名空间。

22.6 router 支持 `ZT_SESSION_PATH` 和 `ZT_APISESSION_PATH`。本地修复镜像分别指向现有持久卷中的 `/data/php/session` 与 `/data/php/apisession`，并迁移原会话文件；只保存 `/data` 而继续使用应用 tmp 默认目录，无法保证下一次容器重建后的会话连续性。迁移时保持原会话身份和权限，不以轮换个人 Token 代替会话保留。

平台默认 `manage.py compose up` 不启动 MCP，也不再提供 `manage.py zentao` 命令。MCP 由用户在独立部署目录直接运行 Docker Compose。

维护模板时可在平台仓库根目录显式运行隔离验收：

```sh
MTX_TEST_ZENTAO_MCP_RUNTIME=1 \
  python3 -m unittest discover -s tests -p test_zentao_mcp_runtime.py -v
```

此测试拉取模板引用的已发布镜像，以独立名称和随机端口启动两个临时容器，只调用不访问上游的实例信息工具。验证配置编辑后重启生效、停止一个不影响另一个，最后清理容器和网络。测试使用虚拟目标及测试 Token，不修改实际配置或现有服务。未设置上述环境变量时，常规测试跳过容器验收，不启动服务。

实现及验证结果见 [验证记录](zentao-mcp-manual-acceptance-2026-10-04.md)。真实部署环境中的网络、个人 Token 和绑定、推送仍由部署负责人验收。

## 独立附件工具升级（2026-10-04）

附件版镜像已构建、通过隔离容器验证，并发布为 `crpi-dkip02fuesikq3zy.cn-hangzhou.personal.cr.aliyuncs.com/xiaoming-x/zentao-mcp:2026-10-04-attachments`，仓库摘要为 `sha256:9b576d52c5bcb3fdfbd1c787ac3ce40b3cbf71ecae7b031fba794a8b8d3fd7ef`；已读取远端 manifest 核对。部署模板固定此附件版摘要。构建材料仍只有项目外的 `/home/xiaoming/zentao-mcp-image/Dockerfile`，内嵌上传工具、核对工具及 Go 测试，不在平台仓库增加构建工程。旧版 `2026-10-04` 镜像不含附件工具，已有部署需更新镜像引用并重新创建容器。

部署负责人将对应部署的 `image` 改为上述已发布镜像并固定摘要，然后执行 `docker compose pull`、`docker compose up -d`。保留原入口、禅道目标、网络和 Token 管理方式。已有服务升级前保留原 Compose 与 YAML 的回退材料，完成下面配置后手动重新创建 MCP；平台不代为启停。

在对应 `servers` 项下增加：

```yaml
# 必须是实际签名 URL 的协议、主机和端口；无路径、凭据或查询参数。
attachment_source_origins: ["https://你的S3地址"]
attachment_max_bytes: 104857600
```

下载客户端只访问这些来源，禁止所有重定向且不使用环境代理，不附带禅道 Token。原签名 URL 的主机和路径不能临时替换，否则签名会失效。若平台使用宿主机 `127.0.0.1` 签发 URL，容器内通常无法直接访问；应统一配置平台、浏览器、MCP 均能访问的 S3 Endpoint，再生成运行配置。原地址未统一前，上传工具会明确失败，不将链接当作已上传附件。

MCP 默认限额 100 MiB，可配置至 1 GiB；需同时满足平台 S3 限额、PHP `upload_max_filesize/post_max_size`、Web 代理请求体与超时限制。工具在临时目录保存原文件和 multipart 副本，当前文件至少需约两倍空间。控制面单次工具调用时限 180 秒，MCP 工具总时限 160 秒；多个附件顺序处理，平台代理须允许相应时长。扩展工具还需 allow/block 规则允许 `POST /files`、`GET /bugs/:bugID`，核对工具另需 `GET /files/:fileID` 和下载路径。

2026-10-07 对发布镜像 `zentao-mcp:2026-10-04-attachments` 的实际分段下载验收确认：源响应开始后，持续下载仍在约 60 秒截止；未下载完整的文件返回 `file_integrity_failed` 且 `uncertain=false`，不会提交到禅道。工具总时限 160 秒与调用方等待 180 秒不能延长这个下载阶段。需要更长下载时间时应先调整并发布 MCP 实现及对应验收，平台单独延长等待没有作用。显式检查如下：

```sh
MTX_TEST_ZENTAO_MCP_ATTACHMENTS=1 MTX_TEST_ZENTAO_MCP_SOURCE_DEADLINE=1 \
  python3 -m unittest discover -s tests -p test_zentao_mcp_attachment_runtime.py -v
```

该检查使用真实发布二进制及隔离 HTTP 来源，验证 60 秒截止、明确失败与未执行 POST /files；真实 S3/禅道链路结果和 180 秒成功响应延迟场景分别记入[集成验收记录](../integration-worker/acceptance-2026-10-07.md)。

发布控制面代码时执行数据库迁移至 `20261004_0026`，部署 Studio 的本轮构建。MCP、控制面迁移和 Studio 三者应一起升级；升级后读取工具列表应出现 `upload_bug_attachment`、`get_bug_attachment`。具体执行入口沿用部署现有流程；独立控制面可在应用目录执行 `uv run alembic upgrade head`，平台容器模式沿用既有迁移服务。

隔离协议验收可在仓库根目录运行：

```sh
MTX_TEST_ZENTAO_MCP_ATTACHMENTS=1 \
  python3 -m unittest discover -s tests -p test_zentao_mcp_attachment_runtime.py -v
```

默认读取本机上述镜像；可通过 `MTX_ATTACHMENT_MCP_IMAGE` 指定已经构建的附件版镜像。该测试仅启动临时容器和虚拟 HTTP 上游，不重启现有服务、不读取真实凭据，退出后清理。正常 root 测试发现不会启动容器。

真实业务验收仍须使用当前成员 Token 和测试 Bug：首次推送及已有 Bug 补传截图、视频、日志，确认附件出现在正确 Bug 的附件区，登录后能查看或下载；重复推送不产生重复文件。隔离网络和数据库测试无法替代此验收。图片可能被禅道原生压缩，待核对的文件若不再匹配原字节摘要，不自动关联或重传。

### 本机升级与发布核对（2026-10-04）

本机独立部署 `/home/xiaoming/zentao-mcp-deploy` 已升级附件版，MCP 与下载转发容器均健康；工具列表确认包含上传及核对工具。数据库已到 `20261004_0027`。现有 S3 签名地址为 `http://localhost:19000`，本机通过共享 MCP 网络命名空间的 IPv4/IPv6 回环转发访问 `rustfs:9000`，不修改签名地址；此转发属于本机配置，其他部署应使用实际可达的 S3 来源。Bug #6 的五个附件从 MCP 容器下载成功，大小及 SHA-256 均匹配；禅道 PHP 上传和请求体上限均为 128M。升级前 Compose 和 YAML 保存在独立部署目录的 `backup-attachments-20261004-193006/`。这些检查尚不代表真实禅道附件上传、查看与下载验收完成。

## 影响版本与指派人接口定义补丁（2026-10-06）

Bug 新建及已同步 Bug 编辑弹窗从禅道读取影响版本和人员列表，提交选择的版本 ID 和人员账号。既有附件版镜像无需重新构建或发布，但其内置 OpenAPI 缺少版本分页和 Bug 指派参数，需要生成并挂载接口定义补丁。脚本从 Compose 固定的已发布镜像读取原始定义，保留已有工具，补充创建/编辑 Bug 的 `assignedTo`、执行版本查询的路径及分页参数；不读取个人 Token，也不修改真实禅道数据。

复制新增的 `enable-bug-options.py` 和 `compose.bug-options.yaml` 到现有独立部署目录。在该目录执行：

```sh
python3 enable-bug-options.py
docker compose -f compose.yaml -f compose.bug-options.yaml config --quiet
docker compose -f compose.yaml -f compose.bug-options.yaml up -d
```

生成的 `config/bug-options-openapi.json` 是被忽略的运行配置，不提交仓库；挂载覆盖容器内 `/config/zentao-openapi.json`，实际 YAML 的 `schema_url` 保持该地址。首次启动、后续启停和配置检查均须包含两个 `-f` 参数。镜像升级后重新执行生成脚本并重新创建 MCP，确保补丁基于当前镜像。脚本支持 `--image` 和 `--output`，供旧目录布局或已安装本地镜像使用。

若部署已有自定义接口定义，先备份并合并所需字段，不能用镜像默认定义覆盖自己的扩展。补丁只补接口描述，不授予业务权限，成员仍需本人 Token 的用户查询及 Bug 创建权限。列表超过查询上限、分页不完整或工具缺少分页参数时平台报错，不提供不完整候选项。

回退时保留生成文件，使用原 Compose 文件重新创建 MCP 即可恢复镜像内定义；新弹窗会提示版本工具需要升级。原 Bug 与附件数据不受影响。

本机 `/home/xiaoming/zentao-mcp-deploy` 已生成并挂载补丁，MCP 与附件下载转发容器已重新创建且健康，工具列表确认分页参数及 `assignedTo` 已生效。原 Compose 备份为 `compose.yaml.before-bug-options-20261006-214723`。控制面相关 72 项测试和 Studio 弹窗 11 项测试通过，Studio `npm run verify` 通过；隔离真实 MCP 容器验证版本分页、用户分页和指派字段到上游的传输。该验收没有新建、转派或修改任何真实禅道 Bug。

```sh
MTX_TEST_ZENTAO_MCP_BUG_OPTIONS=1 \
  python3 -m unittest discover -s tests -p test_zentao_mcp_bug_options_runtime.py -v
```

默认常规测试跳过容器验收；显式验收使用临时容器与虚拟上游，退出后清理。

### 已同步 Bug 的两项编辑（2026-10-06）

已同步 Bug 在「推送到禅道」统一弹窗中修改版本和指派人，复用本节已有的接口定义补丁，无需再次升级 MCP 或迁移数据库。编辑先读取原 Bug 的真实值，PATCH 仅传变化字段，并在修改后回读确认；创建关联及附件补传状态独立保留。新的容器验收同时验证 `PUT /bugs/50` 的版本和指派字段实际传输。控制面字段编辑 18 项测试、之前的创建/候选项/附件/正文图片 72 项测试及 Studio 弹窗 14 项测试通过；类型、生产代码 lint（排除临时 `.scratch` 预览）、主题检查和构建通过。未写入真实禅道 Bug。
