# 统一操作按钮

运行、编辑、删除、新建、保存、刷新、下载和上传使用此组件；线性图标及默认文案统一定义在 `src/shared/icons/actions.ts`。

```tsx
import { ActionButton } from '@/shared/components/ActionButton'

<ActionButton operation="run" loading={running} onClick={run} />
<ActionButton operation="create" type="primary">新建测试集</ActionButton>
<ActionButton operation="edit" iconOnly aria-label="编辑需求" onClick={edit} />
```

- 页面主要操作保留图标与文字，列表紧凑操作可使用 `iconOnly`。
- 支持 Ant Design Button 的尺寸、样式、加载、禁用、事件和 ref，默认尺寸沿用 Ant Design。
- 纯图标模式自动提供 Tooltip 和无障碍名称，优先使用 `aria-label`、`title`，再使用业务文字或默认文案。
- 删除默认使用危险色。确认行为由外层 `Popconfirm` 或已有确认弹窗承担，组件不会绕过确认直接执行删除。
- 需要项目权限控制时，使用 `ProjectActionButton`，传入权限 `action` 和按钮 `operation`，例如 `action="execute" operation="run"`。
- 审核通过、继续优化等业务动作保留明确文案，不强行归入通用操作。

## 全局外观

按钮配色统一在 `src/app/styles/buttons.css` 管理，由 ThemeProvider 加载，涵盖普通 Button、ActionButton、弹窗和抽屉。主操作使用浅蓝底与细边框，普通操作使用中性色，危险操作使用柔和红色；深色主题使用对应低亮度底色。页面不再新增独立按钮渐变、发光阴影或颜色覆盖。
