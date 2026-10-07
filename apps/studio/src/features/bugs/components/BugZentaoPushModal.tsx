import type { UseQueryResult } from '@tanstack/react-query'
import { Alert, Button, Descriptions, Modal, Select } from 'antd'
import { getErrorMessage } from '@/utils/format'
import type { BugZentaoPush, BugZentaoPushOptions } from '../types'

type Props = {
  open: boolean
  data?: BugZentaoPush
  busy: boolean
  pending: boolean
  canConfirm: boolean
  choicesValid: boolean
  fieldsChanged: boolean
  retrySync?: boolean
  openedBuild: string[]
  assignedTo: string
  setOpenedBuild: (values: string[]) => void
  setAssignedTo: (value: string) => void
  setOpen: (value: boolean) => void
  onConfirm: () => void
  options: UseQueryResult<BugZentaoPushOptions, Error>
}

export function BugZentaoPushModal({
  open, data, busy, pending, canConfirm, choicesValid, fieldsChanged, retrySync,
  openedBuild, assignedTo, setOpenedBuild, setAssignedTo, setOpen, onConfirm, options,
}: Props) {
  const existing = data?.status === 'succeeded'
  const targetName = (name?: string, id?: number) => id ? `${name || '未命名'} (#${id})` : '未确定'
  return (
    <Modal title="推送到禅道" open={open} okText="确认推送" cancelText="取消"
      confirmLoading={pending} onCancel={() => !busy && setOpen(false)}
      okButtonProps={{ disabled: !canConfirm }}
      onOk={() => canConfirm && onConfirm()}>
      <Descriptions column={1} size="small" items={[
        { key: 'project', label: '禅道项目', children: targetName(data?.target.projectName, data?.target.project) },
        { key: 'execution', label: '禅道执行', children: targetName(data?.target.executionName, data?.target.execution) },
        { key: 'story', label: '禅道需求', children: targetName(data?.target.storyName, data?.target.story) },
        { key: 'build', label: '影响版本', children: <Select
          aria-label="禅道影响版本" mode="multiple" style={{ width: '100%' }}
          placeholder="请选择影响版本" loading={options.isFetching} disabled={busy || options.isFetching || !!options.error}
          value={openedBuild} optionFilterProp="label"
          options={options.data?.builds.map((build) => ({ value: build.id, label: build.name }))}
          onChange={(values: string[]) => setOpenedBuild(values.includes('trunk') && values.length > 1
            ? openedBuild.includes('trunk') ? values.filter((id) => id !== 'trunk') : ['trunk']
            : values)} /> },
        { key: 'assignee', label: '禅道指派人', children: <Select
          aria-label="禅道指派人" showSearch allowClear style={{ width: '100%' }}
          placeholder="请选择，可按姓名或账号搜索" loading={options.isFetching} disabled={busy || options.isFetching || !!options.error}
          value={assignedTo || undefined} optionFilterProp="label"
          options={options.data?.users.map((user) => ({ value: user.account, label: `${user.name} (${user.account})` }))}
          onChange={(value?: string) => setAssignedTo(value ?? '')} /> },
      ]} />
      {options.error && <Alert type="error" showIcon title={getErrorMessage(options.error)}
        action={<Button onClick={() => options.refetch()}>重新加载候选项</Button>} />}
      {options.data && !options.isFetching && !options.error && !choicesValid && <Alert
        type="warning" showIcon title="请选择有效的影响版本和禅道指派人；候选项可能已发生变化。" />}
      <Alert type="info" showIcon title={existing ? data?.descriptionStatus === 'unknown' ? '先核对正文图片结果；确认旧图片地址错误后会修复引用，不重复上传文件。' : retrySync ? '补传未成功的附件及正文图片，沿用已关联的禅道 Bug。' : `同步到已关联的禅道 Bug #${data?.remoteBugId}。` : '将根据现有绑定在禅道创建一个新 Bug，并同步附件和正文图片。'}
        description={existing ? data?.executionMode === 'worker' && fieldsChanged && retrySync
          ? '本次先修改版本和指派人；成功后继续补传附件和正文图片。平台责任人保持原值。'
          : '影响版本和指派人显示禅道当前值，修改后随本次推送更新；平台责任人保持原值。'
          : data?.warnings.join(' ')} />
    </Modal>
  )
}
