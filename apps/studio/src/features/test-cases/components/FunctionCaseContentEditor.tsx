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

  return <div className="case-editor-grid case-editor-steps-grid">
    <section className="case-editor-section case-editor-section-tinted tone-blue">
      <div className="case-editor-section-head">
        <span className="case-editor-section-title"><OrderedListOutlined />操作步骤</span>
        <span className="case-editor-count-badge">{stepCount} 个步骤</span>
      </div>
      <div className="case-editor-section-body">
        <Input.TextArea aria-label="操作步骤" value={actionsText} onChange={event => update('action', event.target.value)} autoSize={{ minRows: 9, maxRows: 24 }} placeholder="每行填写一个操作步骤" />
      </div>
    </section>
    <section className="case-editor-section case-editor-section-tinted tone-green">
      <div className="case-editor-section-head">
        <span className="case-editor-section-title"><CheckCircleOutlined />预期结果</span>
        <span className="case-editor-count-badge">验证达标标准</span>
      </div>
      <div className="case-editor-section-body">
        <Input.TextArea aria-label="预期结果" value={expectationsText} onChange={event => update('expected', event.target.value)} autoSize={{ minRows: 9, maxRows: 24 }} placeholder="每行填写对应步骤的预期结果" />
      </div>
    </section>
  </div>
}

export function FunctionCaseContentEditor() {
  return <>
    <section className="case-editor-section tone-blue">
      <div className="case-editor-section-head">
        <span className="case-editor-section-title"><FileTextOutlined />前置条件</span>
        <span className="case-editor-section-hint">执行测试前必须具备的环境与依赖数据</span>
      </div>
      <div className="case-editor-section-body">
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
