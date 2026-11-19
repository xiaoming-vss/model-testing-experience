# Kubernetes 部署

平台采用 **chart-per-service**：每个服务一个独立 Helm chart，独立安装、独立升级、独立 values。仓库不再提供 umbrella chart；服务之间通过 K8s Service 名称通信。

- `deploy/helm/charts/<service>/`：每个服务的完整 chart，包含工作负载、Service、ConfigMap、PVC 等资源，以及该 chart 自己的 `values.yaml`。
- 每个 chart 都可以单独 `helm install`，不依赖其他 chart 的发布。
- 当前只覆盖平台本身，不包含性能 Worker；性能 Worker 已支持 Compose `poll` 模式，Helm 待后续补充。

## 前置条件

- Kubernetes 1.30+，自建 kubeadm 集群或等价环境
- Helm 3.16+
- 外部 MySQL、Redis、S3 兼容存储；本仓库不部署这些有状态服务
- 已构建并推送到镜像仓库的五个镜像：
  - `mtx/control-plane`
  - `mtx/studio`
  - `mtx/ai-worker`
  - `mtx/api-ui-worker`
  - `mtx/integration-worker`
- 一个可用 namespace；平台服务全部部署在同一 namespace

性能 Worker 当前未提供 Helm chart；已支持控制面 `poll` 模式和 Compose，后续按压测节点池补充镜像、chart 和 values。
- Studio 使用 NodePort，默认 `30080`；不需要 Ingress

## 目录结构

```text
deploy/helm/charts/
  control-plane/
    Chart.yaml
    values.yaml
    templates/
  studio/
  ai-worker/
  api-ui-worker/
  integration-worker/
```

每个 chart 的 `values.yaml` 就是该服务唯一的部署 values。不存在全局 values 文件；多个服务共享的关键配置必须与 `config/platform.toml` 保持一致，字段清单、校验规则和允许差异见[配置事实源与一致性策略](#配置事实源与一致性策略)。

原 umbrella 的 `values.yaml` 不能直接给单个 chart 使用：单个 chart 只认自己顶层的 key。迁移时把原 `control-plane:`、`studio:` 等 section 的内容分别拆成对应 chart 的 values 文件；所有服务的 `configToml` 都已改成结构化 `config`，studio 的 `apiUpstream` 改成 `config.apiUpstream`。

## 配置事实源与一致性策略

决策日期：2026-11-19；状态：已接受。

`config/platform.example.toml` 与本地 `config/platform.toml` 是平台配置的唯一事实源；Helm values 是同一配置在具体集群上的投影。两者不生成同一份文件，但关键字段必须一致，并由脚本校验。

### 候选方案

| 方案 | 做法 | 优点 | 缺点 |
| --- | --- | --- | --- |
| A 生成 | `manage.py` 从 `platform.toml` 生成完整 values | 单一事实源最彻底 | 需覆盖 Helm 合并语义、Secret、镜像和存储等集群字段；chart 独立 values 退化；成本最高 |
| B 校验（选定） | 脚本读取 `platform.toml` 与各 chart values，比较关键字段 | 直接阻止会导致启动失败、认证失败或数据不可达的漂移；保留独立安装升级；成本低 | 非关键字段仍可不同，需要维护字段清单 |
| C 例外清单 | 文档列出字段，人工核对 | 最轻 | 不可验证，无法发现漂移 |

### 判断标准与结论

按“漂移是否会造成启动失败、认证失败或数据不可达”划分，而不是要求所有字段相同。chart 的副本数、资源、镜像 tag、存储大小、Service/NodePort 属于集群自身的发布参数，不属于平台共享配置。

选定 B：`platform.toml` 是共享语义的唯一事实源；K8s values 可以覆盖与集群绑定、且不影响共享语义的字段。检查命令为 `python3 scripts/check_k8s_config.py`：默认对比平台示例与 chart 默认 values，部署时加 `--platform-config config/platform.toml --values-dir .runtime/k8s`。命令与前置条件见[验证命令矩阵](commands.md#根目录与部署编排)。

### 必须一致的关键字段

| 语义 | `config/platform.toml` | Helm values |
| --- | --- | --- |
| Worker 令牌 | `shared.worker_token` | control-plane `config.security.worker.key`；ai-worker `config.platform.worker_token`；api-ui-worker `config.control_plane.worker_token` |
| 集成 Worker 令牌 | `shared.integration_worker_token` | control-plane `config.security.integration_worker.key`；integration-worker `config.control_plane.worker_token` |
| JWT 密钥 | `shared.jwt_key` | control-plane `config.security.jwt.key` |
| 集成接口密钥 | `shared.integration_key` | control-plane `config.security.integration.key` |
| 超级管理员 | `control_plane.security.super_admin.username` / `email` | control-plane `config.security.super_admin.username` / `email` |
| 集成运行代次 | `shared.integration_runtime_generation`（启用时） | control-plane `config.integration_execution.runtime_generation`（启用时） |
| 数据库 | `database.url`（非空时） | control-plane `config.data.db.user.dsn` |
| Redis | `redis.url`（非空时） | control-plane `config.test_run_notifications.redis_url`；api-ui-worker `config.notifications.redis_url` |
| S3 | `control_plane.storage.s3.*` | control-plane `config.storage.s3.*`（`enabled` / `endpoint` / `region` / `bucket` / `access_key` / `secret_key` / `prefix`） |
| AI 执行底座 | `ai_worker.agent.backend` | ai-worker `config.agent.backend` |

校验规则：

- 密钥、令牌只比较相等性，不输出原值；空值和 `GENERATE`、`change-me` 等占位值按未配置处理并报告，不视为一致。
- `database.url` 或 `redis.url` 为空表示 Compose 使用内置服务。此时 K8s 必须显式填写外部数据库地址，Redis 可以留空降级；不拿 Compose 内置地址与 K8s 地址比较。
- 超级管理员的 `initial_password` 只检查非占位；它仅在首次启动 seed 时使用，允许每个集群独立设置。
- `agent.backend` 必须一致；ai-worker chart 默认值与平台示例同为 `nanobot`，切换为 `pi` 时两侧同步修改。

### 明确例外（允许不同）

| 字段 | 原因 |
| --- | --- |
| 镜像仓库/tag/pullPolicy、`replicaCount`、`resources`、调度字段、`terminationGracePeriodSeconds` | 集群发布参数 |
| Service type/port/nodePort、`healthPort`、PVC 容量/StorageClass、emptyDir 上限 | 集群资源与暴露方式 |
| `config.apiUpstream`、各 Worker 的 `base_url` | K8s 内使用 Service DNS（`http://control-plane:9000`），不是浏览器或 Compose 地址 |
| `/data/runtime`、`/app/logs`、`/app/artifacts`、`/app/runtime` 等容器路径 | chart 挂载约定 |
| control-plane `config.http.host` | K8s 固定为 `0.0.0.0` |
| 性能 Worker 的 `shared.perf_worker_token` | 暂无 Helm chart |
| 非安全、非连通性的调优字段（连接池、超时、保留天数、导入预算等） | 允许按集群容量覆盖 |

性能 Worker 没有 chart，检查脚本不要求其 values；后续新增 chart 时把对应关键字段补入清单。

## Values 的 key

### 所有 chart 共有

| key | 说明 |
| --- | --- |
| `replicaCount` | 副本数 |
| `image.registry` | 镜像仓库地址；为空时直接使用 `image.repository` |
| `image.repository` | 镜像仓库名，例如 `mtx/control-plane` |
| `image.tag` | 镜像 tag |
| `image.pullPolicy` | 拉取策略，默认 `Always` |
| `imagePullSecrets` | 拉取私有镜像的 Secret 列表，每项为 `{name: <secret>}` |
| `resources` | 容器 resources |
| `nodeSelector` | Pod 调度 |
| `tolerations` | Pod 容忍 |
| `affinity` | Pod 亲和性 |
| `podAnnotations` | Pod template annotations |
| `terminationGracePeriodSeconds` | 优雅退出时间 |
| `podSecurityContext` / `securityContext` | 安全上下文；control-plane 不设置，其他 chart 使用默认值 |

### control-plane

| key | 说明 |
| --- | --- |
| `config` | 结构化控制面配置，chart 渲染为 ConfigMap 的 `local.toml`；包含 `env`、`http`、`security`、`integration_execution`、`data.db.user`、`storage.s3`、`code_overview`、`asset_import` |
| `service.type` | Service 类型，默认 `ClusterIP` |
| `service.port` | Service 端口，默认 `9000` |
| `migration.enabled` | 是否在 pre-install/pre-upgrade 执行迁移 |
| `migration.backoffLimit` | 迁移 Job 重试次数 |
| `migration.activeDeadlineSeconds` | 迁移 Job 超时 |
| `migration.resources` | 迁移 Job 的 resources |
| `skillsSync.enabled` | 是否在 post-install/post-upgrade 同步内置默认技能；`config.storage.s3.enabled=false` 时也会跳过 |
| `skillsSync.backoffLimit` | 技能同步 Job 重试次数 |
| `skillsSync.activeDeadlineSeconds` | 技能同步 Job 超时 |
| `skillsSync.resources` | 技能同步 Job 的 resources |

默认技能随控制面镜像内置在 `/app/default-skills`（数量以 `apps/control-plane/default-skills/` 目录为准）。`skillsSync` Job 在迁移完成后把它们发布到 S3 和数据库；同步按内容签名跳过未变化的技能，重复升级不会产生新的 S3 批次。更新技能时修改 `apps/control-plane/default-skills/`，重建控制面镜像后 `helm upgrade`。

### studio

| key | 说明 |
| --- | --- |
| `config.apiUpstream` | nginx 反向代理的控制面地址，默认 `http://control-plane:9000` |
| `service.type` | Service 类型，默认 `NodePort` |
| `service.port` | Service 端口，默认 `80` |
| `service.nodePort` | NodePort，默认 `30080` |

### ai-worker

| key | 说明 |
| --- | --- |
| `config` | 结构化 ai-worker 配置，chart 渲染为 ConfigMap 的 `worker.toml`；包含 `worker`、`platform`、`agent`、`code_risk_analysis`、`repository_profile`、`ui_generation`、`logging` |
| `healthPort` | 健康检查端口，默认 `8080` |
| `persistence.runtimeSize` | `/data/runtime` PVC 容量 |
| `persistence.logsSize` | `/app/logs` PVC 容量 |
| `persistence.storageClass` | PVC StorageClass；为空使用集群默认 |

### api-ui-worker

| key | 说明 |
| --- | --- |
| `config` | 结构化 api-ui-worker 配置，chart 渲染为 ConfigMap 的 `config.toml`；包含 `mode`、`control_plane`、`notifications`、`worker`、`ui`、`once` |
| `healthPort` | 健康检查端口，默认 `8080` |
| `artifactsSizeLimit` | `/app/artifacts` emptyDir 上限 |
| `shmSizeLimit` | `/dev/shm` 内存 emptyDir 上限，默认 `1Gi` |

### integration-worker

| key | 说明 |
| --- | --- |
| `config` | 结构化 integration-worker 配置，chart 渲染为 ConfigMap 的 `local.toml`；包含 `control_plane`、`worker` |
| `persistence.runtimeSize` | `/app/runtime` PVC 容量 |
| `persistence.storageClass` | PVC StorageClass；为空使用集群默认 |

## 准备配置

Docker Compose 仍然使用 `manage.py` 生成的 TOML：

```sh
python3 scripts/manage.py configure --mode docker
```

生成的 `.runtime/docker/<service>.toml` 已经使用容器内路径、`env = "production"` 和 `[http].host = "0.0.0.0"`。

所有 K8s chart 都已改为结构化 `config`，**不再读取** `.runtime/docker/*.toml`；这些文件只服务 Docker Compose。K8s 部署时直接填写各服务的 `config`，结构与对应 TOML 一一对应。

control-plane 需要确认：

1. 把 `config.data.db.user.dsn` 改成 K8s 可访问的 MySQL 地址。
2. 把 `config.test_run_notifications.redis_url` 改成 K8s 可访问的 Redis 地址；Redis 为空时实时功能降级。
3. 把 `config.storage.s3` 的 endpoint、bucket、access_key、secret_key 改成实际值；endpoint 必须同时被浏览器和 Worker 访问到。
4. 确认 `config.security.jwt.key`、`config.security.integration.key`、`config.security.worker.key`、`config.security.integration_worker.key` 在各副本/各服务间一致。
5. 确认 `config.security.super_admin.username`、`email` 已填写；首次启动会 seed 超级管理员。
6. 确认 `config.http.host = "0.0.0.0"`；本地生成配置的 `127.0.0.1` 会导致探针和 Studio 代理无法访问。

Worker 需要额外确认：

- ai-worker：`config.platform.worker_token` 与控制面 `security.worker.key` 一致；`config.agent.backend` 与 `ai_worker.agent.backend` 一致（默认 `nanobot`）；路径使用 `/data/runtime` 和 `/app/logs`。
- api-ui-worker：`config.control_plane.worker_token` 与控制面一致；`config.notifications.redis_url` 在集群内可达；`config.ui.artifacts_dir` 为 `/app/artifacts`。
- integration-worker：`config.control_plane.worker_token` 与控制面 `security.integration_worker.key` 一致；`config.worker.health_file` / `evidence_file` 位于 `/app/runtime`。

然后为每个 chart 准备独立的 values 文件：

```sh
mkdir -p .runtime/k8s
cp deploy/helm/charts/control-plane/values.yaml .runtime/k8s/control-plane-values.yaml
cp deploy/helm/charts/studio/values.yaml .runtime/k8s/studio-values.yaml
cp deploy/helm/charts/ai-worker/values.yaml .runtime/k8s/ai-worker-values.yaml
cp deploy/helm/charts/api-ui-worker/values.yaml .runtime/k8s/api-ui-worker-values.yaml
cp deploy/helm/charts/integration-worker/values.yaml .runtime/k8s/integration-worker-values.yaml
```

每个 values 文件至少填：

```yaml
image:
  registry: registry.example.com
  tag: "2026-11-10"

imagePullSecrets:
  - name: mtx-registry
```

各服务都在 `config` 下填结构化配置，结构与对应 TOML 一一对应。

填写完成后运行一致性检查（strict 模式，缺少关键字段会失败）：

```sh
python3 scripts/check_k8s_config.py \
  --platform-config config/platform.toml \
  --values-dir .runtime/k8s
```

脚本只输出字段名和 empty/placeholder/differs 状态，不打印密钥、DSN 或 token 原值。

注意：

- `config` 会以明文写入 ConfigMap。DB 密码、JWT 密钥、S3 `secret_key`、Worker token 因此也会以明文出现在 `kubectl get configmap` 和 etcd 中；生产环境请开启 etcd encryption at rest 并收紧 ConfigMap 的 RBAC，或改回 Secret。
- `control-plane.config` 渲染出的 TOML 同时被控制面 Deployment 和 migrate Job 使用；migrate Job 只需要数据库 DSN，但复用完整配置可以保证一致。
- ai-worker 的 `config` 渲染出的 TOML 挂到 `/app/config/worker.toml`；镜像内的其他 config 文件不会被覆盖。
- api-ui-worker 的 `config` 渲染出的 TOML 挂到 `/app/config.toml`。
- integration-worker 的 `config` 渲染出的 TOML 挂到 `/app/config/local.toml`，`APP_CONF` 与 `--config` 都指向它。
- 这些 ConfigMap 使用 `subPath` 挂载；修改 values 后 `checksum/config` 会触发对应 Deployment/StatefulSet 滚动更新。

## 环境与 values 覆盖

仓库只提供 chart 默认 values 和以下覆盖示例，不提交任何真实生产 values 或秘密。开发与生产的建议差异：

| 维度 | dev | prod |
| --- | --- | --- |
| namespace | `mtx-dev` | 独立生产 namespace（示例 `mtx-prod`），由发布记录固定 |
| values 文件 | `.runtime/k8s/<service>-values.yaml`，从仓库默认值复制 | 仓库外受控目录，由部署流水线从外部配置/秘密管理器生成 |
| 镜像 | 本地或 CI tag，`pullPolicy: Always` | 与发布版本一致的 tag + digest，`pullPolicy: IfNotPresent` |
| 副本 | control-plane 2；Worker 和 Studio 1 | control-plane ≥ 3；无状态 Worker 按队列扩容；integration-worker 保持 1 |
| 资源 | 可留空 | 每个服务显式 requests/limits，并配置调度和 PDB |
| MySQL | 内置或共享测试库 | 外部高可用 MySQL，独立应用账号，连接池按副本计算 |
| Redis | 内置或共享测试实例 | 外部 Redis（`redis.url`），启用认证/TLS 和隔离网络 |
| S3 | 测试桶/前缀 | 生产桶/独立前缀，最小权限、CORS 和备份策略 |
| 集成执行 | `enabled: false` 或单项目灰度 | 仅白名单 `project_ids` 启用，使用独立令牌和 `runtime_generation` |
| 暴露 | NodePort + HTTP | Ingress/内部负载均衡 + TLS；chart 本身不含 Ingress |
| 备份/演练 | 可选 | 每日及变更前备份，至少季度恢复演练 |

生产覆盖示例（仅展示覆盖形式，DSN、密钥、令牌和 S3 凭据由流水线注入，不能写入本文件）：

```yaml
# control-plane 生产覆盖示例
replicaCount: 3
image:
  registry: registry.example.com
  tag: "2026.11.0"
  pullPolicy: IfNotPresent
resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: "2"
    memory: 2Gi
config:
  data:
    db:
      user:
        pool_size: 40
        max_overflow: 20
  integration_execution:
    enabled: true
    project_ids: [123]
    runtime_generation: "<由流水线注入>"
```

Worker 覆盖示例：

```yaml
# ai-worker 生产覆盖示例
replicaCount: 2
image:
  registry: registry.example.com
  tag: "2026.11.0"
  pullPolicy: IfNotPresent
config:
  platform:
    worker_token: "<由流水线注入>"
```

## 秘密处理

- 真实 DSN、JWT/integration key、Worker 令牌、S3 凭据和初始管理员口令只由外部秘密管理器或 CI 在部署时注入；不要写入仓库、命令历史或发布记录。
- `imagePullSecrets` 使用预先创建的 Kubernetes Secret；生产 values 只引用 Secret 名称。
- 当前 chart 把 `config` 渲染为 ConfigMap，秘密会出现在 ConfigMap 中。生产必须开启 etcd encryption at rest、限制 ConfigMap/Pod 的 RBAC，并在发布记录中注明该限制；后续若改为 Secret 引用，按配置变更流程更新本文件和 chart。
- 发布前按[发布检查清单](release-checklist.md)确认 values 来源、权限、备份和回滚材料。

## 安装

每个 chart 独立安装。建议先安装 control-plane，再安装 Studio 和 Worker。以下命令以 `mtx-dev` 和 `.runtime/k8s/` 为例；生产执行时替换为发布记录中的 namespace、仓库外 values 路径和镜像 digest。

```sh
kubectl create namespace mtx-dev

helm upgrade --install control-plane deploy/helm/charts/control-plane \
  -n mtx-dev \
  -f .runtime/k8s/control-plane-values.yaml

helm upgrade --install studio deploy/helm/charts/studio \
  -n mtx-dev \
  -f .runtime/k8s/studio-values.yaml

helm upgrade --install ai-worker deploy/helm/charts/ai-worker \
  -n mtx-dev \
  -f .runtime/k8s/ai-worker-values.yaml

helm upgrade --install api-ui-worker deploy/helm/charts/api-ui-worker \
  -n mtx-dev \
  -f .runtime/k8s/api-ui-worker-values.yaml

helm upgrade --install integration-worker deploy/helm/charts/integration-worker \
  -n mtx-dev \
  -f .runtime/k8s/integration-worker-values.yaml
```

各 chart 没有相互依赖，可以单独安装、单独升级、单独卸载。worker 和 Studio 在 control-plane Ready 之后再启动即可。

control-plane chart 内部的安装顺序由 Helm hook 保证：

1. `control-plane-migrate-config` ConfigMap（pre-install/pre-upgrade）
2. `control-plane-migrate` Job 执行 `alembic upgrade head`
3. 控制面 Deployment/Service

如果迁移失败，control-plane release 失败，控制面不会启动。查看：

```sh
kubectl get job -n mtx-dev
kubectl logs -n mtx-dev job/control-plane-migrate
```

## 访问

```sh
kubectl get service studio -n mtx-dev
```

默认 NodePort：

```text
http://<node-ip>:30080
```

control-plane 只创建 ClusterIP Service，不对外暴露；Studio 通过 `API_UPSTREAM=http://control-plane:9000` 反向代理 `/v1/`。

## 探针

| 服务 | 探针 | 说明 |
| --- | --- | --- |
| control-plane | 无 | chart 不配置探针，避免 kubelet 持续轮询 `/v1/health` 刷日志；端点仍保留，可手工探测 |
| studio | `GET /healthz` | nginx 静态健康响应 |
| ai-worker | `GET /healthz:8080` | 进程级健康；端口由 `TESTING_AGENT_HEALTH_PORT` 控制，未设置时不启动（本地开发） |
| api-ui-worker | `GET /healthz:8080` | 进程级健康；端口由 `TEST_WORKER_HEALTH_PORT` 控制，未设置时不启动（本地开发） |
| integration-worker | exec `--healthcheck` | 读取 `/app/runtime/health.json`，检查进程和进度年龄 |

## 存储

| 服务 | 路径 | 类型 |
| --- | --- | --- |
| ai-worker | `/data/runtime` | StatefulSet `volumeClaimTemplates`，每副本 RWO PVC |
| ai-worker | `/app/logs` | StatefulSet `volumeClaimTemplates`，每副本 RWO PVC |
| api-ui-worker | `/app/artifacts` | emptyDir + `sizeLimit` |
| api-ui-worker | `/dev/shm` | emptyDir，`medium: Memory`，默认 1Gi |
| integration-worker | `/app/runtime` | 单块 RWO PVC，Deployment `strategy: Recreate` |
| control-plane | `/tmp` | emptyDir |
| 所有服务 | 配置 | ConfigMap `subPath` 只读挂载；Studio 使用 ConfigMap 注入 `API_UPSTREAM` |

PVC 的 `storageClassName` 为空时使用集群默认 StorageClass。

## 安全上下文

- control-plane：chart 不设置 `podSecurityContext` / `securityContext`；镜像自身以 UID 10001 非 root 运行。ConfigMap 以 `0444` 挂载，保证非 root 进程能读取配置文件；不挂载 ServiceAccount token。
- ai-worker、integration-worker：UID 10001、`runAsNonRoot`、drop ALL、`seccompProfile: RuntimeDefault`、`readOnlyRootFilesystem: true`、不挂载 ServiceAccount token。
- api-ui-worker：Playwright 官方镜像默认 root；`runAsUser: 0`、`allowPrivilegeEscalation: false`、`seccompProfile: RuntimeDefault`。如果 Chromium 在 `RuntimeDefault` 下无法启动，只对该 Pod 把 `securityContext.seccompProfile.type` 改为 `Unconfined`，不要全局放开。
- studio：官方 nginx 镜像默认 root；不启用 PSA/NetworkPolicy，仅保证无 privileged/hostPath。
- 首期不启用 PSA 和 NetworkPolicy；生产收紧时再按 namespace 标签和 CNI 能力补齐。

## 升级和回滚

发布前按[发布检查清单](release-checklist.md)核对测试、镜像 digest、数据库 baseline、技能同步和备份。每个 chart 独立升级：

```sh
helm upgrade control-plane deploy/helm/charts/control-plane \
  -n mtx-dev \
  -f .runtime/k8s/control-plane-values.yaml

helm upgrade ai-worker deploy/helm/charts/ai-worker \
  -n mtx-dev \
  -f .runtime/k8s/ai-worker-values.yaml
```

回滚单个 release：

```sh
helm rollback control-plane <revision> -n mtx-dev
```

- control-plane chart 在升级前执行迁移 hook，升级后执行默认技能同步 hook（`skillsSync`）；技能同步失败会使本次 upgrade 报错，修复后重新 upgrade 即可重试。
- 配置 ConfigMap 变化会通过 `checksum/config` 触发对应工作负载滚动。
- 数据库迁移是向前的；回滚应用镜像前先确认 schema 兼容性，必要时从备份恢复数据库。
- `helm rollback` 不会自动回滚数据库。

## 已知限制

- control-plane `/v1/health` 不检查 MySQL；数据库故障时 Pod 仍 Ready。
- ai-worker 收到 SIGTERM 会立即退出，滚动更新会中断在途任务；依赖控制面租约/重试。
- ai-worker `/data/runtime/workspaces` 只在启动时清扫过期失败工作区；运行期间无定期清理，PVC 会随异常任务累积；后续可加 CronJob。
- Studio 和 api-ui-worker 以 root 运行；首期无 PSA/NetworkPolicy。
- 无 Ingress/TLS；Studio 通过 NodePort 暴露。
- 无 Prometheus/Loki 接入；日志走 stdout，ai-worker 本地日志在 PVC。
- S3 endpoint 必须浏览器可达，否则预签名上传/下载失败。
- 各 chart 的 values 由用户分别维护；关键字段必须与 `config/platform.toml` 一致，部署前运行 `python3 scripts/check_k8s_config.py --platform-config config/platform.toml --values-dir .runtime/k8s`，清单和例外见[配置事实源与一致性策略](#配置事实源与一致性策略)。

## 排障

**Pod 起不来，日志提示配置缺失**

检查对应 ConfigMap 是否存在、各服务的 `config` 是否为空、`subPath` 路径是否匹配。

**控制面 CrashLoopBackOff**

先确认 migrate Job 成功、`alembic_version` 正确、`security.super_admin.username/email` 已填写；控制面启动时会 seed 超级管理员。

**Studio 502**

检查 `studio` ConfigMap 的 `API_UPSTREAM` 是否为 `http://control-plane:9000`，以及 control-plane Service/Endpoints 是否正常。

**Playwright 启动失败**

先确认 `/dev/shm` 已挂 1Gi；再检查 seccomp。只对 api-ui-worker 单独放宽，不要影响其他服务。

**PVC Pending**

检查 `persistence.storageClass` 是否存在、是否支持 RWO；ai-worker 每个副本会各创建 runtime/logs 两块 PVC。
