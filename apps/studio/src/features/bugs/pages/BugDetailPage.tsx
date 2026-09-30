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
import { BugDetailHeader } from '../components/BugDetailHeader'
import { useBugDetail } from '../hooks/useBugDetail'
import '@/shared/styles/surface-tokens.css'
import '../styles/bugs-v2.css'
import '../styles/bug-detail.css'

export function BugDetailPage() {
  const { navigate, bugQuery, bug, activitiesQuery, statusChanges, dynamics, resolveUserName,
    sprintNames, projectQuery, canWrite, comment, setComment, commentMutation, downloadAttachment,
    transitionAction, setTransitionAction, transferOpen, setTransferOpen, editOpen, setEditOpen } = useBugDetail()

  if (bugQuery.isLoading) {
    return (
      <div className="workbench-page bugs-detail-page tp-surface">
        <div className="api-automation-content">
          <Alert type="info" showIcon title="Bug 加载中..." />
        </div>
      </div>
    )
  }
  if (bugQuery.error || !bug) {
    return (
      <div className="workbench-page bugs-detail-page tp-surface">
        <div className="api-automation-content">
          <Alert
            showIcon
            type="error"
            title={bugQuery.error ? getErrorMessage(bugQuery.error) : 'Bug 不存在或已被删除'}
          />
          <Button className="bug-back-button" icon={<ArrowLeftOutlined />} onClick={() => navigate('/testing?tab=bugs')}>
            返回 Bug 列表
          </Button>
        </div>
      </div>
    )
  }


  const activityPanels = <>
            <section className="bug-detail-panel bug-detail-history">
              <h2 className="bug-panel-title">处理记录 <span className="bug-section-count">{statusChanges.length}</span></h2>
              {activitiesQuery.error && <Alert type="error" showIcon title="处理记录加载失败" action={<Button onClick={() => activitiesQuery.refetch()}>重试</Button>} />}
              <BugActivityFeed
                items={statusChanges}
                resolveUserName={resolveUserName}
                emptyText="还没有流转记录"
              />
            </section>
            <section className="bug-detail-panel bug-detail-discussion">
              <h2 className="bug-panel-title">评论与动态</h2>
              <div className="bug-comment-composer">
                <Input
                  aria-label="评论输入框"
                  placeholder="写下评论，回车发送"
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  disabled={!canWrite}
                  onPressEnter={(event) => { event.preventDefault(); if (canWrite && !commentMutation.isPending && comment.trim()) commentMutation.mutate() }}
                  suffix={
                    <Button
                      type="text"
                      size="small"
                      aria-label="发送评论"
                      icon={<SendOutlined />}
                      loading={commentMutation.isPending}
                      disabled={!canWrite || !comment.trim()}
                      onClick={() => comment.trim() && commentMutation.mutate()}
                    />
                  }
                />
              </div>
              <BugActivityFeed items={dynamics} resolveUserName={resolveUserName} emptyText="还没有评论与动态" />
            </section>
  </>
  if (editOpen) return <div className="workbench-page bugs-detail-page tp-surface"><div className="api-automation-content">
    <BugInlineEditor key={bug.bugId} bug={bug} projectName={projectQuery.data?.name} sprintNames={sprintNames}
      resolveUserName={resolveUserName} onClose={() => setEditOpen(false)} onBack={() => navigate('/testing?tab=bugs')}>
      {activityPanels}
    </BugInlineEditor>
  </div></div>


  return (
    <div className="workbench-page bugs-detail-page tp-surface">
      <div className="api-automation-content">
        <BugDetailHeader bug={bug} onBack={() => navigate('/testing?tab=bugs')}
          onTransition={setTransitionAction} onEdit={() => setEditOpen(true)} onTransfer={() => setTransferOpen(true)} />

        <div className="bug-detail-cols">
          <div className="bug-detail-main">
            <section className="bug-detail-panel bug-detail-summary">
              <div className="bug-detail-breadcrumb">{projectQuery.data?.name || bug.projectId} <span>/</span> {formatBugNo(bug.bugNo)}</div>
              <h1>{bug.title}</h1>
              <div className="bug-detail-subtitle">{resolveUserName(bug.reporterUserId)} 提交于 {formatTime(pickCreatedAt(bug))}</div>
            </section>
            <BugDescriptionView html={bug.descriptionHtml} />
            <BugEvidencePanel key={bug.bugId} descriptionHtml={bug.descriptionHtml} attachments={bug.attachments ?? []} download={downloadAttachment} />

          </div>

          <BugDetailSidebar bug={bug} projectName={projectQuery.data?.name}
            sprintNames={sprintNames} resolveUserName={resolveUserName}>
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
