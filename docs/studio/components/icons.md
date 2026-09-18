# 项目彩色图标库

彩色图标统一存放在这里，由 `@/shared/icons` 导出，业务页面不直接引用图片路径。

```tsx
import { AppIcon } from '@/shared/icons'

<AppIcon name="llm" />
<AppIcon name="zentao" size={24} />
<AppIcon name="gitlab" size={32} />
```

默认尺寸为 18px。旁边已有文字时，图标作为装饰；独立使用时传入 `label` 提供可访问名称。

## 目录

- `assets/`：图标文件，随构建打包，不依赖外部图片服务。
- `registry.ts`：唯一名称注册表，新增后自动扩展 `AppIcon` 的名称类型。
- `AppIcon.tsx`：统一尺寸、对齐和可访问性的展示组件。
- `licenses/`：第三方许可。

新增图标时，将文件放入 `assets/`，在注册表登记名称，并在下表补充来源与许可。
通用操作图标在 `actions.ts` 集中注册（使用 Ant Design 线性图标），页面通过 [ActionButton](action-button.md) 使用；站点 favicon 保留在 `public/favicon.svg`。

## 来源与许可

| 名称 | 样式 | 来源 | 许可 |
| --- | --- | --- | --- |
| `llm` | 蓝紫渐变对话气泡 | [Microsoft Fluent Chat Color](https://github.com/microsoft/fluentui-system-icons/blob/main/assets/Chat/SVG/ic_fluent_chat_24_color.svg) | [MIT](../../../apps/studio/src/shared/icons/licenses/fluent-icons-LICENSE.txt) |
| `zentao` | 禅道彩色标志 | https://www.zentao.net/favicon.ico | 品牌标志归各自所有者所有 |
| `gitlab` | GitLab 彩色标志 | https://gitlab.com/favicon.ico | 品牌标志归各自所有者所有 |
| `sprint` | 迭代 · Calendar Sync | [Microsoft Fluent](https://github.com/microsoft/fluentui-system-icons/blob/main/assets/Calendar%20Sync/SVG/ic_fluent_calendar_sync_24_color.svg) | [MIT](../../../apps/studio/src/shared/icons/licenses/fluent-icons-LICENSE.txt) |
| `requirement` | 需求 · Document Text | [Microsoft Fluent](https://github.com/microsoft/fluentui-system-icons/blob/main/assets/Document%20Text/SVG/ic_fluent_document_text_24_color.svg) | [MIT](../../../apps/studio/src/shared/icons/licenses/fluent-icons-LICENSE.txt) |
| `functional` | 功能测试 · Clipboard Task | [Microsoft Fluent](https://github.com/microsoft/fluentui-system-icons/blob/main/assets/Clipboard%20Task/SVG/ic_fluent_clipboard_task_24_color.svg) | [MIT](../../../apps/studio/src/shared/icons/licenses/fluent-icons-LICENSE.txt) |
| `api` | API测试 · Link | [Microsoft Fluent](https://github.com/microsoft/fluentui-system-icons/blob/main/assets/Link/SVG/ic_fluent_link_24_color.svg) | [MIT](../../../apps/studio/src/shared/icons/licenses/fluent-icons-LICENSE.txt) |
| `ui` | UI测试 · Laptop | [Microsoft Fluent](https://github.com/microsoft/fluentui-system-icons/blob/main/assets/Laptop/SVG/ic_fluent_laptop_24_color.svg) | [MIT](../../../apps/studio/src/shared/icons/licenses/fluent-icons-LICENSE.txt) |
| `tasks` | 任务 · Board | [Microsoft Fluent](https://github.com/microsoft/fluentui-system-icons/blob/main/assets/Board/SVG/ic_fluent_board_24_color.svg) | [MIT](../../../apps/studio/src/shared/icons/licenses/fluent-icons-LICENSE.txt) |
| `skills` | Skill库 · Library | [Microsoft Fluent](https://github.com/microsoft/fluentui-system-icons/blob/main/assets/Library/SVG/ic_fluent_library_24_color.svg) | [MIT](../../../apps/studio/src/shared/icons/licenses/fluent-icons-LICENSE.txt) |
| `analysis` | 需求分析 · Text Bullet List Square Sparkle | [Microsoft Fluent](https://github.com/microsoft/fluentui-system-icons/blob/main/assets/Text%20Bullet%20List%20Square%20Sparkle/SVG/ic_fluent_text_bullet_list_square_sparkle_24_color.svg) | [MIT](../../../apps/studio/src/shared/icons/licenses/fluent-icons-LICENSE.txt) |
| `codeRisk` | 代码风险分析 · Shield Checkmark | [Microsoft Fluent](https://github.com/microsoft/fluentui-system-icons/blob/main/assets/Shield%20Checkmark/SVG/ic_fluent_shield_checkmark_24_color.svg) | [MIT](../../../apps/studio/src/shared/icons/licenses/fluent-icons-LICENSE.txt) |

主导航 `projects`、`testing`、`testDesign`、`services` 使用本项目自绘的蓝灰双色 SVG（`assets/nav-*.svg`），统一 24px 画布、1.6px 描边及圆角；不使用品牌配色。
