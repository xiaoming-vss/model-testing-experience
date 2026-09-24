import type { ReactNode } from 'react'
import { Input } from 'antd'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'

/*
 * 五个任务详情页（API / 功能 / UI / 代码风险 / 需求分析）共用的外壳零件。
 *
 * 这组页面的骨架本来就是同一套（`.ai-task-detail-layout` → 工具条 + 左右两栏），
 * 但工具条、左侧导航条目、指令编辑区三块在四五个文件里各写了一遍。
 * 结构一致的部分收到这里，页面只提供数据与回调；观感由 `styles/task-detail-v2.css` 接管。
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

/** 左侧导航面板：标题固定是「任务信息 / 导航」，正文由页面按输入、输出分组填充。 */
export function TaskDetailNavPanel({ tip, children }: { tip?: ReactNode; children: ReactNode }) {
  return (
    <aside className="ai-task-detail-nav-panel">
      <div className="ai-task-detail-nav-head">
        <span className="ai-task-detail-nav-head-title">任务信息</span>
        <span className="ai-task-detail-nav-head-sub">导航</span>
      </div>
      <div className="ai-task-detail-nav-body">
        {children}
        {tip ? <div className="ai-task-detail-nav-tip">{tip}</div> : null}
      </div>
    </aside>
  )
}

/** 导航条目：标题行（标题 + 可选计数徽标 + 类型图标）加一行摘要。 */
export function TaskDetailNavItem({ title, sub, icon, active, badge, onClick }: {
  title: ReactNode
  sub: ReactNode
  icon: ReactNode
  active: boolean
  badge?: ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className={`ai-task-detail-nav-item${active ? ' active' : ''}`}
      onClick={onClick}
    >
      <span className="ai-task-detail-nav-item-head">
        <span className="ai-task-detail-nav-item-title">
          {title}
          {badge == null ? null : <span className="ai-task-detail-nav-badge">{badge}</span>}
        </span>
        <span className="ai-task-detail-nav-item-icon">{icon}</span>
      </span>
      <span className="ai-task-detail-nav-item-sub">{sub}</span>
    </button>
  )
}

/**
 * 「指令」视图的内联编辑：设计稿把原来只读的正文换成可直接编辑 + 保存。
 * 只在草稿真的变了以后才允许提交，避免把原值当成一次修改写回去。
 */
export function TaskDetailInstructionEditor({ value, dirty, saving, disabled, placeholder, onChange, onSave }: {
  value: string
  dirty: boolean
  saving: boolean
  disabled?: boolean
  placeholder?: string
  onChange: (value: string) => void
  onSave: () => void
}) {
  return (
    <div className="ai-task-detail-instruction">
      <div className="ai-task-detail-instruction-head">
        <div className="ai-task-detail-instruction-copy">
          <span className="ai-task-detail-instruction-title">生成指令配置</span>
          <span className="ai-task-detail-instruction-desc">
            补充的上下文或测试提示词，将在触发下一次流水线运行时传递给生成内核。
          </span>
        </div>
        <ProjectActionButton action="write"
          type="primary"
          className="action-btn-save"
          disabled={disabled || !dirty || saving}
          loading={saving}
          onClick={onSave}
        >
          保存指令
        </ProjectActionButton>
      </div>
      <Input.TextArea
        className="ai-task-detail-instruction-editor"
        value={value}
        maxLength={1000}
        autoSize={{ minRows: 12, maxRows: 24 }}
        placeholder={placeholder ?? '例如：重点分析异常场景和歧义点'}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}

/** 运行记录视图顶部的四张 KPI：只有「最近状态」带主色左条与淡底，计数卡只给数字上色。 */
export function TaskDetailRunMetrics({ latestStatus, waiting, success, failed }: {
  latestStatus: ReactNode
  waiting: number
  success: number
  failed: number
}) {
  return (
    <div className="ai-task-run-metrics">
      <div className="ai-task-run-metric accent">
        <span className="ai-task-run-metric-k">最近状态</span>
        <span className="ai-task-run-metric-v">{latestStatus}</span>
      </div>
      <div className="ai-task-run-metric">
        <span className="ai-task-run-metric-k">待审核</span>
        <span className="ai-task-run-metric-v">{waiting}<small> 条</small></span>
      </div>
      <div className="ai-task-run-metric success">
        <span className="ai-task-run-metric-k">成功</span>
        <span className="ai-task-run-metric-v">{success}<small> 条</small></span>
      </div>
      <div className="ai-task-run-metric warn">
        <span className="ai-task-run-metric-k">失败</span>
        <span className="ai-task-run-metric-v">{failed}<small> 条</small></span>
      </div>
    </div>
  )
}
