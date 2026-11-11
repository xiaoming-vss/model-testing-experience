# 仓库画像分析

仓库画像是需求分析阶段旁的**人工运行**辅助任务，不属于生成链阶段。每次成功运行形成一个不可变画像版本（失败/运行中不占版本号），本期在生成全景中作为需求分析分组内第二行右对齐的仓库画像卡片展示，尺寸、状态样式和运行态动画与其他阶段卡片一致：单击进入阶段侧栏查看画像版本和上游追溯，双击进入画布内阅读区；进入阅读区后运行或重新生成位于侧栏，主阅读区只展示画像内容；结果不传给功能、API、代码风险或测试单图谱。UI 生成只消费画像中的仓库角色、分支和 HEAD commit 作为源码仓库选择依据，画像正文不进入 UI prompt，详见下文“UI 生成消费方式”。

## 输入

- 用户选择的已审核 `feature_understanding` 版本；
- 该需求全部激活的代码仓库绑定；
- 每个仓库工作分支的 HEAD commit。

控制面建 run 时冻结需求理解正文、版本引用、仓库 `cloneUrl`/`headCommit`/`connectionId`。单仓库解析失败写入 `profileError`，其余仓库继续；没有仓库绑定时拒绝运行。

## UI 生成消费方式

- UI 生成读取成功画像版本中的仓库角色和冻结 `headCommit`，用户确认一个 `frontend/fullstack` 仓库后，控制面把仓库 pin 复制进 `ui_surface` 首阶段快照，不引用画像运行记录。
- `profile` commit 模式使用画像冻结的 `headCommit`；`latest` 模式在启动时解析分支最新 HEAD 并冻结为具体 SHA。
- Worker 通过 `gitlabCredentialsUrl` 获取**本次 UI 发起人**的个人 GitLab 凭据，只 clone 这一个仓库的冻结 commit，整个仓库作为三阶段共用的源码根；检出后删除 `.git`，不把 token 写入 remote URL、`.git/config`、日志或 prompt。
- 仓库 checkout 使用 `[ui_generation]` 的 `git_timeout_seconds`、`workspace_retention_hours`、`max_repo_size_mb` 和 `max_repo_files`；成功后清理工作区，失败保留诊断窗口。
- 画像的职责摘要、技术栈、证据和整体总结只用于选择仓库和来源追溯，不注入 UI 生成 prompt。

UI 生成只使用仓库 pin；历史 ZIP 来源的归档下载路径已随旧数据清理删除。

## 工作区

- `tasks/git_workspace.py` 提供共享 Git 原语：askpass 临时凭据、认证 clone URL、fetch/checkout、失败保留和过期清扫。
- 仓库画像只 clone 工作分支 HEAD，不解析基线、不生成 diff。
- 每次 attempt 使用 `runs/<attemptId>/code/`，单仓库失败删除半成品并记为不可分析。
- 成功删除工作区；失败保留 `repository_profile.workspace_retention_hours`（默认 24 小时）。
- token 只通过临时 askpass 环境变量传入，不写 remote URL、`.git/config`、日志或 prompt。

## 模型调用

- 本期只支持 Pi；使用 `read/grep/find/ls` 只读工具。
- 使用 `repository-profile-analysis` 默认 skill；Worker 通过 `prompt_builder` 注入技能规则，并对模型输出执行三次有界校验修正。
- 上下文包含需求理解正文、可分析仓库 manifest、顶层目录/文件清单，以及不可分析仓库原因。
- 模型必须只返回一个 JSON 对象，不含 Markdown fence、解释或额外元数据。

## 输出契约

```json
{
  "repositories": [
    {
      "repositoryId": "repo-1",
      "pathWithNamespace": "team/order-service",
      "role": "backend",
      "responsibilitySummary": "提供订单创建与查询接口",
      "techStack": ["Java", "Spring Boot"],
      "keyPaths": ["src/main/java"],
      "confidence": 0.86,
      "evidence": ["pom.xml", "controller/"]
    }
  ],
  "overallSummary": "当前需求主要涉及后端订单服务"
}
```

校验规则：

- 顶层只允许 `repositories`、`overallSummary`；仓库条目只允许上述 8 个字段。
- `role` 只能是 `frontend/backend/fullstack/infra/test/unknown`。
- `responsibilitySummary` ≤120 字，`overallSummary` ≤200 字；`techStack`/`keyPaths`/`evidence` 各最多 5 项。
- `confidence` 为 0–1；非 `unknown` 至少 1 条 evidence；`unknown` 时 confidence=0、evidence=[]。
- `keyPaths` 必须是仓库内存在的相对路径。
- 每个可分析仓库恰好一条；Worker 按原始绑定顺序补齐不可分析仓库的 `unknown` 条目。
- 模型 JSON 契约非法时整次失败；单仓库读取失败才降级为 `unknown`。

## 配置

`[repository_profile]`：

- `git_timeout_seconds`
- `workspace_retention_hours`
- `max_repos`
- `max_output_chars`

## 测试

```sh
cd apps/ai-worker
uv run --locked --group dev python -m unittest discover -s tests/unit/tasks/repository_profile -t . -v
uv run --locked --group dev python -m unittest discover -s tests -v
```
