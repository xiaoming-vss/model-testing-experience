# Kubernetes 部署

平台提供 GitLab 风格的 **chart-per-service + umbrella** 部署：

- `deploy/helm/charts/<service>/`：每个服务一个独立 chart，自己包含工作负载（Deployment/StatefulSet）及所需资源（Service、ConfigMap、Secret、PVC、PDB 按需）。
- `deploy/helm/mtx/`：umbrella chart，只负责依赖和全局 values；一次 `helm install` 部署全部服务。
- 每个 chart 也可以单独安装，用于调试。

当前只覆盖平台本身，不包含 CI Worker。

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

```
deploy/helm/
  charts/
    control-plane/
    studio/
    ai-worker/
    api-ui-worker/
    integration-worker/
  mtx/
    Chart.yaml
    values.yaml
    NOTES.txt
```

`deploy/helm/mtx/Chart.yaml` 通过 `file://../charts/<service>` 引用五个 subchart。`helm dependency build` 会把它们复制到 `deploy/helm/mtx/charts/`，该目录已加入 `.gitignore`。

## Values 的 key

`deploy/helm/mtx/values.yaml` 定义 key 和安全默认值。实际部署时复制一份 values 文件并把值填进去；**不要提交包含真实密钥的 values 文件**。

```yaml
global:
  imageRegistry: "registry.example.com"
  imageTag: "2026-11-06"
  imagePullSecrets:
    - name: mtx-registry

namespace: "mtx-dev"

control-plane:
  replicaCount: 2
  configToml: |
    # 完整 local.toml

studio:
  replicaCount: 1
  apiUpstream: "http://control-plane:9000"
  service:
    type: NodePort
    port: 80
    nodePort: 30080

ai-worker:
  replicaCount: 1
  configToml: |
    # 完整 worker.toml
  persistence:
    runtimeSize: 20Gi
    logsSize: 10Gi
    storageClass: ""

api-ui-worker:
  replicaCount: 1
  configToml: |
    # 完整 config.toml
  artifactsSizeLimit: 5Gi
  shmSizeLimit: 1Gi

integration-worker:
  replicaCount: 1
  configToml: |
    # 完整 local.toml
  persistence:
    runtimeSize: 5Gi
    storageClass: ""
```

### key 说明

| key | 说明 |
| --- | --- |
| `global.imageRegistry` | 镜像仓库地址，与 chart 内的 `mtx/<service>` 仓库名拼接；例如填 `registry.example.com` 得到 `registry.example.com/mtx/control-plane`。为空时直接使用 `mtx/<service>` |
| `global.imageTag` | 镜像 tag |
| `global.imagePullSecrets` | 拉取私有镜像的 Secret 引用列表，每项为 `{name: <secret>}` |
| `namespace` | 仅用于提示/生成安装命令；实际 namespace 由 `helm -n` 决定，两者必须一致 |
| `control-plane.replicaCount` | 控制面副本数，默认 2 |
| `control-plane.configToml` | 完整 control-plane TOML，包含 JWT、Worker token、DB DSN、S3 密钥等 |
| `studio.apiUpstream` | Studio nginx 反向代理的控制面地址 |
| `studio.service.nodePort` | Studio NodePort |
| `ai-worker.configToml` | 完整 ai-worker TOML |
| `ai-worker.persistence.*` | `/data/runtime`、`/app/logs` 的 PVC 容量和 storageClass |
| `api-ui-worker.configToml` | 完整 api-ui-worker TOML |
| `api-ui-worker.artifactsSizeLimit` | `/app/artifacts` emptyDir 上限 |
| `api-ui-worker.shmSizeLimit` | `/dev/shm` 内存 emptyDir 上限，默认 1Gi |
| `integration-worker.configToml` | 完整 integration-worker TOML |
| `integration-worker.persistence.*` | `/app/runtime` 的 PVC 容量和 storageClass |

所有 subchart 还支持 `resources`、`nodeSelector`、`tolerations`、`affinity`、`podAnnotations`。

## 准备配置

每个服务只读**一个完整 TOML**。推荐先运行 `python3 scripts/manage.py configure --mode docker`，以生成的 `.runtime/docker/<service>.toml` 为基础（已使用容器内路径、`env = "production"` 和 `[http].host = "0.0.0.0"`），再按实际环境填写：

1. 把 `[data.db.user].dsn` 改成 K8s 可访问的 MySQL 地址。
2. 把 `[test_run_notifications].redis_url` 改成 K8s 可访问的 Redis 地址；Redis 为空时实时功能降级。
3. 把 `[storage.s3]` 的 endpoint、bucket、access_key、secret_key 改成实际值；endpoint 必须同时被浏览器和 Worker 访问到。
4. 确认 `security.jwt.key`、`security.integration.key`、`security.worker.key`、`security.integration_worker.key` 在各副本/各服务间一致。
5. 确认 `security.super_admin.username`、`email` 已填写；首次启动会 seed 超级管理员。
6. 确认控制面 `[http].host = "0.0.0.0"`；使用 `config/local.example.toml` 的 `127.0.0.1` 会导致探针和 Studio 代理无法访问。
7. 把 Worker 的上游地址（`platform.base_url` 或对应环境变量）改成控制面 Service 地址，不能保留 `127.0.0.1`。

注意：

- `control-plane.configToml` 同时被控制面 Deployment 和 migrate Job 使用；migrate Job 只需要数据库 DSN，但复用完整 TOML 可以保证配置一致。
- ai-worker 的 `configToml` 挂到 `/app/config/worker.toml`；镜像内的其他 config 文件不会被覆盖。
- api-ui-worker 的 `configToml` 挂到 `/app/config.toml`。
- integration-worker 的 `configToml` 挂到 `/app/config/local.toml`，`APP_CONF` 与 `--config` 都指向它。
- 这些 Secret 使用 `subPath` 挂载；修改 values 后 `checksum/config` 会触发对应 Deployment/StatefulSet 滚动更新。

## 安装

```sh
helm dependency build deploy/helm/mtx
helm upgrade --install mtx deploy/helm/mtx \
  -n mtx-dev \
  --create-namespace \
  -f /path/to/values.yaml
```

`helm dependency build` 只需要在 chart 变更后执行；也可以使用 `--dependency-update`。

安装顺序由 Helm hook 保证：

1. `mtx-control-plane-migrate-config` Secret（pre-install/pre-upgrade）
2. `mtx-control-plane-migrate` Job 执行 `alembic upgrade head`
3. 其他 Deployment/StatefulSet/Service

如果迁移失败，Helm 发布失败，控制面不会启动。查看：

```sh
kubectl get job -n mtx-dev
kubectl logs -n mtx-dev job/mtx-control-plane-migrate
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
| control-plane | `GET /v1/health` | 静态 200，不检查 MySQL；DB 故障时仍 Ready |
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
| 所有服务 | 配置 | Secret `subPath` 只读挂载；Studio 使用 ConfigMap 注入 `API_UPSTREAM` |

PVC 的 `storageClassName` 为空时使用集群默认 StorageClass。

## 安全上下文

- control-plane、ai-worker、integration-worker：UID 10001、`runAsNonRoot`、drop ALL、`seccompProfile: RuntimeDefault`、`readOnlyRootFilesystem: true`、不挂载 ServiceAccount token。
- api-ui-worker：Playwright 官方镜像默认 root；`runAsUser: 0`、`allowPrivilegeEscalation: false`、`seccompProfile: RuntimeDefault`。如果 Chromium 在 `RuntimeDefault` 下无法启动，只对该 Pod 把 `securityContext.seccompProfile.type` 改为 `Unconfined`，不要全局放开。
- studio：官方 nginx 镜像默认 root；不启用 PSA/NetworkPolicy，仅保证无 privileged/hostPath。
- 首期不启用 PSA 和 NetworkPolicy；生产收紧时再按 namespace 标签和 CNI 能力补齐。

## 升级和回滚

```sh
helm upgrade mtx deploy/helm/mtx -n mtx-dev -f /path/to/values.yaml
```

- pre-upgrade hook 会先执行迁移。
- 配置 Secret 变化会通过 `checksum/config` 触发对应工作负载滚动。
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
- values 由用户维护，与 `config/platform.toml` 的一致性由用户保证；后续可加生成器。

## 排障

**Pod 起不来，日志提示配置缺失**

检查对应 Secret 是否存在、`configToml` 是否为空、`subPath` 路径是否匹配。

**控制面 CrashLoopBackOff**

先确认 migrate Job 成功、`alembic_version` 正确、`security.super_admin.username/email` 已填写；控制面启动时会 seed 超级管理员。

**Studio 502**

检查 `studio` ConfigMap 的 `API_UPSTREAM` 是否为 `http://control-plane:9000`，以及 control-plane Service/Endpoints 是否正常。

**Playwright 启动失败**

先确认 `/dev/shm` 已挂 1Gi；再检查 seccomp。只对 api-ui-worker 单独放宽，不要影响其他服务。

**PVC Pending**

检查 `persistence.storageClass` 是否存在、是否支持 RWO；ai-worker 每个副本会各创建 runtime/logs 两块 PVC。
