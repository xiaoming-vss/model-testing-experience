import { useEffect, useState, type ReactNode } from 'react'
import { Button, Form, Input, Select } from 'antd'
import { RichTextEditor } from '@/shared/components/RichTextEditor'
import { extractRichTextFileIds } from '@/shared/components/RichTextEditor/utils'
import { pickCreatedAt, formatTime } from '@/utils/format'
import { useBugForm } from '../hooks/useBugForm'
import { BUG_PRIORITY_LABELS, BUG_SEVERITY_LABELS, formatBugNo } from '../utils/bugMeta'
import type { Bug } from '../types'
import { BugDetailHeader } from './BugDetailHeader'
import { BugDetailSidebar } from './BugDetailSidebar'
import { BugAttachmentUploader } from './BugAttachmentUploader'
import { BugDescriptionTemplates } from './BugDescriptionTemplates'
import { UserDisplayName } from '@/shared/components/UserReference/UserReference'

export function BugInlineEditor({ bug, projectName, sprintNames, resolveUserName, onClose, onBack, children }: {
  bug: Bug; projectName?: string; sprintNames: Map<string, string>; resolveUserName: (id: string) => string
  onClose: () => void; onBack: () => void; children?: ReactNode
}) {
  // 编辑期间缓存刷新（例如评论）不能覆盖尚未保存的表单。
  const [snapshot] = useState(bug)
  const [dirty, setDirty] = useState(false)
  const [revision, setRevision] = useState(0)
  const model = useBugForm({ open: true, bug: snapshot, projectId: snapshot.projectId, onClose, onSaved: onClose })
  const { form, descriptionHtml, setDescriptionHtml, attachments, setAttachments, saveMutation } = model
  const inlineIds = new Set(extractRichTextFileIds(snapshot.descriptionHtml))
  const existing = (snapshot.attachments ?? []).filter((item) => !inlineIds.has(item.fileId) && !model.removedAttachmentFileIds.includes(item.fileId))
  const canLeave = () => !dirty || window.confirm('有未保存的修改，确定放弃并离开吗？')

  useEffect(() => {
    if (!dirty) return
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    const linkClick = (event: MouseEvent) => {
      const link = (event.target as Element).closest?.('a[href]') as HTMLAnchorElement | null
      if (!link || link.target === '_blank' || event.ctrlKey || event.metaKey || link.href === window.location.href) return
      if (!window.confirm('有未保存的修改，确定放弃并离开吗？')) {
        event.preventDefault()
        event.stopPropagation()
      }
    }
    const historyIndex = window.history.state?.idx
    let restoringHistory = false
    const popState = (event: PopStateEvent) => {
      if (restoringHistory) { restoringHistory = false; event.stopImmediatePropagation(); return }
      const nextIndex = event.state?.idx
      if (typeof historyIndex !== 'number' || typeof nextIndex !== 'number' || nextIndex === historyIndex) return
      if (!window.confirm('有未保存的修改，确定放弃并离开吗？')) {
        event.stopImmediatePropagation()
        restoringHistory = true
        window.history.go(historyIndex - nextIndex)
      }
    }
    window.addEventListener('popstate', popState, true)
    window.addEventListener('beforeunload', beforeUnload)
    document.addEventListener('click', linkClick, true)
    return () => { window.removeEventListener('popstate', popState, true); window.removeEventListener('beforeunload', beforeUnload); document.removeEventListener('click', linkClick, true) }
  }, [dirty])

  return <Form form={form} layout="vertical" className="bug-inline-form" onValuesChange={() => setDirty(true)}
    onFinish={(values) => saveMutation.mutate(values)}>
    <BugDetailHeader bug={snapshot} onBack={() => { if (!saveMutation.isPending && canLeave()) onBack() }}
      onEdit={() => {}} onTransfer={() => {}} onTransition={() => {}}
      editingActions={<>
        <Button disabled={saveMutation.isPending} onClick={onClose}>取消</Button>
        <Button type="primary" className="bug-detail-primary-action" loading={saveMutation.isPending} onClick={() => form.submit()}>保存修改</Button>
      </>} />
    <div className="bug-detail-cols">
      <div className="bug-detail-main">
        <section className="bug-detail-panel bug-detail-summary">
          <div className="bug-detail-breadcrumb">{projectName || snapshot.projectId} / {formatBugNo(snapshot.bugNo)} · 编辑中</div>
          <Form.Item name="title" label="标题" rules={[{ required: true, whitespace: true, message: '请输入 Bug 标题' }]}>
            <Input maxLength={200} disabled={saveMutation.isPending} />
          </Form.Item>
          <div className="bug-detail-subtitle"><UserDisplayName name={resolveUserName(snapshot.reporterUserId)} /> 提交于 {formatTime(pickCreatedAt(snapshot))}</div>
        </section>
        <section className="bug-detail-panel">
          <div className="bug-description-heading"><h2 className="bug-panel-title">编辑问题描述</h2>
            <BugDescriptionTemplates value={descriptionHtml} onChange={(html) => { setDescriptionHtml(html); setRevision((value) => value + 1); setDirty(true) }} />
          </div>
          <RichTextEditor key={revision} value={descriptionHtml || snapshot.descriptionHtml} projectId={snapshot.projectId}
            disabled={saveMutation.isPending} onChange={(html) => { setDescriptionHtml(html); setDirty(true) }} ariaLabel="问题描述" />
        </section>
        <section className="bug-detail-panel"><h2 className="bug-panel-title">附件</h2>
          <BugAttachmentUploader existing={existing} items={attachments} disabled={saveMutation.isPending}
            onRemoveExisting={(fileId) => { model.setRemovedAttachmentFileIds((ids) => [...ids, fileId]); setDirty(true) }}
            onChange={(items) => { setAttachments(items); setDirty(true) }} />
        </section>
      </div>
      <BugDetailSidebar bug={snapshot} projectName={projectName} sprintNames={sprintNames} resolveUserName={resolveUserName}
        editors={{
          severity: <Form.Item name="severity"><Select aria-label="严重程度" disabled={saveMutation.isPending} options={Object.entries(BUG_SEVERITY_LABELS).map(([value, label]) => ({ value, label }))} /></Form.Item>,
          priority: <Form.Item name="priority"><Select aria-label="优先级" disabled={saveMutation.isPending} options={Object.entries(BUG_PRIORITY_LABELS).map(([value, label]) => ({ value, label }))} /></Form.Item>,
          plannedFixSprint: <Form.Item name="plannedFixSprintId"><Select aria-label="计划修复迭代" allowClear disabled={saveMutation.isPending} options={model.sprints.map((sprint) => ({ value: sprint.sprintId, label: sprint.name }))} /></Form.Item>,
          requirement: <Form.Item name="requirementId"><Select aria-label="所属需求" allowClear showSearch optionFilterProp="label" disabled={saveMutation.isPending} options={model.requirementOptions} loading={model.requirementsQuery.isLoading} /></Form.Item>,
        }}>{children}</BugDetailSidebar>
    </div>
  </Form>
}
