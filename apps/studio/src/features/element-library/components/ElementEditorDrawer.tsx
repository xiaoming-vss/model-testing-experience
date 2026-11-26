import { Alert, Button, Drawer, Form, Input, Select } from 'antd'
import { useState } from 'react'
import { parameterNames } from '../utils/locatorTemplate'
import { locatorTypes, type ElementDetail, type ElementDraft } from '../types'

type FormValues = Omit<ElementDraft, 'groupId' | 'parameters'> & { group: string }

export function ElementEditorDrawer({ editor, groups, defaultGroup, saving, error, onClose, onSave }: {
  editor: ElementDetail | null
  groups: { value: string; label: string }[]
  defaultGroup: string
  saving: boolean
  error: string
  onClose: () => void
  onSave: (draft: ElementDraft) => void
}) {
  const [form] = Form.useForm<FormValues>()
  const [descriptions, setDescriptions] = useState(new Map(editor?.parameters.map(parameter => [parameter.name, parameter.description])))
  const template = Form.useWatch('locatorValue', form) ?? editor?.locatorValue ?? ''

  function save(values: FormValues) {
    const { group, ...fields } = values
    onSave({
      ...fields,
      groupId: group === 'common' ? null : group,
      parameters: parameterNames(fields.locatorValue).map(name => ({ name, description: descriptions.get(name)?.trim() ?? '' })),
    })
  }

  return <Drawer open title={editor ? '编辑元素' : '新建元素'} size="min(500px, 100vw)" onClose={onClose}
    closable={!saving} mask={{ closable: !saving }} keyboard={!saving}
    footer={<div className="flex justify-end gap-2">
      <Button disabled={saving} onClick={onClose}>取消</Button>
      <Button type="primary" loading={saving} onClick={() => form.submit()}>保存元素</Button>
    </div>}>
    {error && <Alert className="mb-4" type="error" showIcon title={error} />}
    <Form form={form} layout="vertical" onFinish={save} initialValues={{
      group: defaultGroup, name: editor?.name, scope: editor?.scope,
      locatorType: editor?.locatorType ?? 'test_id', locatorValue: editor?.locatorValue,
    }}>
      <Form.Item name="name" label="元素名称" rules={[{ required: true, whitespace: true }]}>
        <Input maxLength={120} />
      </Form.Item>
      <Form.Item name="group" label="所属分组" rules={[{ required: true }]}>
        <Select options={groups} />
      </Form.Item>
      <Form.Item name="scope" label="作用范围" rules={[{ required: true, whitespace: true }]}>
        <Input maxLength={255} placeholder="例如 编辑订单弹窗 · 已打开" />
      </Form.Item>
      <Form.Item name="locatorType" label="定位方式" rules={[{ required: true }]}>
        <Select virtual={false} options={locatorTypes.map(value => ({ label: value, value }))} />
      </Form.Item>
      <Form.Item name="locatorValue" label="定位值或模板" rules={[{ required: true, whitespace: true }]}
        extra="动态定位使用 {{参数名}}，XPath 使用 {{参数名|xpath}}。">
        <Input.TextArea rows={3} maxLength={4096} />
      </Form.Item>
    </Form>
    {parameterNames(template).map(name => <label key={name} className="mb-3 grid gap-1.5">
      <span className="[overflow-wrap:anywhere]">参数说明 <code>{name}</code></span>
      <Input maxLength={255} value={descriptions.get(name) ?? ''} onChange={event => {
        setDescriptions(new Map(descriptions).set(name, event.target.value))
      }} />
    </label>)}
  </Drawer>
}
