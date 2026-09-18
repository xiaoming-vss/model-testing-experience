import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { Alert, Drawer, Form, Input, Select } from 'antd'
import type { FormInstance } from 'antd'
import type { CreateRequirementAnalysisTaskPayload } from '../types'
import { getErrorMessage } from '@/utils/format'

export type RequirementAnalysisTaskFormValues = CreateRequirementAnalysisTaskPayload & {
  sprintId?: string
}

export function RequirementAnalysisTaskDrawer({
  title,
  open,
  form,
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
  form: FormInstance<RequirementAnalysisTaskFormValues>
  loading: boolean
  error: unknown
  sprintOptions: Array<{ label: string; value: string }>
  requirementOptions: Array<{ label: string; value: string }>
  onSprintChange: (value?: string) => void
  onClose: () => void
  onFinish: (values: CreateRequirementAnalysisTaskPayload) => void
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
      <Form<RequirementAnalysisTaskFormValues>
        className="ai-task-drawer-form"
        form={form}
        layout="vertical"
        onFinish={(values) =>
          onFinish({
            name: values.name.trim(),
            requirementId: values.requirementId,
            instruction: values.instruction?.trim() ?? '',
          })
        }
        requiredMark={false}
      >
        <div className="ai-task-drawer-basic-grid">
          <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
            <Input maxLength={120} placeholder="例如：需求分析" />
          </Form.Item>
          <Form.Item name="sprintId" label="所属迭代">
            <Select allowClear placeholder="可先选择迭代筛选需求" options={sprintOptions} onChange={onSprintChange} />
          </Form.Item>
          <Form.Item name="requirementId" label="所属需求" rules={[{ required: true, message: '请选择所属需求' }]}>
            <Select showSearch placeholder="请选择需求" options={requirementOptions} optionFilterProp="label" />
          </Form.Item>
        </div>

        <Form.Item name="instruction" label="补充指令" extra="可选，描述本任务希望重点分析的异常场景、歧义点或输出侧重点。">
          <Input.TextArea
            className="ai-task-instruction-textarea"
            maxLength={1000}
            placeholder="例如：重点分析异常场景和歧义点"
          />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
