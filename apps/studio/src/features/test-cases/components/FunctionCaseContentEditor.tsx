import { CheckCircleOutlined, FileTextOutlined, OrderedListOutlined } from '@ant-design/icons'
import { Form, Input } from 'antd'
import { useState } from 'react'
import type { FunctionCaseContent } from '../types'

type Steps = FunctionCaseContent['steps']

function StepsInput({ value = [], onChange }: { value?: Steps; onChange?: (value: Steps) => void }) {
  const [draft, setDraft] = useState<{ value: Steps; actions: string; expectations: string } | null>(null)
  const actionsText = draft?.value === value ? draft.actions : value.map(step => step.action).join('\n')
  const expectationsText = draft?.value === value ? draft.expectations : value.map(step => step.expected).join('\n')
  const update = (field: 'action' | 'expected', text: string) => {
    const actions = field === 'action' ? text : actionsText
    const expectations = field === 'expected' ? text : expectationsText
    const actionLines = actions.split('\n')
    const expectedLines = expectations.split('\n')
    const next = !actions && !expectations ? [] : Array.from({ length: Math.max(actionLines.length, expectedLines.length) }, (_, index) => ({
      action: actionLines[index] ?? '',
      expected: expectedLines[index] ?? '',
    }))
    setDraft({ value: next, actions, expectations })
    onChange?.(next)
  }
  // 空行不算步骤：这样「N 个步骤」和用户在框里看到的有效行数一致。
  const stepCount = value.filter(step => step.action.trim()).length

  return <div className="case-editor-grid case-editor-steps-grid grid grid-cols-2 items-stretch gap-4 max-[900.01px]:grid-cols-1">
    <section className="case-editor-section case-editor-section-tinted flex min-w-0 flex-col overflow-hidden rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] tone-blue">
      <div className="case-editor-section-head flex flex-wrap items-center justify-between gap-2 px-4 py-3">
        <span className="case-editor-section-title inline-flex items-center gap-2 text-xs font-bold leading-[18px] text-[var(--srf-text)]"><OrderedListOutlined />操作步骤</span>
        <span className="case-editor-count-badge rounded-[4px] bg-[var(--srf-chip)] px-2 py-0.5 text-[10px] font-semibold leading-[16px] text-[var(--srf-tone-text,var(--srf-text-secondary))]">{stepCount} 个步骤</span>
      </div>
      <div className="case-editor-section-body flex flex-1 flex-col px-4 pt-3.5 pb-4">
        <Input.TextArea className="flex-1" aria-label="操作步骤" value={actionsText} onChange={event => update('action', event.target.value)} autoSize={{ minRows: 9, maxRows: 24 }} placeholder="每行填写一个操作步骤" />
      </div>
    </section>
    <section className="case-editor-section case-editor-section-tinted flex min-w-0 flex-col overflow-hidden rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] tone-green">
      <div className="case-editor-section-head flex flex-wrap items-center justify-between gap-2 px-4 py-3">
        <span className="case-editor-section-title inline-flex items-center gap-2 text-xs font-bold leading-[18px] text-[var(--srf-text)]"><CheckCircleOutlined />预期结果</span>
        <span className="case-editor-count-badge rounded-[4px] bg-[var(--srf-chip)] px-2 py-0.5 text-[10px] font-semibold leading-[16px] text-[var(--srf-tone-text,var(--srf-text-secondary))]">验证达标标准</span>
      </div>
      <div className="case-editor-section-body flex flex-1 flex-col px-4 pt-3.5 pb-4">
        <Input.TextArea className="flex-1" aria-label="预期结果" value={expectationsText} onChange={event => update('expected', event.target.value)} autoSize={{ minRows: 9, maxRows: 24 }} placeholder="每行填写对应步骤的预期结果" />
      </div>
    </section>
  </div>
}

export function FunctionCaseContentEditor() {
  return <>
    <section className="case-editor-section flex min-w-0 flex-col overflow-hidden rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] tone-blue">
      <div className="case-editor-section-head flex flex-wrap items-center justify-between gap-2 px-4 py-3">
        <span className="case-editor-section-title inline-flex items-center gap-2 text-xs font-bold leading-[18px] text-[var(--srf-text)]"><FileTextOutlined />前置条件</span>
        <span className="case-editor-section-hint text-[11px] leading-[16px] text-[var(--srf-text-muted)]">执行测试前必须具备的环境与依赖数据</span>
      </div>
      <div className="case-editor-section-body px-4 pt-3.5 pb-4">
        <Form.Item
          name={['content', 'preconditions']}
          getValueProps={(value?: string[]) => ({ value: (value ?? []).join('\n') })}
          getValueFromEvent={event => event.target.value ? [event.target.value] : []}
        >
          <Input.TextArea aria-label="前置条件" autoSize={{ minRows: 4, maxRows: 16 }} placeholder="请输入前置条件，可换行填写" />
        </Form.Item>
      </div>
    </section>
    <Form.Item name={['content', 'steps']} style={{ marginBottom: 0 }}>
      <StepsInput />
    </Form.Item>
  </>
}
