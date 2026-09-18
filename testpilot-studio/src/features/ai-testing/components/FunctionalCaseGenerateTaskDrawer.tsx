import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { Alert, Drawer, Form, Input, Select } from 'antd'
import type { FormInstance } from 'antd'
import type { CreateFunctionalCaseGenerateTaskPayload } from '../types'
import { getErrorMessage } from '@/utils/format'

export type FunctionalCaseGenerateTaskFormValues = CreateFunctionalCaseGenerateTaskPayload

export function FunctionalCaseGenerateTaskDrawer({
  title,
  open,
  form,
  editing,
  loading,
  error,
  sprintOptions,
  requirementOptions,
  onSprintChange,
  onClose,
  onFinish,
}: {
  title: string
  open: boolean
  form: FormInstance<FunctionalCaseGenerateTaskFormValues>
  editing: boolean
  loading: boolean
  error: unknown
  sprintOptions: Array<{ label: string; value: string }>
  requirementOptions: Array<{ label: string; value: string }>
  onSprintChange: (value?: string) => void
  onClose: () => void
  onFinish: (values: FunctionalCaseGenerateTaskFormValues) => void
}) {
  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      size={640}
      rootClassName="ai-task-generate-drawer"
      destroyOnHidden={false}
      extra={
        <ProjectActionButton operation="save" action="write" type="primary" className="action-btn-save" loading={loading} onClick={() => form.submit()}>
          保存
        </ProjectActionButton>
      }
    >
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} style={{ marginBottom: 16 }} /> : null}
      <Form<FunctionalCaseGenerateTaskFormValues>
        className="ai-task-drawer-form"
        form={form}
        layout="vertical"
        onFinish={(values) =>
          onFinish({
            ...values,
            instruction: values.instruction?.trim() ?? '',
          })
        }
        requiredMark={false}
      >
        <div className="ai-task-drawer-basic-grid">
          <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
            <Input maxLength={120} placeholder="例如：订单审批功能用例生成" />
          </Form.Item>
          <Form.Item name="sprintId" label="所属迭代" rules={[{ required: true, message: '请选择所属迭代' }]}>
            <Select placeholder="请选择迭代" options={sprintOptions} onChange={onSprintChange} />
          </Form.Item>
          <Form.Item name="requirementId" label="所属需求" rules={[{ required: true, message: '请选择所属需求' }]}>
            <Select placeholder="请选择需求" options={requirementOptions} disabled={requirementOptions.length === 0} />
          </Form.Item>
        </div>

        <Form.Item
          name="instruction"
          label="生成指令"
          extra={editing ? '可选，留空则按默认生成策略执行。' : '可选，描述希望覆盖的业务范围、异常场景或输出约束。'}
        >
          <Input.TextArea
            className="ai-task-instruction-textarea"
            maxLength={1000}
            placeholder="例如：重点覆盖异常登录、权限校验和边界条件"
          />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
