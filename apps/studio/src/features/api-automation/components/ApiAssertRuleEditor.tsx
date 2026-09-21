import {
  assertComparatorOptions,
  assertSourceOptions
} from '@/features/api-automation/config/collectionConfig'
import { type AssertRuleFormValues } from '@/features/api-automation/utils/detailView'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import {
  type ApiAssertComparator,
  type ApiAssertRule,
  type ApiAssertSource,
  type CreateApiAssertRulePayload
} from '@/services/api'
import { Form, Input, InputNumber, Select, Switch } from 'antd'

import type { UseMutationResult } from '@tanstack/react-query'
import type { FormInstance } from 'antd'

type Props = {
  assertRuleModalOpen: boolean
  editingAssertRule: ApiAssertRule | null
  setAssertRuleModalOpen: React.Dispatch<React.SetStateAction<boolean>>
  setEditingAssertRule: React.Dispatch<React.SetStateAction<ApiAssertRule | null>>
  assertRuleForm: FormInstance<CreateApiAssertRulePayload>
  saveAssertRuleMutation: UseMutationResult<ApiAssertRule, Error, CreateApiAssertRulePayload, unknown>
  watchedAssertSource: ApiAssertSource
  watchedAssertComparator: ApiAssertComparator
}

export function ApiAssertRuleEditor({ assertRuleModalOpen, editingAssertRule, setAssertRuleModalOpen, setEditingAssertRule, assertRuleForm, saveAssertRuleMutation, watchedAssertSource, watchedAssertComparator }: Props) {
  return (
    <ProjectActionModal action="write"
      mask={{ closable: false }}
      open={assertRuleModalOpen}
      title={editingAssertRule ? '编辑断言规则' : '新增断言规则'}
      okText="保存"
      onCancel={() => {
        setAssertRuleModalOpen(false)
        setEditingAssertRule(null)
        assertRuleForm.resetFields()
      }}
      confirmLoading={saveAssertRuleMutation.isPending}
      okButtonProps={{ className: 'action-btn-save' }}
      onOk={() => assertRuleForm.submit()}
      destroyOnHidden
    >
      <Form<AssertRuleFormValues>
        form={assertRuleForm}
        layout="vertical"
        requiredMark={false}
        onFinish={(values) => saveAssertRuleMutation.mutate(values)}
      >
        <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入规则名称' }]}>
          <Input maxLength={120} />
        </Form.Item>
        <div className="api-rule-form-grid">
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="orderNo" label="顺序">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
        </div>
        <div className="api-rule-form-grid">
          <Form.Item name="assertSource" label="来源" rules={[{ required: true, message: '请选择来源' }]}>
            <Select options={assertSourceOptions} />
          </Form.Item>
          <Form.Item name="comparator" label="比较方式" rules={[{ required: true, message: '请选择比较方式' }]}>
            <Select options={assertComparatorOptions} />
          </Form.Item>
        </div>
        <Form.Item name="targetExpr" label="目标表达式" extra={watchedAssertSource === 'status_code' ? 'status_code 场景可留空。' : undefined}>
          <Input placeholder={watchedAssertSource === 'status_code' ? '可留空' : '例如：$.data.token'} />
        </Form.Item>
        <Form.Item
          name="expectedValue"
          label="期望值"
          extra={watchedAssertComparator === 'exists' ? 'exists 断言可留空。' : undefined}
        >
          <Input placeholder={watchedAssertComparator === 'exists' ? '可留空' : '填写期望结果'} />
        </Form.Item>
      </Form>
    </ProjectActionModal>
  )
}
