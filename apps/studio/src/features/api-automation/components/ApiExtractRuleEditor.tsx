import {
  extractSourceOptions
} from '@/features/api-automation/config/collectionConfig'
import { type ExtractRuleFormValues } from '@/features/api-automation/utils/detailView'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import {
  type ApiExtractRule,
  type CreateApiExtractRulePayload
} from '@/services/api'
import { Form, Input, InputNumber, Select, Switch } from 'antd'

import type { ApiExtractRuleSource } from '@/features/api-automation/types'
import type { UseMutationResult } from '@tanstack/react-query'
import type { FormInstance } from 'antd'

type Props = {
  extractRuleModalOpen: boolean
  editingExtractRule: ApiExtractRule | null
  setExtractRuleModalOpen: React.Dispatch<React.SetStateAction<boolean>>
  setEditingExtractRule: React.Dispatch<React.SetStateAction<ApiExtractRule | null>>
  extractRuleForm: FormInstance<CreateApiExtractRulePayload>
  saveExtractRuleMutation: UseMutationResult<ApiExtractRule, Error, CreateApiExtractRulePayload, unknown>
  watchedExtractSource: ApiExtractRuleSource
}

export function ApiExtractRuleEditor({ extractRuleModalOpen, editingExtractRule, setExtractRuleModalOpen, setEditingExtractRule, extractRuleForm, saveExtractRuleMutation, watchedExtractSource }: Props) {
  return (
    <ProjectActionModal action="write"
      mask={{ closable: false }}
      open={extractRuleModalOpen}
      title={editingExtractRule ? '编辑提取规则' : '新增提取规则'}
      okText="保存"
      onCancel={() => {
        setExtractRuleModalOpen(false)
        setEditingExtractRule(null)
        extractRuleForm.resetFields()
      }}
      confirmLoading={saveExtractRuleMutation.isPending}
      okButtonProps={{ className: 'action-btn-save' }}
      onOk={() => extractRuleForm.submit()}
      destroyOnHidden
    >
      <Form<ExtractRuleFormValues>
        form={extractRuleForm}
        layout="vertical"
        requiredMark={false}
        onFinish={(values) => saveExtractRuleMutation.mutate(values)}
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
          <Form.Item name="source" label="来源" rules={[{ required: true, message: '请选择来源' }]}>
            <Select options={extractSourceOptions} />
          </Form.Item>
          <Form.Item
            name="varKey"
            label="写回变量 Key"
            extra="运行后会写回当前所选环境；同名变量存在时更新，不存在时自动创建。"
            rules={[{ required: true, message: '请输入写回变量 Key' }]}
          >
            <Input maxLength={120} placeholder="例如：token" />
          </Form.Item>
        </div>
        <Form.Item name="sourceExpr" label="来源表达式">
          <Input placeholder={watchedExtractSource === 'status_code' ? '可留空' : '例如：$.data.token'} />
        </Form.Item>
        <Form.Item name="defaultValue" label="默认值">
          <Input placeholder="提取失败时回退" />
        </Form.Item>
      </Form>
    </ProjectActionModal>
  )
}
