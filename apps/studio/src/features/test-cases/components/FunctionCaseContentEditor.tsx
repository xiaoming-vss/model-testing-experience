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
  return <div className="functional-case-editor-split-grid functional-case-step-inputs">
    <div className="functional-case-comparison-card">
      <h4 className="functional-case-field-heading"><OrderedListOutlined />操作步骤</h4>
      <Input.TextArea aria-label="操作步骤" value={actionsText} onChange={event => update('action', event.target.value)} autoSize={{ minRows: 9, maxRows: 24 }} placeholder="每行填写一个操作步骤" />
    </div>
    <div className="functional-case-comparison-card functional-case-comparison-expected">
      <h4 className="functional-case-field-heading"><CheckCircleOutlined />预期结果</h4>
      <Input.TextArea aria-label="预期结果" value={expectationsText} onChange={event => update('expected', event.target.value)} autoSize={{ minRows: 9, maxRows: 24 }} placeholder="每行填写对应步骤的预期结果" />
    </div>
  </div>
}

export function FunctionCaseContentEditor() {
  return <>
    <div className="functional-case-section-card functional-case-preconditions">
      <h4 className="functional-case-field-heading"><FileTextOutlined />前置条件</h4>
      <Form.Item
        name={['content', 'preconditions']}
        getValueProps={(value?: string[]) => ({ value: (value ?? []).join('\n') })}
        getValueFromEvent={event => event.target.value ? [event.target.value] : []}
      >
        <Input.TextArea aria-label="前置条件" autoSize={{ minRows: 4, maxRows: 16 }} placeholder="请输入前置条件，可换行填写" />
      </Form.Item>
    </div>
    <div className="functional-case-comparison-section">
      <Form.Item name={['content', 'steps']} style={{ marginBottom: 0 }}>
        <StepsInput />
      </Form.Item>
    </div>
  </>
}
