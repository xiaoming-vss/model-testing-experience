import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { Alert, Drawer, Form, Input, Select } from 'antd'
import type { FormInstance } from 'antd'
import { getErrorMessage } from '@/utils/format'

export type CollectionFormValues = {
  sprintId?: string
  requirementId?: string
  name: string
  summary?: string
}

export function CollectionDrawer({
  title,
  open,
  form,
  loading,
  error,
  onClose,
  sprintOptions,
  requirementOptions,
  showScopeFields = true,
  onSprintChange,
  onFinish,
}: {
  title: string
  open: boolean
  form: FormInstance
  loading: boolean
  error: unknown
  onClose: () => void
  sprintOptions: Array<{ label: string; value: string }>
  requirementOptions: Array<{ label: string; value: string }>
  showScopeFields?: boolean
  onSprintChange?: (value?: string) => void
  onFinish: (values: CollectionFormValues) => void
}) {
  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      size={520}
      extra={
        <ProjectActionButton operation="save" action="write" type="primary" className="action-btn-save" loading={loading} onClick={() => form.submit()}>
          保存
        </ProjectActionButton>
      }
    >
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} /> : null}
      <Form<CollectionFormValues> form={form} layout="vertical" onFinish={onFinish} requiredMark={false}>
        {showScopeFields ? (
          <>
            <Form.Item name="sprintId" label="所属迭代" rules={[{ required: true, message: '请选择所属迭代' }]}>
              <Select placeholder="请选择迭代" options={sprintOptions} onChange={onSprintChange} />
            </Form.Item>
            <Form.Item name="requirementId" label="所属需求" rules={[{ required: true, message: '请选择所属需求' }]}>
              <Select placeholder="请选择需求" options={requirementOptions} />
            </Form.Item>
          </>
        ) : null}
        <Form.Item name="name" label="API测试集名称" rules={[{ required: true, message: '请输入API测试集名称' }]}>
          <Input maxLength={64} />
        </Form.Item>
        <Form.Item name="summary" label="描述">
          <Input.TextArea rows={6} maxLength={200} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
