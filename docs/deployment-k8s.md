# Kubernetes 部署

平台采用 **chart-per-service**：每个服务一个独立 Helm chart，独立安装、独立升级、独立 values。仓库不再提供 umbrella chart；服务之间通过 K8s Service 名称通信。

- `deploy/helm/charts/<service>/`：每个服务的完整 chart，包含工作负载、Service、ConfigMap、PVC 等资源，以及该 chart 自己的 `values.yaml`。
- 每个 chart 都可以单独 `helm install`，不依赖其他 chart 的发布。
- 当前只覆盖平台本身，不包含 CI Worker。

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

每个 chart 的 `values.yaml` 就是该服务唯一的部署 values。不存在全局 values 文件；需要多服务共享的配置（例如镜像仓库、Worker token、DB 地址）要在各自的 values 或生成的 TOML 中保持一致。

原 umbrella 的 `values.yaml` 不能直接给单个 chart 使用：单个 chart 只认自己顶层的 key。迁移时把原 `control-plane:`、`studio:` 等 section 的内容分别拆成对应 chart 的 values 文件；所有服务的 `configToml` 都已改成结构化 `config`，studio 的 `apiUpstream` 改成 `config.apiUpstream`。

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

默认技能随控制面镜像内置在 `/app/default-skills`（16 个系统技能）。`skillsSync` Job 在迁移完成后把它们发布到 S3 和数据库；同步按内容签名跳过未变化的技能，重复升级不会产生新的 S3 批次。更新技能时修改 `apps/control-plane/default-skills/`，重建控制面镜像后 `helm upgrade`。

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
6. 确认 `config.http.host = "0.0.0.0"`；使用 `config/local.example.toml` 的 `127.0.0.1` 会导致探针和 Studio 代理无法访问。

Worker 需要额外确认：

- ai-worker：`config.platform.worker_token` 与控制面 `security.worker.key` 一致；`config.agent.backend` 为 `pi` 或 `nanobot`；路径使用 `/data/runtime` 和 `/app/logs`。
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

注意：

- `config` 会以明文写入 ConfigMap。DB 密码、JWT 密钥、S3 `secret_key`、Worker token 因此也会以明文出现在 `kubectl get configmap` 和 etcd 中；生产环境请开启 etcd encryption at rest 并收紧 ConfigMap 的 RBAC，或改回 Secret。
- `control-plane.config` 渲染出的 TOML 同时被控制面 Deployment 和 migrate Job 使用；migrate Job 只需要数据库 DSN，但复用完整配置可以保证一致。
- ai-worker 的 `config` 渲染出的 TOML 挂到 `/app/config/worker.toml`；镜像内的其他 config 文件不会被覆盖。
- api-ui-worker 的 `config` 渲染出的 TOML 挂到 `/app/config.toml`。
- integration-worker 的 `config` 渲染出的 TOML 挂到 `/app/config/local.toml`，`APP_CONF` 与 `--config` 都指向它。
- 这些 ConfigMap 使用 `subPath` 挂载；修改 values 后 `checksum/config` 会触发对应 Deployment/StatefulSet 滚动更新。

## 安装

每个 chart 独立安装。建议先安装 control-plane，再安装 Studio 和 Worker：

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

每个 chart 独立升级：

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
- 各 chart 的 values 由用户分别维护，与 `config/platform.toml` 的一致性由用户保证；后续可加生成器。

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
