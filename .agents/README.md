# .agents

本目录存放随仓库版本化的 Agent 技能（Agent Skills 约定：一个技能一个目录，内含 `SKILL.md`）。

工作区作用域下，ZCode 会扫描 `<仓库根>/.agents/skills/`（`<仓库根>/.zcode/skills/` 是同级的 ZCode 专用位置，但 `.zcode/` 在 `.gitignore` 中，不会随仓库版本化）。`.agents/` 同时是跨工具约定，Claude Code 与 Codex 也能读取。

## skills/

来源：<https://github.com/mattpocock/skills>（MIT）

| 项 | 值 |
| --- | --- |
| 版本 | 1.2.3 |
| 提交 | `74ca5fe077456a0b3b2f5310cf9430999fd0b5fd`（2026-09-17） |
| 安装日期 | 2026-09-18 |
| 内容 | mattpocock 上游 `.claude-plugin/plugin.json` 中 `skills` 数组声明的 25 个已发布技能 |

未包含上游的 `skills/deprecated/`（已退役）、`skills/misc/`（未推广）、`skills/in-progress/`（未发布）。上游自带的 `scripts/link-skills.sh` 也是同样的取舍。

这是**复制**而非符号链接：技能文件属于本仓库，可以直接修改，上游更新不会自动流入。升级方式是从上游取新版本后重新复制对应目录，并重新核对 `SKILL.md` 的 `description` 长度（见下）。

### ponytail（其他来源）

来源：<https://github.com/DietrichGebert/ponytail>（MIT）

| 项 | 值 |
| --- | --- |
| 版本 | 5.3.3 |
| 提交 | `96608e078b2d5ea607c5c3b8b5a54d1c1fba6846`（2026-11-20） |
| 安装日期 | 2026-11-20 |
| 内容 | 仅核心技能 `skills/ponytail/SKILL.md`，连同上游 `LICENSE` |

上游还提供 `ponytail-review`、`ponytail-audit`、`ponytail-debt`、`ponytail-gain`、`ponytail-help` 五个命令型技能，以及插件宿主（hooks、band、board）。本次未安装：review/audit 与既有 `code-review`、`tdd` 职责重叠，命令型技能依赖 Claude Code 插件宿主，band 仅支持 Claude Code。

本地改动：

- `description` 从上游 366 字符压缩到 242 字符，让触发短语落在 ZCode 的约 250 字符截断点之内（见下节）。
- 移除 Claude Code 专用的 `argument-hint` frontmatter 字段；`license: MIT` 保留。
- 正文增加一段仓库优先级说明：`AGENTS.md`、项目规则、ADR、必需的测试/文档优先于「最小改动」偏好。
- 在 `ask-matt` 的 Standalone 列表补充 `/ponytail` 入口。

升级时从上游重新取同名文件，并逐条复查上述改动。

## 与 ZCode 的差异

上游只用 `disable-model-invocation: true`（Claude Code）和 `agents/openai.yaml` 的 `policy.allow_implicit_invocation: false`（Codex）来区分「只能人工调用」与「模型可自动调用」。**ZCode 的 `SKILL.md` frontmatter 只识别 `name`、`description`、`when_to_use`、`license`、`metadata`**，不识别上述两个字段，因此本目录下 `ask-matt`、`grill-me`、`grill-with-docs`、`handoff`、`implement`、`improve-codebase-architecture`、`setup-matt-pocock-skills`、`teach`、`to-questionnaire`、`to-spec`、`to-tickets`、`triage`、`wait-what`、`wayfinder` 这些上游的「用户调用」技能在 ZCode 中同样可被模型自动调用。它们的 description 是写给人看的、不含触发短语，所以误触发概率不高，但没有硬性保证。

ZCode 会把 `description` 截断到约 250 字符后再呈现给模型，并在 `description` 超过 1024 字符时丢弃整个技能。当前技能都未超过 1024 字符；超过 250 字符的是 `code-review`、`codebase-design`、`wizard`，其中 `code-review` 的触发短语落在截断点之后，自动触发可能不稳定，可按名字手动调用。`ponytail` 已按此限制压缩到 250 字符以内。

各技能引用的 `CONTEXT.md`、`docs/adr/`、`src/<context>/docs/adr/` 等路径是上游的通用布局。本仓库的领域文档在 `docs/<项目>/` 下，由根目录 `CONTEXT-MAP.md` 指路；写 ADR 时需明确告知技能目标路径。
