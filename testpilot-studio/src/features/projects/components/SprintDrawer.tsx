import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { Alert, DatePicker, Drawer, Form, Input } from 'antd'
import type { FormInstance } from 'antd'
import type { SprintCreatePayload } from '@/services/api'
import { getErrorMessage } from '@/utils/format'

type DateLikeValue = string | Date | { toDate?: () => Date; toISOString?: () => string } | null | undefined

export type SprintFormValues = Omit<SprintCreatePayload, 'startTime' | 'endTime'> & {
  startTime: DateLikeValue
  endTime: DateLikeValue
}

function toTimestamp(value: DateLikeValue) {
  if (!value) return Number.NaN
  if (value instanceof Date) return value.getTime()
  if (typeof value === 'string') return new Date(value).getTime()
  if (typeof value.toDate === 'function') return value.toDate().getTime()
  if (typeof value.toISOString === 'function') return new Date(value.toISOString()).getTime()
  return Number.NaN
}

export function SprintDrawer({
  title,
  open,
  form,
  loading,
  error,
  onClose,
  onFinish,
}: {
  title: string
  open: boolean
  form: FormInstance
  loading: boolean
  error: unknown
  onClose: () => void
  onFinish: (values: SprintFormValues) => void
}) {
  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      size={480}
      extra={
        <ProjectActionButton operation="save" action="write" type="primary" className="action-btn-save" loading={loading} onClick={() => form.submit()}>
          保存
        </ProjectActionButton>
      }
    >
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} /> : null}
      <Form form={form} layout="vertical" onFinish={onFinish} requiredMark={false}>
        <Form.Item name="name" label="迭代名称" rules={[{ required: true, message: '请输入迭代名称' }]}>
          <Input maxLength={64} />
        </Form.Item>
        <Form.Item name="startTime" label="开始时间" rules={[{ required: true, message: '请选择开始时间' }]}>
          <DatePicker showTime format="YYYY-MM-DD HH:mm:ss" placeholder="请选择开始时间" style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item
          name="endTime"
          label="结束时间"
          dependencies={['startTime']}
          rules={[
            { required: true, message: '请选择结束时间' },
            ({ getFieldValue }) => ({
              validator(_, value: DateLikeValue) {
                const startTime = getFieldValue('startTime') as DateLikeValue
                if (!value || !startTime || toTimestamp(value) > toTimestamp(startTime)) return Promise.resolve()
                return Promise.reject(new Error('结束时间必须晚于开始时间'))
              },
            }),
          ]}
        >
          <DatePicker showTime format="YYYY-MM-DD HH:mm:ss" placeholder="请选择结束时间" style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="description" label="迭代描述">
          <Input.TextArea rows={4} maxLength={256} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
