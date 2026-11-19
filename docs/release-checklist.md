# 发布检查清单

- 状态：现行
- 负责人：release owner
- 最近复核：2026-11-19
- 复核周期：每季度
- 适用范围：Compose 与 Kubernetes 的平台发布、升级和回滚
- 变更/废弃：按[规范变更检查清单](agents/domain.md#规范变更检查清单)执行。

本清单用于内部部署和对外发布。命令以[验证命令矩阵](commands.md)为唯一来源，本文件只规定发布门禁、记录内容和回滚责任，不复制完整命令。

## 版本与 tag 策略

- 内部部署使用日历版本 `YYYY.MM.PATCH`，例如 `2026.11.0`；同月修复递增 `PATCH`。
- 对外发布使用 SemVer `MAJOR.MINOR.PATCH`；对外发布时再建立与内部日期的映射记录。
- Git tag 使用 annotated tag `v<版本>`（如 `v2026.11.0`），指向实际构建镜像的提交；tag 创建后不移动、不覆盖。
- 镜像 tag 与发布版本一致；部署记录必须同时保存镜像 digest。禁止用 `latest` 或重新推送同名 tag 代替新版本。
- 各应用 `pyproject.toml` / `package.json` 的包版本是构建元数据，不作为平台发布标识；对外发布需要独立版本号时再统一调整。
- `CHANGELOG.md` 按版本记录变更；发布提交只把 `Unreleased` 内容移入新版本小节，不补写未发生的发布。

## 发布前门禁

| 门禁 | 必须完成 | 记录 |
| --- | --- | --- |
| 版本与范围 | 确定版本号、目标环境、包含的工单/变更和明确排除项 | 发布记录 |
| 代码与测试 | 按[验证命令矩阵](commands.md#按变更选择入口)执行受影响项目和根目录检查；跨项目协议同时验证生产方和消费方 | 实际命令、通过/失败/跳过数量 |
| 文档 | 运行 `python3 scripts/check_docs.py`；新增 ADR 或规范变更已完成复核 | 结果 |
| 锁文件与镜像 | `scripts/build_images.sh` 通过；记录六个镜像的 ID 和 registry digest | 构建日志、digest 清单 |
| 配置 | 使用 `config/platform.example.toml` 核对新增字段；本地 `config/platform.toml` 不提交；外部 MySQL/Redis 使用对应 overlay | 配置差异摘要 |
| K8s values | 填写目标 namespace 和镜像 digest 后运行 strict 配置一致性检查 | 检查退出码 |
| 数据库 | 确认只有唯一 baseline `20261103_0001_v1_baseline` 或已按发布策略新增 revision；空库 `alembic upgrade head` 可完成 | `alembic current` / `heads` 输出 |
| 备份 | 迁移数据库、修改桶/前缀或扩大回收范围前完成联合备份并 verify | 快照路径、verify 结果 |
| 技能 | 确认 `apps/control-plane/default-skills/` 已进入镜像；K8s `skillsSync` 成功，或 Compose 已执行技能同步 | 技能数量/签名、同步日志 |
| 外部系统 | 真实 MySQL、S3、禅道 MCP、浏览器、LLM、k6 等按变更范围完成目标环境验收 | 环境、命令、结果、未覆盖范围 |

没有完成或明确跳过的门禁必须写入发布记录，不能以“本地 fixture 通过”代替外部验收。

## 部署顺序

1. 完成备份和配置核对，冻结发布窗口内的写入和大规模导入。
2. 先部署控制面和迁移；确认 `/v1/health`、登录、数据库连接和启动日志正常。
3. 再部署 Worker（ai / api-ui / integration / perf）和 Studio；确认健康检查、领取和实时通知。
4. Kubernetes 按 chart 独立升级，参照[升级和回滚](deployment-k8s.md#升级和回滚)；control-plane 的迁移和技能同步 hook 必须先成功。
5. 执行发布后冒烟：登录、项目列表、一次只读查询、实时通知；涉及集成写入时只做 noop 或显式授权的测试项目。

## 发布记录模板

```markdown
### 发布记录

- 版本 / Git tag：
- 提交：
- 目标环境 / namespace：
- 镜像与 digest：
- 数据库 baseline / heads：
- 备份快照与 verify：
- 配置与 values：
- 技能同步：
- 测试与检查结果：
- 外部验收：
- 未验证范围及原因：
- 回滚版本与回滚负责人：
```

## 回滚

1. 先停止新任务和大规模写入，保留日志、结果和证据；不要删除数据库或对象存储中的恢复材料。
2. 应用回滚优先使用上一版本镜像 digest 和配置快照。Compose 固定镜像 digest；Kubernetes 使用 `helm rollback <release> <revision>`。
3. `helm rollback` 不会回滚数据库迁移、技能同步或对象存储内容。确认旧应用与当前 schema、已同步技能兼容；不兼容时按[存储运维](control-plane/storage-operations.md)从已验证备份恢复到独立数据库/桶，再切换流量。
4. 集成 Worker 回滚前先暂停提交/领取，等待结果和 evidence 排空；存在未决写入时使用兼容控制面核对，不重放旧任务。
5. 回滚后重新执行健康、登录、领取和一次只读/冒烟验证，并记录实际回滚到的镜像 digest。

## 备份责任

- 部署环境 owner 负责备份调度、异机复制、保留清单和恢复演练组织；应用 maintainer 负责提供维护窗口、恢复验收和业务数据核对。
- 每日执行一次完整联合备份；迁移数据库、修改桶/前缀或扩大回收范围前额外备份。至少保留最近 7 个每日、4 个每周、3 个每月快照。
- 至少每季度执行一次隔离恢复演练，并在首次生产发布前完成一次；演练覆盖 MySQL、S3 对象、文件引用、技能和集成隔离门控。具体命令和验收项见[存储运维](control-plane/storage-operations.md)。

仓库提供备份/恢复 CLI，但不创建定时任务；在上述责任和频率落地前，发布记录不得把备份门禁标为完成。
