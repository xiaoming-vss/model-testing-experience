import { ProjectActionButton } from './ProjectActionButton'
import { Alert, Button, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Tooltip } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { projectsApi } from '../api/projects.api'
import { roleLabels, useProjectAccess } from '../hooks/useProjectAccess'
import { useWorkbenchStore } from '../store/workbench.store'
import { listItems } from '@/shared/api/request'
import { getErrorMessage } from '@/utils/format'
import type { ProjectMember } from '../types'

const roles = [{ value: 'member', label: '普通成员' }, { value: 'viewer', label: '只读成员' }]

export function ProjectMembersModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const { project, can } = useProjectAccess(projectId)
  const client = useQueryClient()
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const members = useQuery({ queryKey: ['projectMembers', projectId], queryFn: () => projectsApi.getProjectMembers(projectId) })
  const mutation = useMutation({
    mutationFn: async (operation: () => Promise<unknown>) => operation(),
    onSuccess: async () => {
      form.resetFields()
      await client.invalidateQueries()
    },
  })
  function leave() {
    mutation.mutate(async () => {
      await projectsApi.leaveProject(projectId)
      await client.cancelQueries()
      client.removeQueries()
      useWorkbenchStore.getState().setActiveProjectId(undefined)
      onClose()
      navigate('/projects')
    })
  }
  return <Modal title={`项目成员 · ${project?.name ?? ''}`} open onCancel={onClose} width={700} footer={null}>
    {members.error || mutation.error ? <Alert type="error" showIcon title={getErrorMessage(members.error || mutation.error)} /> : null}
    <Form disabled={!can('manage')} form={form} layout="inline" initialValues={{ role: 'member' }} onFinish={(values) => mutation.mutate(() => projectsApi.addProjectMember(projectId, values))} style={{ marginBottom: 20 }}>
      <Form.Item name="name" rules={[{ required: true, whitespace: true, message: '请输入已注册的准确用户名' }]}><Input placeholder="已注册的准确用户名" aria-label="成员用户名" /></Form.Item>
      <Form.Item name="role"><Select options={roles} aria-label="新成员角色" /></Form.Item>
      <ProjectActionButton action="manage" projectId={projectId} htmlType="submit" type="primary" loading={mutation.isPending}>添加成员</ProjectActionButton>
    </Form>
    <Table<ProjectMember> rowKey="userId" dataSource={listItems(members.data)} loading={members.isLoading} pagination={false} columns={[
      { title: '用户名', dataIndex: 'name' },
      { title: '角色', render: (_, member) => member.role !== 'owner'
        ? <Tooltip title={can('manage') ? undefined : '仅项目所有者可以操作'}><span><Select aria-label={`${member.name}的角色`} value={member.role} options={roles} disabled={!can('manage') || mutation.isPending} onChange={(role) => mutation.mutate(() => projectsApi.updateProjectMember(projectId, member.userId, role))} /></span></Tooltip>
        : <Tag>{roleLabels[member.role]}</Tag> },
      { title: '操作', render: (_, member) => member.role !== 'owner' ? <Space>
        <Popconfirm disabled={!can('manage')} title={`将所有权转移给 ${member.name}？`} description="你将成为普通成员，无法再管理项目和绑定。" onConfirm={() => mutation.mutate(() => projectsApi.transferProjectOwnership(projectId, member.userId))}>
          <ProjectActionButton action="manage" projectId={projectId} disabled={mutation.isPending}>转移所有权</ProjectActionButton>
        </Popconfirm>
        <Popconfirm disabled={!can('manage')} title={`移除 ${member.name}？`} description="成员将失去访问权限，其未完成任务会失败。" onConfirm={() => mutation.mutate(() => projectsApi.removeProjectMember(projectId, member.userId))}>
          <ProjectActionButton action="manage" projectId={projectId} danger disabled={mutation.isPending}>移除</ProjectActionButton>
        </Popconfirm>
      </Space> : null },
    ]} />
    {project?.role && project.role !== 'owner' ? <Popconfirm title="退出此项目？" description="你将无法访问项目资产，未完成任务会失败。" onConfirm={leave}>
      <Button danger disabled={mutation.isPending} style={{ marginTop: 20 }}>退出项目</Button>
    </Popconfirm> : null}
  </Modal>
}
