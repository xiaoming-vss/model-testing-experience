# Nanobot 0.3.5 配置字段对比

核对日期：2026-09-16。比较基线为项目升级前固定的 `b55b76d75574d74c1ff5356bace3b76ad12ef399`（包版本元数据 0.3.0），目标为实际安装的 PyPI `nanobot-ai==0.3.5`。这里的“新增”指相对该提交新增，不等同于相对 PyPI 0.3.0 发布包新增。

使用两版配置模型及渠道默认配置进行比较；Matrix、NapCat、QQ、Slack、Telegram 缺少可选运行依赖，改用渠道配置类源码 AST 对比字段。没有安装额外渠道依赖，也没有启动渠道或调用模型。`model_presets` 按支持的别名 `modelPresets` 比较，不算缺失。

## 相对升级前提交新增的字段

以下字段当前模板均未显式填写，SDK 会使用默认值或兼容规则。

| 字段 | 新版默认值／规则 | 含义和当前项目影响 |
| --- | --- | --- |
| `agents.defaults.timezoneMode` | 新配置 `auto`；旧配置明确填写 timezone 时推导为 `manual` | 自动探测或手动指定时区。当前模板有 `timezone: UTC`，实际为 manual，并未自动切换上海时区。 |
| `agents.defaults.idleCompactCheckIntervalSeconds` | `60` | 空闲会话压缩扫描的最小间隔，单位秒；与现有 15 分钟空闲阈值不同。 |
| `tools.maxSessionMessagesPerMinute` | `6` | 会话消息工具的发送限额；不是模型请求限流，也不是 Worker 并发任务数。 |
| `providers.orcarouter` | 空的 Provider 配置 | 新增 OrcaRouter 服务商配置组，当前使用 custom 时不需要配置。 |
| `providers.edenai` | 空的 Provider 配置 | 新增 Eden AI 服务商配置组，当前使用 custom 时不需要配置。 |
| `channels.dingtalk.disablePrivateChat` | `false` | 禁止钉钉私聊的开关。 |
| `channels.email.trustedAuthservIds` | `[]` | 邮件 Authentication-Results 的可信认证服务标识；启用 SPF/DKIM 检查的邮件渠道需要正确配置。 |
| `channels.mattermost.groupPolicyInThread` | 未指定时继承 groupPolicy；通常为 `mention` | Mattermost 群组线程内的消息处理策略。 |
| `channels.websocket.publicWsUrl` | `""` | 对外公开的 WebSocket 地址。 |
| `channels.websocket.trustedProxyAuth` | `null` | 可信代理认证的可选配置组。 |
| `channels.weixin.sendProgress` | `false` | 微信进度消息。 |
| `channels.weixin.sendToolHints` | `false` | 微信工具调用提示。 |
| `channels.weixin.replyProgressMessages` | `false` | 将进度作为回复消息发送。 |
| `channels.weixin.replyProgressMaxMessages` | `2` | 进度回复数量限制。 |
| `channels.weixin.contextMessageBudget` | `8` | 微信上下文消息预算。 |
| `channels.weixin.blockStreaming` | `false` | 微信分块流式回复开关。 |
| `channels.weixin.blockStreamingMinChars` | `1200` | 微信流式回复分块字符阈值。 |
| `channels.weixin.blockStreamingMaxMessages` | `3` | 微信流式回复分块消息数限制。 |
| `channels.whatsapp.proxy` | `""` | WhatsApp 代理。 |
| `channels.matrix.proxy` | `null` | Matrix 代理。 |
| `channels.slack.proxy` | `null` | Slack 代理。 |

当前模板中的渠道均未启用，新增渠道字段不影响现有 SDK 用例生成流程。

## 旧版已有、当前模板尚未显式填写

这些不能称为本次升级新增：

- `providers.*.proxy=null`、`providers.*.thinkingStyle=null`；Provider 还支持可选 `displayName`，默认不输出该空字段。
- 服务商配置组：`modelscope`、`kimiCoding`、`opencode`、`opencodeZen`、`opencodeGo`。
- `api.apiKey=""`。
- `gateway.restartMode="auto"`。
- `tools.exec.sandboxRoBinds=[]`、`tools.exec.sandboxRwBinds=[]`。
- `tools.webuiAllowRemotePackageInstall=false`。
- Mattermost 渠道整体配置（其中 groupPolicyInThread 才是本次新增）。
- 飞书的 `instanceId`、`name`、`identityKey`，微信的 `streaming`，WhatsApp 的 `databasePath`。

顶层 `transcription` 已在模板内，包含 enabled、provider、model、language、maxDurationSec、maxUploadMb；并非缺失。旧的 `channels.transcriptionProvider`、`channels.transcriptionLanguage` 仍保留，需要另行清理或明确转录来源，避免混淆。

## 默认行为变化

- `maxConcurrentSubagents` 默认值从 1 变为 4；模板明确设置为 1，所以当前仍为 1。
- 新配置的时区默认自动探测；模板明确设置 UTC，兼容规则保持手动 UTC。
- Signal 私聊 enabled 默认从 false 变为 true；模板显式为 false，当前行为保持不变。

## 建议

如需显式对齐当前行为，优先填写 `timezoneMode: manual`、`idleCompactCheckIntervalSeconds: 60`、`maxSessionMessagesPerMinute: 6`。不要因为新版存在某配置组就启用对应服务商或渠道。

`NANOBOT_STREAM_IDLE_TIMEOUT_S` 是环境变量，不是新增 JSON 字段。其默认值为 90 秒，控制流式调用无数据超时；旧的 `NANOBOT_LLM_TIMEOUT_S` 已不生效，应单独处理 Worker 的超时配置。

本次仅对比并记录，没有向模板添加字段。当前 `maxTokens=65536`、`contextWindowTokens=200000`。
