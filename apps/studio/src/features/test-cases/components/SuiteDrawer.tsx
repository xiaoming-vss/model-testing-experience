import { Drawer, Form, Input, Select } from 'antd'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { normalizeRequirementId, normalizeSprintId } from '@/utils/format'
import type { CaseLibraryPageModel } from '../hooks/useCaseLibraryPage'

export function SuiteDrawer({ page }: { page: CaseLibraryPageModel }) {
  const {
    editingSuite,
    suiteDrawerOpen,
    setSuiteDrawerOpen,
    setEditingSuite,
    suiteForm,
    sprints,
    suiteDrawerRequirements,
    allRequirementsQuery,
    setSuiteDrawerSprintId,
    saveSuiteMutation,
  } = page

  return (
    <Drawer
      title={editingSuite ? '编辑功能测试集' : '新建功能测试集'}
      open={suiteDrawerOpen}
      onClose={() => {
        setSuiteDrawerOpen(false)
        setEditingSuite(null)
      }}
      size={520}
      extra={
        <ProjectActionButton
          action="write"
          type="primary"
          className="action-btn-save"
          onClick={() => suiteForm.submit()}
        >
          {saveSuiteMutation.isPending ? '保存中...' : '保存'}
        </ProjectActionButton>
      }
    >
      <Form
        form={suiteForm}
        layout="vertical"
        requiredMark={false}
        onFinish={(values) => saveSuiteMutation.mutate(values)}
      >
        <Form.Item
          label="所属迭代"
          name="sprintId"
          rules={[{ required: true, message: '请选择迭代' }]}
        >
          <Select
            options={sprints.map((sprint) => ({
              label: sprint.name,
              value: normalizeSprintId(sprint),
            }))}
            placeholder="请选择迭代"
            disabled={Boolean(editingSuite)}
            onChange={(value: string) => {
              setSuiteDrawerSprintId(value)
              suiteForm.setFieldsValue({ requirementId: undefined })
            }}
          />
        </Form.Item>
        <Form.Item
          label="所属需求"
          name="requirementId"
          rules={[{ required: true, message: '请选择需求' }]}
        >
          <Select
            options={suiteDrawerRequirements.map((requirement) => ({
              label: requirement.name,
              value: normalizeRequirementId(requirement),
            }))}
            loading={allRequirementsQuery.isLoading}
            placeholder="请选择需求"
            disabled={Boolean(editingSuite)}
          />
        </Form.Item>
        <Form.Item
          label="测试集名称"
          name="name"
          rules={[{ required: true, message: '请输入测试集名称' }]}
        >
          <Input placeholder="例如：登录与鉴权" maxLength={100} />
        </Form.Item>
        <Form.Item label="描述" name="description">
          <Input.TextArea rows={3} placeholder="例如：登录主流程 / 订单核心链路" maxLength={512} />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
