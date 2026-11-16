import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/task-form.css'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { Alert, Drawer, Form, Input, Select } from 'antd'
import type { FormInstance } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import type { CreateCodeRiskTaskPayload } from '../types'
import { listItems } from '@/services/api'
import { interfaceLibraryApi } from '@/features/interface-library/api/interfaceLibrary.api'
import { getErrorMessage } from '@/utils/format'

export type CodeRiskTaskFormValues = CreateCodeRiskTaskPayload & {
  sprintId?: string
}

export function CodeRiskTaskDrawer({
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
  form: FormInstance<CodeRiskTaskFormValues>
  loading: boolean
  error: unknown
  sprintOptions: Array<{ label: string; value: string }>
  requirementOptions: Array<{ label: string; value: string }>
  onSprintChange: (value?: string) => void
  onClose: () => void
  onFinish: (values: CreateCodeRiskTaskPayload) => void
}) {
  const requirementId = Form.useWatch('requirementId', form)
  const bindingsQuery = useQuery({
    queryKey: ['requirementSoftwareRepositories', requirementId],
    queryFn: () => interfaceLibraryApi.getRequirementSoftwareRepositories(requirementId!),
    enabled: open && Boolean(requirementId),
  })
  const bindings = useMemo(
    () => (bindingsQuery.data ? listItems(bindingsQuery.data) : []),
    [bindingsQuery.data],
  )
  const hasCodeBindings = bindingsQuery.data ? bindings.length > 0 : true
  const hasRunnableBindings = bindingsQuery.data
    ? bindings.some(binding => binding.branch.trim() && binding.baselineBranch.trim())
    : true
  const bindingsLoading = bindingsQuery.isLoading
  const saveDisabled = Boolean(requirementId) && (bindingsLoading || !hasRunnableBindings)

  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      size={640}
      rootClassName="ai-task-generate-drawer"
      destroyOnHidden={false}
      extra={
        <ProjectActionButton operation="save" action="write" type="primary" className="action-btn-save" loading={loading} disabled={saveDisabled} onClick={() => form.submit()}>
          保存
        </ProjectActionButton>
      }
    >
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} style={{ marginBottom: 16 }} /> : null}
      <Form<CodeRiskTaskFormValues>
        className="ai-task-drawer-form"
        form={form}
        layout="vertical"
        onFinish={(values) =>
          onFinish({
            name: (values.name ?? '').trim(),
            requirementId: values.requirementId,
            instruction: values.instruction?.trim() ?? '',
          })
        }
        requiredMark={false}
      >
        <div className="ai-task-drawer-basic-grid">
          <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称' }]}>
            <Input maxLength={120} placeholder="例如：登录模块代码风险分析" />
          </Form.Item>
          <Form.Item name="sprintId" label="所属迭代">
            <Select allowClear placeholder="可先选择迭代筛选需求" options={sprintOptions} onChange={onSprintChange} />
          </Form.Item>
          <Form.Item name="requirementId" label="所属需求" rules={[{ required: true, message: '请选择所属需求' }]}>
            <Select showSearch placeholder="请选择需求" options={requirementOptions} optionFilterProp="label" />
          </Form.Item>
        </div>

        <Form.Item name="instruction" label="补充指令" extra="可选，描述希望重点分析的代码变更或风险范围。">
          <Input.TextArea
            className="ai-task-instruction-textarea"
            maxLength={1000}
            placeholder="例如：重点分析鉴权相关变更的影响面"
          />
        </Form.Item>

        {requirementId && !bindingsLoading && !hasCodeBindings ? (
          <Alert
            showIcon
            type="warning"
            title="该需求未关联任何软件仓库"
            description="请先在需求列表对该需求进行「软件仓库」关联，再创建代码风险分析任务。"
          />
        ) : null}
        {requirementId && !bindingsLoading && hasCodeBindings && !hasRunnableBindings ? (
          <Alert
            showIcon
            type="warning"
            title="软件仓库关联缺少分支"
            description="请先为需求关联的软件仓库重新设置工作分支和基线分支，再创建代码风险分析任务。"
          />
        ) : null}
      </Form>
    </Drawer>
  )
}
