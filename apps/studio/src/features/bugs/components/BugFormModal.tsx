import { extractRichTextFileIds } from '@/shared/components/RichTextEditor/utils'
import { useState } from 'react'
import { Button, Form, Input, Modal, Segmented, Select } from 'antd'
import { BugOutlined, FolderOutlined, LockOutlined, UploadOutlined } from '@ant-design/icons'
import { RichTextEditor } from '@/shared/components/RichTextEditor'
import { api, listItems } from '@/services/api'
import { PagedSelect } from '@/shared/components/PagedSelect'
import type { BugFormProps } from '../types'
import { BUG_PRIORITY_LABELS, BUG_SEVERITY_LABELS, formatBugNo } from '../utils/bugMeta'
import { BugDescriptionTemplates } from './BugDescriptionTemplates'
import { BugAttachmentUploader } from './BugAttachmentUploader'
import { useBugForm } from '../hooks/useBugForm'
import bugStyles from '../styles/bugs.module.css'

const SEVERITY_OPTIONS = Object.entries(BUG_SEVERITY_LABELS).map(([value, label]) => ({ value, label }))
const PRIORITY_OPTIONS = Object.entries(BUG_PRIORITY_LABELS).map(([value, label]) => ({ value, label }))

export function BugFormModal(props: BugFormProps) {
  const { open, bug, source, onClose } = props
  const [templateRevision, setTemplateRevision] = useState(0)
  const { form, isEdit, descriptionHtml, setDescriptionHtml, attachments, setAttachments,
    activeProjectId, projectsQuery, sprintsQuery, sprints, memberOptions, membersQuery,
    requirementOptions, requirementsQuery, selectedOrderId,
    saveMutation } = useBugForm(props)
  const inlineFileIds = new Set(extractRichTextFileIds(bug?.descriptionHtml ?? ''))
  const existingAttachments = (bug?.attachments ?? []).filter((item) => !inlineFileIds.has(item.fileId))
  const attachmentCount = existingAttachments.length + attachments.length
  const severity = Form.useWatch('severity', form)
  const foundSprintId = Form.useWatch('foundSprintId', form)
  const foundSprintName = sprints.find((sprint) => sprint.sprintId === foundSprintId)?.name
  const projectName = listItems(projectsQuery.data).find((project) => project.projectId === activeProjectId)?.name
  const sprintOptions = sprints.map((sprint) => ({ label: sprint.name, value: sprint.sprintId }))

  return (
    <Modal open={open} onCancel={onClose} width={1024} centered mask={{ closable: false }}
      rootClassName={`tp-surface bug-form-modal ${bugStyles.root}`}
      title={<div className="bug-form-heading flex items-start gap-3 pr-7">
        <span className="bug-form-heading-icon flex h-9 w-9 flex-[0_0_36px] items-center justify-center rounded-[8px] bg-[var(--srf-accent-soft)] text-[22px] text-[var(--srf-accent)]"><BugOutlined /></span>
        <div><div className="bug-form-title-line flex flex-wrap items-center gap-2.5"><h2 className="mb-1 mt-0 text-[18px] leading-[24px] text-[var(--srf-text)]">{isEdit ? `编辑 ${formatBugNo(bug!.bugNo)}` : '新建缺陷 (New Bug)'}</h2>
          {foundSprintName ? <span className="bug-form-sprint-badge rounded-[4px] bg-[var(--srf-count-badge)] px-2 py-0.5 text-[11px] leading-[18px] text-[var(--srf-accent-strong)]">发现迭代 · {foundSprintName}</span> : null}</div>
          <p className="m-0 text-xs font-normal leading-[18px] text-[var(--srf-text-muted)]">{source ? '测试单与执行记录已自动关联，请补充问题信息。' : '清晰记录问题现象与复现步骤，帮助团队快速定位与修复。'}</p>
        </div>
      </div>}
      footer={<div className="bug-form-footer flex items-center justify-between gap-4 max-[480.01px]:justify-end">
        <span className="bug-form-footer-hint text-left text-xs text-[var(--srf-text-muted)] max-[480.01px]:hidden">{isEdit ? '修改记录将保存在缺陷动态中' : '提交后可在详情中跟进处理进度'}</span>
        <div className="bug-form-footer-actions flex flex-none gap-2">
          <Button onClick={onClose} disabled={saveMutation.isPending}>取消</Button>
          <Button type="primary" className="bug-form-submit min-w-40" aria-label={isEdit ? '保存修改' : '立即提交缺陷'} icon={<UploadOutlined />} disabled={!activeProjectId} loading={saveMutation.isPending}
            onClick={() => form.submit()}>{isEdit ? '保存修改' : '立即提交缺陷'}</Button>
        </div>
      </div>}
    >
      <Form form={form} layout="vertical" requiredMark onFinish={(values) => saveMutation.mutate(values)}>
        <div className="bug-form-row bug-form-row-two grid grid-cols-2 gap-3 max-[480.01px]:grid-cols-1 [&>*]:min-w-0">
          <Form.Item label="归属项目" required>
            <div className="bug-form-project flex min-h-8 cursor-default items-center gap-2 rounded-[6px] border border-[var(--srf-card-border)] bg-[var(--srf-accent-soft)] px-3 py-1 text-[var(--srf-text)]" aria-label="归属项目（只读）" title={projectName || activeProjectId}>
              <FolderOutlined className="bug-form-project-icon text-[var(--srf-accent)]" />
              <span className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap">{projectName || (projectsQuery.isLoading ? '加载中…' : activeProjectId || '未选择项目')}</span>
              <LockOutlined className="bug-form-project-lock ml-auto text-[var(--srf-text-muted)]" aria-label="项目不可切换" />
            </div>
          </Form.Item>
          <Form.Item label="发现迭代" name="foundSprintId" rules={[{ required: !isEdit, message: '请选择发现迭代' }]}>
            <Select options={sprintOptions} loading={sprintsQuery.isLoading} placeholder="问题在哪个迭代发现"
              disabled={isEdit || Boolean(source)}
              onChange={(value) => {
                if (!form.isFieldTouched('plannedFixSprintId')) form.setFieldValue('plannedFixSprintId', value)
              }} />
          </Form.Item>
        </div>
        <Form.Item label="缺陷标题" name="title" rules={[{ required: true, whitespace: true, message: '请输入 Bug 标题' }]}>
          <Input placeholder="[模块 / 场景] 触发条件 + 问题现象" maxLength={200} />
        </Form.Item>
        <div className="bug-form-row bug-form-row-four grid grid-cols-4 gap-3 max-[760.01px]:grid-cols-2 max-[480.01px]:grid-cols-1 [&>*]:min-w-0">
          <Form.Item label="责任人" name="assigneeUserId" rules={[{ required: !isEdit, message: '请选择责任人' }]}>
            <Select showSearch optionFilterProp="label" options={memberOptions} loading={membersQuery.isLoading}
              placeholder="选择责任人" disabled={isEdit} />
          </Form.Item>
          <Form.Item label="严重程度" name="severity" className={`bug-form-severity${severity === 'critical' || severity === 'serious' ? ' is-severe' : ''}`}><Segmented block options={SEVERITY_OPTIONS} /></Form.Item>
          <Form.Item label="优先级" name="priority" className="bug-form-priority"><Segmented block options={PRIORITY_OPTIONS} /></Form.Item>
          <Form.Item label="计划修复迭代" name="plannedFixSprintId">
            <Select allowClear options={sprintOptions} loading={sprintsQuery.isLoading} placeholder="暂未安排" />
          </Form.Item>
        </div>
        <div className="bug-form-row bug-form-row-two grid grid-cols-2 gap-3 max-[480.01px]:grid-cols-1 [&>*]:min-w-0">
          <Form.Item label="关联所属需求" name="requirementId">
            <Select showSearch allowClear optionFilterProp="label" options={requirementOptions}
              loading={requirementsQuery.isLoading} placeholder="选择关联需求（可选）" />
          </Form.Item>
          {!isEdit && !source ? <Form.Item label="关联测试单" name="sourceOrderId">
            <PagedSelect placeholder="选择测试单（可选）" disabled={!open || !activeProjectId}
              scopeKey={activeProjectId ?? ''} queryKey={['testOrders', activeProjectId, 'forBug']}
              onChange={() => form.setFieldValue('sourceEntryId', undefined)}
              loadPage={async (page, keyword) => {
                const result = await api.getProjectTestOrders(activeProjectId!, { page, pageSize: 20, keyword })
                return { total: result.total, page: result.page, items: listItems(result).map((item) => ({ label: item.name, value: item.orderId! })) }
              }} />
          </Form.Item> : null}
        </div>
        {!isEdit && !source && selectedOrderId ? <Form.Item label="关联执行记录" name="sourceEntryId">
          <PagedSelect placeholder="选择测试单中的执行条目" disabled={!open}
            scopeKey={selectedOrderId} queryKey={['testOrderEntries', selectedOrderId, 'forBug']}
            loadPage={async (page, keyword) => {
              const result = await api.getTestOrderEntries(selectedOrderId, { page, pageSize: 20, keyword })
              return { total: result.total, page: result.page, items: listItems(result).map((item) => ({ label: item.caseTitle || item.caseId || '', value: item.entryId! })) }
            }} />
        </Form.Item> : null}
        <div className="bug-description-heading mb-1.5 flex flex-wrap items-center justify-between gap-2">
          <span className="bug-description-label text-[13px] text-[var(--srf-text)]">问题描述与复现细节 <span className="text-[var(--srf-danger)]" aria-hidden="true">*</span></span>
          <BugDescriptionTemplates value={descriptionHtml} onChange={(html) => {
            setDescriptionHtml(html)
            setTemplateRevision((revision) => revision + 1)
          }} />
        </div>
        <Form.Item className="bug-form-description">
          <RichTextEditor key={templateRevision} value={descriptionHtml} onChange={setDescriptionHtml} projectId={activeProjectId} ariaLabel="问题描述" />
          <span className="bug-form-field-hint mt-1.5 block text-xs text-[var(--srf-text-muted)]">建议包含复现步骤、实际结果和预期结果，支持粘贴截图。</span>
        </Form.Item>
        <Form.Item label={`附件与日志凭据${attachmentCount ? `（共 ${attachmentCount} 个）` : ''}`} className="bug-form-attachments mb-0">
          <BugAttachmentUploader existing={existingAttachments} items={attachments} onChange={setAttachments} disabled={saveMutation.isPending} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
