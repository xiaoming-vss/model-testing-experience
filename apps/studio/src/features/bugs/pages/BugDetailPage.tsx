import { BugDetailPanel } from '../components/BugDetailPanel'
import { ArrowLeftOutlined, SendOutlined } from '@ant-design/icons'
import { Alert, Button, Input } from 'antd'
import { BugDescriptionView } from '../components/BugDescriptionView'
import { BugEvidencePanel } from '../components/BugEvidencePanel'
import { pickCreatedAt, formatTime } from '@/utils/format'
import { formatBugNo } from '../utils/bugMeta'
import { getErrorMessage } from '@/utils/format'
import { BugActivityFeed } from '../components/BugActivityFeed'
import { BugInlineEditor } from '../components/BugInlineEditor'
import { BugTransferModal } from '../components/BugTransferModal'
import { BugTransitionModal } from '../components/BugTransitionModal'
import { BugDetailSidebar } from '../components/BugDetailSidebar'
import { UserDisplayName } from '@/shared/components/UserReference/UserReference'
import { goBackOrFallback } from '@/shared/utils/backNavigation'
import { BugDetailHeader } from '../components/BugDetailHeader'
import { BugZentaoPushPanel } from '../components/BugZentaoPushPanel'
import { useBugDetail } from '../hooks/useBugDetail'
import '@/shared/styles/surface-tokens.css'
import styles from '../styles/bugs.module.css'

export function BugDetailPage() {
  const { navigate, bugQuery, bug, activitiesQuery, statusChanges, dynamics, resolveUserName,
    sprintNames, projectQuery, canRead, canWrite, canHandle, comment, setComment, commentMutation, downloadAttachment,
    transitionAction, setTransitionAction, transferOpen, setTransferOpen, editOpen, setEditOpen } = useBugDetail()

  if (bugQuery.isLoading) {
    return (
      <div className={`workbench-page bugs-detail-page tp-surface ${styles.root}`}>
        <div className="api-automation-content">
          <Alert type="info" showIcon title="Bug 加载中..." />
        </div>
      </div>
    )
  }
  if (bugQuery.error || !bug) {
    return (
      <div className={`workbench-page bugs-detail-page tp-surface ${styles.root}`}>
        <div className="api-automation-content">
          <Alert
            showIcon
            type="error"
            title={bugQuery.error ? getErrorMessage(bugQuery.error) : 'Bug 不存在或已被删除'}
          />
          <Button className="bug-back-button" icon={<ArrowLeftOutlined />} onClick={() => goBackOrFallback(navigate, '/testing?tab=bugs')}>
            返回 Bug 列表
          </Button>
        </div>
      </div>
    )
  }


  const activityPanels = <>
            <BugDetailPanel className="bug-detail-history col-span-full">
              <h2 className="bug-panel-title mb-4 flex items-center gap-2 border-b border-[var(--srf-divider)] pb-3 text-[14px] font-semibold text-[var(--srf-text)]">处理记录 <span className="bug-section-count text-xs font-normal text-[var(--srf-text-muted)]">{statusChanges.length}</span></h2>
              {activitiesQuery.error && <Alert type="error" showIcon title="处理记录加载失败" action={<Button onClick={() => activitiesQuery.refetch()}>重试</Button>} />}
              <BugActivityFeed
                items={statusChanges}
                resolveUserName={resolveUserName}
                emptyText="还没有流转记录"
              />
            </BugDetailPanel>
            <BugDetailPanel className="bug-detail-discussion col-span-full">
              <h2 className="bug-panel-title mb-4 flex items-center gap-2 border-b border-[var(--srf-divider)] pb-3 text-[14px] font-semibold text-[var(--srf-text)]">评论与动态</h2>
              <div className="bug-comment-composer mb-2.5">
                <Input
                  aria-label="评论输入框"
                  placeholder="写下评论，回车发送"
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  disabled={!canHandle}
                  onPressEnter={(event) => { event.preventDefault(); if (canHandle && !commentMutation.isPending && comment.trim()) commentMutation.mutate() }}
                  suffix={
                    <Button
                      type="text"
                      size="small"
                      aria-label="发送评论"
                      icon={<SendOutlined />}
                      loading={commentMutation.isPending}
                      disabled={!canHandle || !comment.trim()}
                      onClick={() => comment.trim() && commentMutation.mutate()}
                    />
                  }
                />
              </div>
              <BugActivityFeed items={dynamics} resolveUserName={resolveUserName} emptyText="还没有评论与动态" />
            </BugDetailPanel>
  </>
  if (editOpen && canWrite) return <div className={`workbench-page bugs-detail-page tp-surface ${styles.root}`}><div className="api-automation-content">
    <BugInlineEditor key={bug.bugId} bug={bug} projectName={projectQuery.data?.name} sprintNames={sprintNames}
      resolveUserName={resolveUserName} onClose={() => setEditOpen(false)} onBack={() => goBackOrFallback(navigate, '/testing?tab=bugs')}>
      {activityPanels}
    </BugInlineEditor>
  </div></div>


  return (
    <div className={`workbench-page bugs-detail-page tp-surface ${styles.root}`}>
      <div className="api-automation-content">
        <BugDetailHeader bug={bug} onBack={() => goBackOrFallback(navigate, '/testing?tab=bugs')}
          onTransition={setTransitionAction} onEdit={() => setEditOpen(true)} onTransfer={() => setTransferOpen(true)} />

        <div className="bug-detail-cols mt-5 grid w-full min-w-0 grid-cols-[minmax(0,2.15fr)_minmax(300px,1fr)] items-start gap-5 max-[1100.01px]:grid-cols-1">
          <div className="bug-detail-main min-w-0">
            <BugDetailPanel className="bug-detail-summary">
              <div className="bug-detail-breadcrumb flex items-center gap-2.5 break-words font-mono text-[11px] text-[var(--srf-text-muted)]">{projectQuery.data?.name || bug.projectId} <span>/</span> {formatBugNo(bug.bugNo)}</div>
              <h1 className="mb-2.5 mt-3.5 break-words text-[22px] font-semibold leading-normal text-[var(--srf-text)] max-[720.01px]:text-[18px]">{bug.title}</h1>
              <div className="bug-detail-subtitle text-xs text-[var(--srf-text-muted)]"><UserDisplayName name={resolveUserName(bug.reporterUserId)} /> 提交于 {formatTime(pickCreatedAt(bug))}</div>
            </BugDetailPanel>
            <BugDescriptionView html={bug.descriptionHtml} />
            {canRead && <BugZentaoPushPanel key={`zentao:${bug.bugId}`} bugId={bug.bugId} projectId={bug.projectId} canWrite={canWrite} attachments={bug.attachments ?? []} />}
            <BugEvidencePanel key={`evidence:${bug.bugId}`} descriptionHtml={bug.descriptionHtml} attachments={bug.attachments ?? []} download={downloadAttachment} />

          </div>

          <BugDetailSidebar bug={bug} projectName={projectQuery.data?.name}
            sprintNames={sprintNames} resolveUserName={resolveUserName} canReadContext={canRead}>
            {activityPanels}
          </BugDetailSidebar>
        </div>
      </div>

      <BugTransitionModal
        bug={bug}
        action={transitionAction}
        onClose={() => setTransitionAction(null)}
        />
      <BugTransferModal bug={transferOpen ? bug : null} onClose={() => setTransferOpen(false)} />

    </div>
  )
}
