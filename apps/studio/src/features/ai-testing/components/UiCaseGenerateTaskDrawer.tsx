import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/task-form.css'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { Alert, Drawer, Form, Input, Select, Typography } from 'antd'
import type { FormInstance } from 'antd'
import type { CreateUiCaseGenerateTaskPayload } from '../types'
import { validateUiSourceArchive } from '../utils/uiSourceArchive'
import { getErrorMessage } from '@/utils/format'

export type UiCaseGenerateTaskFormValues = CreateUiCaseGenerateTaskPayload & {
  sourceArchiveFile: File
}

export function UiCaseGenerateTaskDrawer({
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
  open: boolean
  form: FormInstance<UiCaseGenerateTaskFormValues>
  loading: boolean
  error: unknown
  sprintOptions: Array<{ label: string; value: string }>
  requirementOptions: Array<{ label: string; value: string }>
  onSprintChange: (value?: string) => void
  onClose: () => void
  onFinish: (values: UiCaseGenerateTaskFormValues) => void
}) {
  return (
    <Drawer
      title="新建 UI 用例生成任务"
      open={open}
      onClose={onClose}
      size={640}
      rootClassName="ai-task-generate-drawer"
      destroyOnHidden={false}
      extra={
        <ProjectActionButton action="write" type="primary" loading={loading} disabled={loading} onClick={() => form.submit()}>
          创建并上传
        </ProjectActionButton>
      }
    >
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} style={{ marginBottom: 16 }} /> : null}
      <Form<UiCaseGenerateTaskFormValues>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(values) => onFinish({ ...values, instruction: values.instruction?.trim() ?? '' })}
      >
        <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
          <Input maxLength={120} placeholder="例如：登录模块 UI 用例生成" />
        </Form.Item>
        <Form.Item name="sprintId" label="所属迭代" rules={[{ required: true, message: '请选择所属迭代' }]}>
          <Select placeholder="请选择迭代" options={sprintOptions} onChange={onSprintChange} />
        </Form.Item>
        <Form.Item name="requirementId" label="所属需求" rules={[{ required: true, message: '请选择所属需求' }]}>
          <Select placeholder="请选择需求" options={requirementOptions} disabled={requirementOptions.length === 0} />
        </Form.Item>
        <Form.Item
          name="sourceArchiveFile"
          label="源码 ZIP"
          valuePropName="file"
          getValueFromEvent={(event: React.ChangeEvent<HTMLInputElement>) => event.target.files?.[0]}
          rules={[{ validator: (_, file?: File) => {
            const validationError = validateUiSourceArchive(file)
            return validationError ? Promise.reject(new Error(validationError)) : Promise.resolve()
          } }]}
          extra={<Typography.Text type="secondary">仅接受 .zip，压缩包不超过 100 MiB；浏览器不会读取或解压源码内容。</Typography.Text>}
        >
          <input aria-label="源码 ZIP" type="file" accept=".zip,application/zip" disabled={loading} />
        </Form.Item>
        <Form.Item name="instruction" label="生成指令" extra="可选，可描述重点场景或输出约束。">
          <Input.TextArea maxLength={1000} placeholder="例如：重点覆盖登录失败和表单校验" />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
