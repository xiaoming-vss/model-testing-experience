import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { Alert, Drawer, Form, Input, Select } from 'antd'
import type { FormInstance } from 'antd'
import type { CollectionFormValues } from '@/shared/types/forms'
import { getErrorMessage } from '@/utils/format'

export type { CollectionFormValues }

export function CollectionDrawer({
  title,
  open,
  form,
  loading,
  error,
  onClose,
  requirementOptions,
  showScopeFields = true,
  onFinish,
}: {
  title: string
  open: boolean
  form: FormInstance
  loading: boolean
  error: unknown
  onClose: () => void
  requirementOptions: Array<{ label: string; value: string }>
  showScopeFields?: boolean
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
          <Form.Item name="requirementId" label="所属需求">
            <Select allowClear placeholder="不关联需求（项目级测试集）" options={requirementOptions} />
          </Form.Item>
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
