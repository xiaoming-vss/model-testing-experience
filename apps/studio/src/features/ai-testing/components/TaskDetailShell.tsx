import type { ReactNode } from 'react'

/*
 * 任务详情页顶部工具条。页面只提供字段与回调；观感由 `styles/task-detail-v2.css` 接管。
 */

/** 工具条上的一个字段。`kind` 决定值的呈现形态，取值与样式层一一对应。 */
export type TaskDetailToolbarField = {
  label: string
  value: ReactNode
  /**
   * name：任务名，最长、可被压缩；
   * chip-accent / chip-muted：迭代、来源类型这类小色块；
   * time：等宽时间；
   * text：默认的普通值。
   */
  kind?: 'name' | 'chip-accent' | 'chip-muted' | 'text' | 'time'
  /** 这一项前面画什么：竖线分组，或同组内的中点。 */
  separator?: 'line' | 'dot'
}

const fieldValueClass: Record<NonNullable<TaskDetailToolbarField['kind']>, string> = {
  name: 'ai-task-detail-toolbar-name',
  'chip-accent': 'ai-task-detail-chip',
  'chip-muted': 'ai-task-detail-chip is-muted',
  text: 'ai-task-detail-toolbar-value',
  time: 'ai-task-detail-time',
}

/** 详情页顶部工具条：返回 + 若干字段 + 右侧动作组。 */
export function TaskDetailToolbar({ back, fields, actions }: {
  back: ReactNode
  fields: TaskDetailToolbarField[]
  actions: ReactNode
}) {
  return (
    <div className="ai-task-detail-toolbar">
      <div className="ai-task-detail-toolbar-main">
        {back}
        {fields.map((field) => (
          <div
            key={field.label}
            className={`ai-task-detail-toolbar-field${field.kind === 'name' ? ' is-name' : ''}`}
          >
            {field.separator === 'line' ? <span className="ai-task-detail-toolbar-divider" aria-hidden="true" /> : null}
            {field.separator === 'dot' ? <span className="ai-task-detail-meta-sep" aria-hidden="true">·</span> : null}
            <span className="ai-task-detail-toolbar-label">{field.label}</span>
            <span className={fieldValueClass[field.kind ?? 'text']}>{field.value}</span>
          </div>
        ))}
      </div>
      <div className="ai-task-detail-inline-actions">{actions}</div>
    </div>
  )
}
