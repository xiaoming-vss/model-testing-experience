import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Modal, Radio, Select, Space, Table, Tag, Typography } from 'antd'
import { getErrorMessage } from '@/utils/format'
import { message } from '@/shared/utils/feedback'
import { bugsApi } from '../api/bugs.api'
import type { ZentaoRemoteGroup, ZentaoRemotePreview } from '../types'
import { BUG_PRIORITY_LABELS, BUG_RESOLUTION_LABELS, BUG_SEVERITY_LABELS, BUG_STATUS_LABELS } from '../utils/bugMeta'

type Props = {
  open: boolean
  bugId: string
  projectId?: string
  onClose: () => void
}

const GROUP_LABELS: Record<string, string> = {
  profile: '基本信息',
  description: '描述',
  status: '状态',
  assignee: '责任人',
}

const STATE_LABELS: Record<string, { label: string; color: string }> = {
  synced: { label: '一致', color: 'green' },
  remote_changed: { label: '禅道有变化', color: 'blue' },
  local_changed: { label: '本地未推送', color: 'amber' },
  conflict: { label: '两端冲突', color: 'red' },
  confirm_baseline: { label: '待建立基线', color: 'default' },
  pending_files: { label: '图片待文件管线', color: 'default' },
  pending_map: { label: '待映射', color: 'default' },
  manual: { label: '需人工映射', color: 'default' },
}

const valueText = (value: unknown) => (value === undefined || value === null || value === '' ? '—' : String(value))

function groupValues(group: ZentaoRemoteGroup): { local: string; remote: string } {
  if (group.group === 'profile') {
    const text = (side: Record<string, unknown>) =>
      `${valueText(side.title)} / ${BUG_SEVERITY_LABELS[String(side.severity)] || valueText(side.severity)} / ${BUG_PRIORITY_LABELS[String(side.priority)] || valueText(side.priority)}`
    return { local: text(group.local), remote: text(group.remote) }
  }
  if (group.group === 'description') {
    return { local: '平台正文', remote: group.remote.hasImages ? '含图片（待文件管线）' : '禅道正文' }
  }
  if (group.group === 'status') {
    const text = (side: Record<string, unknown>) =>
      `${BUG_STATUS_LABELS[String(side.status)] || valueText(side.status)}${side.confirmed ? ' · 已确认' : ''} / ${BUG_RESOLUTION_LABELS[String(side.resolution)] || valueText(side.resolution)}${side.resolvedBuild ? ` · ${side.resolvedBuild}` : ''}`
    return { local: text(group.local), remote: text(group.remote) }
  }
  const text = (side: Record<string, unknown>) => valueText(group.group === 'assignee' ? side.account ?? side.userId : side)
  return { local: text(group.local), remote: text(group.remote) }
}

type Choice = 'keep_local' | 'apply_remote'

export function BugZentaoPullModal({ open, bugId, projectId, onClose }: Props) {
  const client = useQueryClient()
  const [choices, setChoices] = useState<Record<string, Choice>>({})
  const [assignee, setAssignee] = useState('')
  const [severityOverrides, setSeverityOverrides] = useState<Record<string, string>>({})
  const [priorityOverrides, setPriorityOverrides] = useState<Record<string, string>>({})
  const preview = useQuery({
    queryKey: ['bugZentaoRemote', bugId, open],
    queryFn: () => bugsApi.getBugZentaoRemote(bugId),
    enabled: open && !!bugId,
    staleTime: 0,
    refetchOnWindowFocus: false,
  })
  const options = useQuery({
    queryKey: ['bugOptionsForPull', projectId],
    queryFn: () => bugsApi.getBugOptions(projectId!),
    enabled: open && !!projectId,
    staleTime: 0,
    refetchOnWindowFocus: false,
  })
  const members = options.data?.members ?? []
  const pull = useMutation({
    mutationFn: (data: ZentaoRemotePreview) => bugsApi.pullBugZentao(bugId, {
      remoteDigest: data.remoteDigest,
      groups: data.groups.map((group) => ({
        group: group.group,
        action: choices[group.group] ?? 'keep_local',
        ...(group.group === 'assignee' && choices[group.group] === 'apply_remote' ? { assigneeUserId: assignee } : {}),
        ...(choices[group.group] === 'apply_remote' && severityOverrides[group.group]
          ? { severity: severityOverrides[group.group] }
          : {}),
        ...(choices[group.group] === 'apply_remote' && priorityOverrides[group.group]
          ? { priority: priorityOverrides[group.group] }
          : {}),
      })),
    }),
    onSuccess: (result) => {
      message.success(`已应用 ${result.applied.length} 组，保留 ${result.kept.length} 组`)
      void client.invalidateQueries({ queryKey: ['bugZentaoPush', bugId] })
      void client.invalidateQueries({ queryKey: ['bugDetail', bugId] })
      void client.invalidateQueries({ queryKey: ['bugActivities', bugId] })
      onClose()
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const data = preview.data
  const actionable = (data?.groups ?? []).filter((group) =>
    ['remote_changed', 'confirm_baseline', 'conflict'].includes(group.state),
  )
  const canConfirm = !!data && data.groups.every((group) => {
    const choice = choices[group.group] ?? 'keep_local'
    if (group.group !== 'assignee' || choice !== 'apply_remote') return true
    return !!assignee
  })
  const close = () => {
    if (pull.isPending) return
    setChoices({})
    setAssignee('')
    onClose()
  }
  const columns = [
    { title: '字段组', dataIndex: 'group', width: 90, render: (value: string) => GROUP_LABELS[value] || value },
    {
      title: '状态',
      dataIndex: 'state',
      width: 120,
      render: (value: string) => {
        const meta = STATE_LABELS[value] || { label: value, color: 'default' }
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '平台当前值',
      key: 'local',
      render: (_: unknown, group: ZentaoRemoteGroup) => (
        <Typography.Text style={{ maxWidth: 220 }} ellipsis={{ tooltip: groupValues(group).local }}>
          {groupValues(group).local}
        </Typography.Text>
      ),
    },
    {
      title: '禅道当前值',
      key: 'remote',
      render: (_: unknown, group: ZentaoRemoteGroup) => (
        <Typography.Text style={{ maxWidth: 220 }} ellipsis={{ tooltip: groupValues(group).remote }}>
          {groupValues(group).remote}
        </Typography.Text>
      ),
    },
    {
      title: '本次选择',
      key: 'choice',
      width: 220,
      render: (_: unknown, group: ZentaoRemoteGroup) => {
        if (['synced', 'pending_files', 'pending_map', 'local_changed'].includes(group.state)) {
          return <Typography.Text type="secondary">无需处理</Typography.Text>
        }
        return (
          <Radio.Group
            aria-label={`同步方向-${GROUP_LABELS[group.group] || group.group}`}
            size="small"
            value={choices[group.group] ?? 'keep_local'}
            onChange={(event) => setChoices((current) => ({ ...current, [group.group]: event.target.value }))}
            options={[
              { value: 'apply_remote', label: '应用禅道' },
              { value: 'keep_local', label: '保留平台' },
            ]}
          />
        )
      },
    },
  ]
  return (
    <Modal
      mask={{ closable: false }}
      centered
      title="从禅道同步"
      open={open}
      width={860}
      onCancel={close}
      footer={
        <Space>
          <Button onClick={close}>取消</Button>
          <Button
            type="primary"
            loading={pull.isPending}
            disabled={!canConfirm || (!actionable.length && !data?.groups.some((group) => group.state === 'manual'))}
            onClick={() => data && pull.mutate(data)}
          >
            确认同步
          </Button>
        </Space>
      }
    >
      <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
        {preview.error && (
          <Alert showIcon type="error" title={getErrorMessage(preview.error)}
            action={<Button onClick={() => preview.refetch()}>重新加载</Button>} />
        )}
        {data && (
          <Alert
            type="info"
            showIcon
            title={`禅道 Bug #${data.remoteBugId}（关联来源：${data.linkedSource === 'import' ? '禅道导入' : '平台推送'}）`}
            description="按字段组比较上次同步基线与两端当前值；冲突由你逐组选择，应用只更新平台数据，不会修改禅道。"
          />
        )}
        {data && actionable.length === 0 && (
          <Alert type="success" showIcon title="所有字段组与禅道一致，或暂无可应用的差异。" />
        )}
        {data && (
          <Table<ZentaoRemoteGroup>
            size="small"
            rowKey="group"
            loading={preview.isFetching}
            columns={columns}
            dataSource={data.groups}
            pagination={false}
            defaultExpandAllRows
            expandable={{
              rowExpandable: (group) =>
                ['pending_map', 'manual', 'remote_changed', 'conflict', 'confirm_baseline'].includes(group.state),
              expandedRowRender: (group) => (
                <Space orientation="vertical" size="small" style={{ width: '100%' }}>
                  {group.reason && <Typography.Text type="secondary">{group.reason}</Typography.Text>}
                  {group.state === 'manual' && (
                    <Select
                      aria-label="映射平台责任人"
                      placeholder="选择平台责任人后可应用禅道值"
                      style={{ width: 220 }}
                      showSearch
                      optionFilterProp="label"
                      value={assignee || undefined}
                      options={members.map((member) => ({ value: member.userId, label: member.name || member.userId }))}
                      onChange={(value) => setAssignee(value ?? '')}
                    />
                  )}
                  {group.state === 'pending_map' && group.group === 'profile' && (
                    <Space wrap>
                      <Select
                        aria-label="指定平台严重程度"
                        placeholder="指定严重程度"
                        style={{ width: 160 }}
                        value={severityOverrides[group.group] || undefined}
                        options={Object.entries(BUG_SEVERITY_LABELS).map(([value, label]) => ({ value, label }))}
                        onChange={(value) => setSeverityOverrides((current) => ({ ...current, [group.group]: value ?? '' }))}
                      />
                      <Select
                        aria-label="指定平台优先级"
                        placeholder="指定优先级"
                        style={{ width: 160 }}
                        value={priorityOverrides[group.group] || undefined}
                        options={Object.entries(BUG_PRIORITY_LABELS).map(([value, label]) => ({ value, label }))}
                        onChange={(value) => setPriorityOverrides((current) => ({ ...current, [group.group]: value ?? '' }))}
                      />
                    </Space>
                  )}
                </Space>
              ),
            }}
          />
        )}
      </Space>
    </Modal>
  )
}
