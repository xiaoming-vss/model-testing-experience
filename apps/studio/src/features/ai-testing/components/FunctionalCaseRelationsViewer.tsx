import { ArtifactModeSwitch } from './ArtifactViewTabs'
import { useViewMotion } from '@/shared/ui/useViewMotion'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Empty, Spin } from 'antd'
import { createPortal } from 'react-dom'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  FunctionalCaseRelationsGraph,
  type FunctionalCaseRelationsGraphHandle,
} from './FunctionalCaseRelationsGraph'
import {
  buildRelationsGraphModel,
  parseCaseRelationsContent,
  parseDetailedCaseMeta,
} from '../utils/caseRelationsGraph'
import type { FunctionalCaseGenerateTaskRun } from '../types'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { api } from '@/services/api'
import { relationFailed, relationGenerating, useFunctionalCaseRelationsRun } from '../hooks/useFunctionalCaseRelationsRun'
import './FunctionalCaseRelationsViewer.css'

// relation_analysis 产物只存在 configJson.caseRelations 里，是已通过校验的 JSON 对象。
function getCaseRelationsContent(run?: FunctionalCaseGenerateTaskRun) {
  if (run?.configJson === undefined || run.configJson === null || run.configJson === '') return ''
  let parsed: unknown = run.configJson
  if (typeof parsed === 'string') {
    try {
      parsed = JSON.parse(parsed)
    } catch {
      return ''
    }
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return ''
  const relations = (parsed as Record<string, unknown>).caseRelations
  if (relations === undefined || relations === null || relations === '') return ''
  try {
    return JSON.stringify(relations, null, 2)
  } catch {
    return ''
  }
}

export function FunctionalCaseRelationsViewer({ taskId, runId, onBack, embedded = false, controlsContainer }: { taskId: string; runId: string; onBack?: () => void; embedded?: boolean; controlsContainer?: HTMLElement | null }) {
  const [activeTab, setActiveTab] = useState<'graph' | 'json'>('graph')
  const viewRef = useViewMotion(activeTab === 'graph' ? 0 : 1)
  const [jsonToolbar, setJsonToolbar] = useState<HTMLDivElement | null>(null)
  const [hasSelection, setHasSelection] = useState(false)
  const graphRef = useRef<FunctionalCaseRelationsGraphHandle | null>(null)

  const taskQuery = useQuery({
    queryKey: ['functionalCaseGenerateTask', taskId],
    queryFn: () => api.getFunctionalCaseGenerateTask(taskId as string),
    enabled: Boolean(taskId),
  })
  const runQuery = useFunctionalCaseRelationsRun(runId)

  const run = runQuery.data
  const generating = relationGenerating(run)
  const failed = relationFailed(run)
  const relationsContent = useMemo(() => getCaseRelationsContent(run), [run])
  const stats = useMemo(() => {
    const data = parseCaseRelationsContent(relationsContent)
    if (!data) return null
    const model = buildRelationsGraphModel(data, parseDetailedCaseMeta(run?.resultYaml))
    return { caseCount: model.nodes.length, edgeCount: model.edges.length, pathCount: model.paths.length }
  }, [relationsContent, run?.resultYaml])
  const loading = taskQuery.isLoading || runQuery.isLoading

  const handleSelectionChange = useCallback((caseId: string | null) => setHasSelection(Boolean(caseId)), [])

  // 切到 json 页签时图谱卸载，定位按钮同步失效。
  useEffect(() => {
    if (activeTab !== 'graph') setHasSelection(false)
  }, [activeTab])

  const tools = <>
          <ArtifactModeSwitch
            value={activeTab}
            onChange={(value) => setActiveTab(value as 'graph' | 'json')}
            options={[
              { label: '可视化', value: 'graph' },
              { label: 'JSON', value: 'json' },
            ]}
          />
          {activeTab === 'graph' ? (
            <>
              <Button size="small" disabled={!stats?.caseCount} onClick={() => graphRef.current?.fitView()}>查看全图</Button>
              <Button size="small" disabled={!hasSelection} onClick={() => graphRef.current?.locateSelected()}>
                定位选中用例
              </Button>
            </>
          ) : null}
          {activeTab === 'json' ? <div className="ai-relations-json-actions" ref={setJsonToolbar} /> : null}
          {activeTab === 'graph' ? <span className="ai-relations-page-legend">
            <span className="legend-item"><i className="legend-line solid" aria-hidden />主线 / 后续</span>
            <span className="legend-item"><i className="legend-line dashed" aria-hidden />分支</span>
          </span> : null}
  </>
  const sidebarTools = embedded && controlsContainer ? createPortal(
    <section className="gc-inspector-section gc-relations-controls"><h3>阅读工具</h3>
      {tools}
      <p className="gc-relations-meta">{stats ? `${stats.caseCount} 条用例 · ${stats.edgeCount} 条关联 · ${stats.pathCount} 条业务主线 · ` : ''}运行 {runId.slice(0, 8)}</p>
    </section>, controlsContainer,
  ) : null

  return (
    <ProjectAccessScope resourceError={taskQuery.error} projectId={taskQuery.data?.projectId ?? ''}>
      <div className={`ai-relations-page${embedded ? " is-embedded" : ""}`}>
        {sidebarTools}
        {!embedded ? <div className="ai-relations-page-bar">
          {onBack ? (
            <Button type="text" size="small" icon={<ArrowLeftOutlined />} onClick={onBack}>返回任务</Button>
          ) : null}
          <div className="ai-relations-page-heading">
            <span className="t1">{taskQuery.data?.name || '功能测试用例生成'} · 用例图谱</span>
            <span className="t2">
              {stats ? `${stats.caseCount} 条用例 · ${stats.edgeCount} 条关联 · ${stats.pathCount} 条业务主线 · ` : ''}
              运行 {runId ? runId.slice(0, 8) : '-'}
            </span>
          </div>
          <span className="ai-relations-page-spacer" />
          {tools}
        </div> : null}

        {failed ? <Alert type="error" showIcon title={run?.status === 'canceled' ? '图谱生成已取消' : '图谱生成失败'} description={run?.errorMessage || '本次图谱未生成成功，请重试。'} /> : null}
        <div ref={viewRef} className="ai-relations-page-body">
          {loading ? (
            <div className="ai-relations-page-loading"><Spin /></div>
          ) : runQuery.error ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="运行记录加载失败，请返回任务页重试" />
          ) : !relationsContent ? (
            generating ? <div className="ai-relations-page-loading"><Spin /></div>
              : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={failed ? '本次未产生图谱，可重新生成' : '当前运行尚未生成用例图谱'} />
          ) : activeTab === 'graph' ? (
            <FunctionalCaseRelationsGraph
              ref={graphRef}
              content={relationsContent}
              casesContent={run?.resultYaml}
              orientation="horizontal"
              presentation="hierarchy"
              onSelectionChange={handleSelectionChange}
            />
          ) : (
            <div className="ai-relations-page-json">
              {relationsContent ? (
                <JsonEditor value={relationsContent} readOnly foldable minHeight={0} toolbarContainer={jsonToolbar} downloadFileName={`case-relations-${runId}.json`} />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前运行还没有图谱数据" />
              )}
            </div>
          )}
        </div>
      </div>
    </ProjectAccessScope>
  )
}
