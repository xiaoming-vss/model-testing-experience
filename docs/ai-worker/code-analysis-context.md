# 代码风险分析工作区与报告

代码风险分析不再只消费 GitLab compare 返回的 diff。控制面在创建 run 时解析并固化每个仓库的 `cloneUrl`、`baseCommit`、`headCommit`，Worker 为本次 run 准备独立代码工作区，模型通过只读工具读取仓库文件。正式的 `code-risk-analysis` skill 已接入本地 Worker：模型输出四个风险分析区块，Worker 负责三次有界校验修正并注入确定性的仓库版本事实。

## 快照与固定版本

- 需求仓库绑定时必须选择基线分支；基线不能与工作分支相同，两个分支都按当前操作人的个人 PAT 校验存在且可访问。
- `CodeRiskAnalysisService.build_snapshot` 不再从历史迭代推断基线。缺少基线、缺少连接或任一仓库的 commit/克隆地址解析失败时，整次 run 创建失败。
- 快照中的每个 binding 包含 `repositoryId`、`instanceUrl`、`pathWithNamespace`、`cloneUrl`、`branch`、`baselineBranch`、`baseCommit`、`headCommit` 与 `connectionId`。
- 凭据接口只下发当前执行人的个人连接 token；token 不进入任务快照。

## 每次 run 的工作区

目录结构：

```text
<task-workspace>/runs/<attemptId>/
  .active                  # 工作区准备中/可清理标记
  code/
    manifest.json          # 仓库、分支、commit、本地路径与变更统计
    repos/<name>-<hash>/   # 每个绑定仓库的 detached checkout
```

- clone 使用 `--filter=blob:none --no-checkout --no-recurse-submodules`，再按工作/基线分支 fetch，失败时回退按 commit SHA fetch；随后 `checkout --detach <headCommit>` 并核对 `HEAD`。
- 每个仓库使用独立的临时 `GIT_ASKPASS`、空 `HOME` 和空全局 gitconfig；token 只出现在子进程环境变量中，不写入 remote URL、`.git/config`、日志或提示词。认证临时目录在准备结束后删除。
- diff 由工作区本地 `git diff` 生成，复用 `diff_prep.py` 的 lockfile/生成物/二进制过滤，并计算 diffstat。
- 成功后删除整个 run 目录；失败时写 `.retain-until` 并保留 `workspace_retention_hours`。Worker 启动及每次准备前清扫已过期目录。

## 上下文与只读工具

固定上下文包含需求理解记录、仓库/commit manifest、按预算裁剪后的 diff、改动文件清单与现有功能/API/UI 用例。改动文件全文不预置，模型在工作区内按需读取。

- Pi 调用参数固定为 `--tools read,grep,find,ls`，不启用 bash、write 或 edit；不加载技能包。
- `max_diff_chars` 是预置 diff 的总字符预算。超出预算时按整文件跳过并记录 `truncatedFiles`，不静默截断。
- `code-risk-analysis` skill 要求模型只输出 `changeOverview`、`risks`、`affectedCases`、`coverageGaps` 四个区块；Worker 校验 YAML/Schema、用例 ID、风险证据路径和仓库事实。
- 输出校验失败时最多追加两次调用，将上一次完整输出和最多 20 条校验问题交回模型；模型服务、凭据、工作区准备和截断错误不进入输出修正。
- 成功结果由 Worker 注入 `analyzedAt` 和固定仓库 manifest，写入 `output_yaml`；校验耗尽时任务失败并保留工作区。

## 配置

`[code_risk_analysis]`：

| 字段 | 默认 | 作用 |
| --- | --- | --- |
| `gitlab_timeout_seconds` | 120 | 兼容旧配置；当前代码拉取使用 `git_timeout_seconds` |
| `git_timeout_seconds` | 300 | 单次 git 命令超时 |
| `workspace_retention_hours` | 24 | 失败工作区保留时长 |
| `max_diff_chars` | 1000000 | 预置 diff 字符预算 |
| `max_repos` | 20 | 单次 run 仓库数上限 |

部署配置通过 `config/platform.toml` 的 `[ai_worker.code_risk_analysis]` 提供，`scripts/manage.py` 合并到生成的 `worker.toml`。

## 已知边界

- 本期只验收 Pi 后端；Nanobot 后端会直接返回“仅支持 Pi”。
- Pi `read` 工具当前允许绝对路径，工作区外读取风险尚未由沙箱封堵；代码目录也未只读挂载，依赖只读工具白名单，不能修改代码或执行命令。
- 大仓库依赖 partial clone 与 diff 预算；`git diff` 完整输出当前先读入内存再由预算裁剪，尚无 git 输出字节上限或流式裁剪。
- 本期未限制 agent 工具调用次数，只有模型运行总时限、空闲超时与 diff 字符预算。
- 多仓库 fail-fast：任一仓库准备失败会阻断整次分析。
- 代码风险分析的正式报告由 `code-risk-analysis` skill 生成；代码工作区、凭据和只读工具边界保持不变。
