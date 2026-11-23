# 2026-11-20 整改复核及本地验收

- 日期：2026-11-20
- 状态：验收记录；外部验收待各环境负责人执行
- 负责人：platform maintainers
- 来源：全量整改工单 01–68、本地工作树复核
- 关联：[验证命令矩阵](../commands.md)、[部署说明](../deployment.md)

## 已复核的缺口

- 性能 Worker 数据下载对 429 与全部 500–599 按退避重试；其他 4xx 保持原有快速失败语义。测试包含 501、505 和 599。
- Studio feature 边界使用 TypeScript 语法树识别别名、相对路径、静态导出以及字面量动态导入；存量以来源文件和目标路径为键记录，当前 20 条。无法静态解析的非字面量动态导入在 feature 内直接拒绝。
- Studio bundle 预算补充登录页与默认项目页的懒加载入口及静态依赖；其他页面和进一步动态加载的代码不在这两项预算内。
- 部署文档的 Playwright 命令改为锁定依赖；MySQL 回归夹具按当前产物和事务契约更新；禅道 MCP 容器测试的模块入口可独立运行。
- [EntityCard 浏览器验收](../studio/records/2026-11-20-entity-card-visual-check.md)和[用例可视化历史试跑](../ai-worker/records/2026-11-14-case-visualization-skill-trial.md)有可追溯记录。

## 本地环境与结果

- 根目录 unittest：68 项通过，4 项 opt-in 跳过；Compose 配置、文档检查通过。四类 opt-in 容器验收已另行执行：Integration Worker 隔离 1 项、禅道 MCP 启停 1 项、附件 1 项、Bug 选项 3 项，全部通过；禅道上游使用隔离夹具。
- 六应用镜像本地构建通过；未推送镜像。
- 五个 Helm chart 在容器化 Helm 3.17.3 下 lint 与默认值模板渲染通过，不代表集群部署通过。
- Studio Node 22.23.1：`npm run verify` 通过，198 个测试文件、985 项通过。登录页 JS/CSS gzip 258.6/42.0 KiB，默认项目页 642.3/46.7 KiB。
- API/UI Worker 本地 Chromium 冒烟：执行器完成点击、文本断言、截图与 Trace；目标为临时页面，不代表真实业务站点通过。
- k6 2.3.0 向一次性本地 Prometheus 3.13.5 Remote Write，查询到带 `run_id` 的指标；未验证目标环境监控接入。
- 控制面默认 `apps/control-plane/scripts/check.py`：1735 项通过、128 项因环境等原因跳过、3 个子测试通过；Ruff 和 mypy 通过。另在隔离 MySQL 8.4 实例上运行全部引用 MySQL 测试库的模块，123 项通过；隔离 MySQL 及 RustFS 的 `apps/control-plane/tests/test_storage_live.py` 10 项通过，包含备份恢复和对象哈希核对。测试库及桶为一次性数据，不替代生产恢复演练。
- 工单 11–14 的补充验证：`python3 scripts/manage.py init --help` 成功；源码与配置扫描未发现旧数据库凭据及硬编码关闭 TLS 校验。弱口令字符串扫描仍命中拒绝列表和用于触发 fail-fast 的默认占位值，不能把扫描结果描述成零命中。上述控制面测试覆盖相关本地回归，真实外部连接另行验收。
- AI Worker unittest：541 项通过、5 项跳过。
- 性能 Worker pytest：109 项通过；Ruff、格式和 mypy 通过。API/UI Worker pytest：131 项通过。
- Integration Worker pytest：61 项通过、1 项默认跳过；再以 `MTX_INTEGRATION_LONG_UPLOAD=1` 运行长传输专项，1 项通过，用时 192.96 秒。测试使用隔离上游，不代表真实禅道写入。
- Studio 依赖补充检查：`npm audit --omit=dev --json` 报告 2 项（1 项高、1 项低），高风险涉及间接依赖 `react-router`。这是本次新增发现，尚未评估各公告的适用性，也未调整锁文件。

## 仍需目标环境执行

K8s 部署 values 与实际服务地址一致性、生产或预发布 MySQL/S3 数据和恢复演练、真实禅道/GitLab 写入及恢复、目标浏览器与业务站点、真实 LLM 服务、目标 Prometheus Remote Write、实际旧 Pi 卷名均须在对应环境完成。`.runtime/k8s` 的当前控制面与 API/UI Worker Redis 配置不一致，需部署负责人确认正确地址；本次未覆盖或修改用户配置。
