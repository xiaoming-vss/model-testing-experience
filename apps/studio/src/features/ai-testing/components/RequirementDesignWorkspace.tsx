import { useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { RequirementDesignKind } from '../api/requirementDesign.api'
import { Alert, Button, Empty, Modal, Spin, Tooltip } from 'antd'
import { EyeOutlined, ExportOutlined, InfoCircleOutlined, NodeIndexOutlined, RedoOutlined } from '@ant-design/icons'
import { useRequirementDesignWorkspace } from '../hooks/useRequirementDesignWorkspace'
import { requirementDesignArtifacts } from '../utils/requirementDesign'
import { RequirementDesignConfigurationModal } from './RequirementDesignConfigurationModal'
import { RequirementTaskRunDialogs } from './RequirementTaskRunDialogs'
import { RunHistoryTable, RunRowActions } from './RunHistoryTable'
import { RunArtifacts } from './RunPipelineStatus'
import { RunListStatus } from './RunListStatus'
import { RequirementWorkspaceTabs } from './RequirementWorkspaceTabs'
import { RequirementCodeRiskPanel } from './RequirementCodeRiskPanel'
import { useRequirementCodeRiskWorkspace } from '../hooks/useRequirementCodeRiskWorkspace'
import { confirmDeleteRun, isRunDeletable } from '../utils/runDeletion'
import { ActionButton } from '@/shared/components/ActionButton'
import { ListPagination } from '@/shared/components/ListPagination'
import { getErrorMessage } from '@/utils/format'
import '../styles/index.css'
import '../styles/task-detail-v2.css'
import '@/shared/styles/list-table.css'
import '../styles/requirement-design.css'

export type RequirementWorkspaceTab = 'content' | RequirementDesignKind | 'codeRisk'

export function RequirementDesignWorkspace({ requirementId, projectId, documentHash, canWrite, canExecute, canReview,
  document, activeTab, onTabChange, tabsContainer, actionsContainer }: {
  requirementId: string; projectId: string; documentHash?: string; canWrite: boolean; canExecute: boolean; canReview: boolean
  tabsContainer?: HTMLElement | null; actionsContainer?: HTMLElement | null
  document?: ReactNode; activeTab?: RequirementWorkspaceTab; onTabChange?: (tab: RequirementWorkspaceTab) => void
}) {
  const [localTab, setLocalTab] = useState<RequirementWorkspaceTab>(document ? 'content' : 'requirement_analysis')
  const tab = activeTab ?? localTab
  const kind = tab === 'content' || tab === 'codeRisk' ? 'requirement_analysis' : tab
  const { overview, tasks, selectedTaskId, selected, definitions, generationBlocked,
    sourceChanged, history, rows, page, setPage, pageSize, setPageSize, start, remove, retry,
    graph, busy, run, refresh, personalLlm, configure, setConfigure, dialog, open, errorContent, setErrorContent,
    resetRunRequest, setConfigurationIds, setSelectedId } = useRequirementDesignWorkspace(requirementId, projectId, documentHash, kind)
  const codeRisk = useRequirementCodeRiskWorkspace(requirementId, projectId, tab === 'codeRisk')
  const changeTab = (next: RequirementWorkspaceTab) => {
    if (next === tab) return
    setLocalTab(next); onTabChange?.(next); setSelectedId(undefined); setPage(1); resetRunRequest()
  }
  const runDisabledReason = overview.error ? '运行信息读取失败，请点击“重试读取”。'
    : overview.isPending ? '正在读取运行信息，请稍候。'
    : busy ? '正在处理当前操作，请完成后再运行。'
    : generationBlocked ? '请先补充有效的需求增强文本，再生成功能用例。'
    : selectedTaskId && overview.data?.activeTaskIds?.includes(selectedTaskId) ? '当前任务尚未结束，请完成当前运行后再试。'
    : undefined
  const pagination = { current: page, pageSize, total: history.data?.total ?? 0, loading: history.isFetching,
    onChange: (next: number, size: number) => { setPage(size === pageSize ? next : 1); setPageSize(size); setSelectedId(undefined) } }
  const tabs = <RequirementWorkspaceTabs activeTab={tab} includeDocument={Boolean(document)} counts={overview.data?.runCounts}
      countError={Boolean(overview.error)} codeRiskCount={codeRisk.count} codeRiskCountError={codeRisk.countError}
      disabled={busy || codeRisk.busy || Boolean(dialog) || Boolean(configure)} onChange={changeTab} />
  const toolbar = <div className="ai-requirement-design-toolbar" hidden={tab === 'content'}>
      <div className="ai-requirement-design-tools tp-refresh-actions">
        {tab === 'codeRisk' ? <>
          <ActionButton operation="refresh" loading={codeRisk.runsFetching} onClick={codeRisk.refresh}>刷新</ActionButton>
          {canExecute ? <Tooltip trigger={['hover', 'focus']} title={codeRisk.runDisabledReason}>
            <span style={{ display: 'inline-flex' }} tabIndex={codeRisk.runDisabledReason ? 0 : undefined} aria-label={codeRisk.runDisabledReason}>
              <ActionButton operation="run" type="primary" loading={codeRisk.start.isPending} disabled={Boolean(codeRisk.runDisabledReason)} onClick={() => codeRisk.start.mutate()}>
                运行分析
              </ActionButton>
            </span>
          </Tooltip> : null}
        </> : <>
          {canWrite && (kind === 'api' || kind === 'ui') ? <ActionButton operation="edit" disabled={busy} onClick={() => setConfigure('save')}>设置</ActionButton> : null}
          <ActionButton operation="refresh" loading={history.isFetching} onClick={refresh}>刷新</ActionButton>
          {canExecute ? <Tooltip trigger={['hover', 'focus']} title={runDisabledReason}>
            <span style={{ display: 'inline-flex' }} tabIndex={runDisabledReason ? 0 : undefined} aria-label={runDisabledReason}>
              <ActionButton operation="run" type="primary" loading={start.isPending} disabled={Boolean(runDisabledReason)} onClick={run}>
                {kind === 'requirement_analysis' ? '运行分析' : '生成用例'}
              </ActionButton>
            </span>
          </Tooltip> : null}
        </>}
      </div>
    </div>
  return <div className="ai-requirement-design tp-surface tp-list-surface">
    {personalLlm.dialog}
    <Modal title="错误信息" open={errorContent !== undefined} onCancel={() => setErrorContent(undefined)} footer={<Button onClick={() => setErrorContent(undefined)}>关闭</Button>}><pre style={{ whiteSpace: 'pre-wrap', maxHeight: '60dvh', overflow: 'auto' }}>{errorContent}</pre></Modal>
    {tabsContainer ? createPortal(tabs, tabsContainer) : null}
    {actionsContainer ? createPortal(toolbar, actionsContainer) : null}
    <div className="ai-requirement-design-navigation" hidden={Boolean(tabsContainer) && (Boolean(actionsContainer) || tab === 'content')}>
    {!tabsContainer ? tabs : null}
    {!actionsContainer ? toolbar : null}

    </div>
    {document ? <div role="tabpanel" id="requirement-panel-content" aria-labelledby="requirement-tab-content"
      className="ai-requirement-document-panel" hidden={tab !== 'content'}>{document}</div> : null}
    <div role="tabpanel" id="requirement-panel-codeRisk" aria-labelledby="requirement-tab-codeRisk"
      className="ai-requirement-design-panel" hidden={tab !== 'codeRisk'}>
      {tab === 'codeRisk' ? <RequirementCodeRiskPanel workspace={codeRisk} canWrite={canWrite} /> : null}
    </div>
    <div role="tabpanel" id="requirement-panel-design" aria-labelledby={`requirement-tab-${kind}`} className="ai-requirement-design-panel" hidden={tab === 'content' || tab === 'codeRisk'}>
    {overview.error || history.error ? <Alert showIcon type="error" title={getErrorMessage(overview.error ?? history.error)} action={<Button onClick={refresh}>重试读取</Button>} /> : null}
    {sourceChanged ? <Alert showIcon type="warning" title={`当前材料已更新，选中运行使用的是生成时的材料快照。${kind === 'requirement_analysis' ? '请重新分析最新材料。' : '请基于最新材料重新生成用例。'}`} /> : null}
    <section className="ai-requirement-design-history">
    {history.isPending ? <Spin /> : rows.length ? <RunHistoryTable appearance="list" className="tp-list-table" rows={rows} getRunId={row => row.runId} selectedRunId={selected?.runId}
      resolveRow={row => row} onSelect={setSelectedId} pagination={pagination}
      getCreatedAt={row => row.createdAt}
      renderStatus={row => <RunListStatus run={row} stages={kind === 'requirement_analysis' ? ['generate', 'review'] : undefined}
        stageTag={row.currentStage ? <span className="tp-tone-tag tone-slate">{definitions.find(stage => stage.key === row.currentStage)?.label ?? (row.currentStage === 'completed' ? definitions[definitions.length - 1].label : row.currentStage === 'relation_analysis' ? '图谱分析' : row.currentStage)}</span> : undefined} />}
      renderArtifacts={row => <RunArtifacts artifacts={requirementDesignArtifacts[kind].map(artifact => ({ ...artifact,
        available: artifact.key === 'resultYaml' ? Boolean(row.hasResult) : (row.availableArtifacts ?? []).includes(artifact.key) }))}
        onOpen={artifact => open(row, artifact)} />}
      renderActions={row => {
        const rejected = row.reviewStatus === 'rejected'
        const reviewable = !rejected && row.reviewStatus === 'pending' && ['waiting_review', 'success'].includes(row.status ?? '')
        const importable = row.reviewStatus === 'approved' && row.status === 'success' && row.importStatus !== 'imported'
        const artifact = kind === 'requirement_analysis' && row.currentStage === 'extracting_text' ? 'firstStepOutput'
          : kind === 'function' && row.currentStage === 'requirement_analysis' ? 'requirementAnalysis'
          : kind === 'function' && row.currentStage === 'case_names' ? 'caseNames' : 'resultYaml'
        return <RunRowActions inline={<>
          {reviewable && canReview ? <Tooltip title="审核"><Button size="small" type="text" shape="circle" className="app-action app-action-icon app-action-read" icon={<EyeOutlined />} aria-label="审核" onClick={event => { event.stopPropagation(); open(row, artifact, 'review') }} /></Tooltip> : null}
          {importable && canExecute ? <Tooltip title="导入"><Button size="small" type="text" shape="circle" className="app-action app-action-icon app-action-upload" icon={<ExportOutlined />} aria-label="导入" onClick={event => { event.stopPropagation(); open(row, 'resultYaml', 'import') }} /></Tooltip> : null}
          {['failed', 'error'].includes(row.status ?? '') ? <>
            {row.errorMessage ? <Tooltip title="错误信息"><Button size="small" type="text" shape="circle" className="app-action app-action-icon app-action-read" icon={<InfoCircleOutlined />} aria-label="错误信息" onClick={event => { event.stopPropagation(); open(row, 'errorMessage') }} /></Tooltip> : null}
            {canExecute && row.reviewStatus === 'pending' && row.importStatus !== 'imported' && ['failed', 'retrying'].includes(row.stageStatus ?? '') && (kind === 'requirement_analysis' ? ['extracting_text', 'feature_understanding'] : kind === 'function' ? ['requirement_analysis', 'case_names', 'detailed_cases'] : []).includes(row.currentStage ?? '') ? <Tooltip title="重试"><Button size="small" type="text" shape="circle" className="app-action app-action-icon app-action-read" icon={<RedoOutlined />} aria-label="重试" disabled={retry.isPending} onClick={event => { event.stopPropagation(); retry.mutate(row) }} /></Tooltip> : null}
          </> : null}
          {kind === 'function' && canExecute && row.reviewStatus === 'approved' && row.hasResult && (row.status === 'success' || (['failed', 'error'].includes(row.status ?? '') && row.currentStage === 'relation_analysis')) ? <Tooltip title={(row.availableArtifacts ?? []).includes('caseRelations') ? '重新生成图谱' : '生成图谱'}><Button size="small" type="text" shape="circle" className="app-action app-action-icon app-action-create" icon={<NodeIndexOutlined />} aria-label={(row.availableArtifacts ?? []).includes('caseRelations') ? '重新生成图谱' : '生成图谱'} disabled={graph.isPending} onClick={event => { event.stopPropagation(); graph.mutate(row.runId!) }} /></Tooltip> : null}
          {canWrite ? <ActionButton operation="delete" iconOnly size="small" aria-label="删除运行记录" disabled={!isRunDeletable(row.status) || remove.isPending}
            onClick={event => { event.stopPropagation(); confirmDeleteRun(() => remove.mutate(row.runId!)) }} /> : null}
        </>} />
      }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={history.error ? '运行记录读取失败' : '当前类型暂无运行记录'} />}
      {history.isSuccess && !rows.length ? <div className="table-footer"><ListPagination {...pagination} /></div> : null}
    </section>
    </div>
    {configure ? <RequirementDesignConfigurationModal key={`${kind}:${selectedTaskId ?? 'new'}`} requirementId={requirementId} kind={kind} tasks={tasks}
      initialTaskId={selectedTaskId} onClose={() => { setConfigure(undefined); refresh() }} onSaved={(id) => {
        setConfigurationIds(previous => ({ ...previous, [kind]: id }))
        const runAfter = configure === 'run'; setConfigure(undefined); refresh(); if (runAfter) start.mutate(id)
      }} /> : null}
    {dialog ? <RequirementTaskRunDialogs kind={kind} request={dialog} /> : null}
  </div>
}
