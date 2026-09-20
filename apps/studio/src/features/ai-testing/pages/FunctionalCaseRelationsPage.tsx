import { ArrowLeftOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Button, Empty, Segmented, Select, Spin } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  FunctionalCaseRelationsGraph,
  type FunctionalCaseRelationsGraphHandle,
} from '../components/FunctionalCaseRelationsGraph'
import {
  buildRelationsGraphModel,
  parseCaseRelationsContent,
  parseDetailedCaseMeta,
  type RelationsOrientation,
} from '../utils/caseRelationsGraph'
import type { FunctionalCaseGenerateTaskRun } from '../types'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { api } from '@/services/api'
import './FunctionalCaseRelationsPage.css'

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

function FunctionalCaseRelationsPageInner() {
  const { taskId, runId } = useParams()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<'graph' | 'json'>('graph')
  const [orientation, setOrientation] = useState<RelationsOrientation>('horizontal')
  const [hasSelection, setHasSelection] = useState(false)
  const graphRef = useRef<FunctionalCaseRelationsGraphHandle | null>(null)

  const taskQuery = useQuery({
    queryKey: ['functionalCaseGenerateTask', taskId],
    queryFn: () => api.getFunctionalCaseGenerateTask(taskId as string),
    enabled: Boolean(taskId),
  })
  const runQuery = useQuery({
    queryKey: ['functionalCaseGenerateTaskRun', runId],
    queryFn: () => api.getFunctionalCaseGenerateTaskRun(runId as string),
    enabled: Boolean(runId),
  })

  const run = runQuery.data
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

  return (
    <ProjectAccessScope resourceError={taskQuery.error} projectId={taskQuery.data?.projectId ?? ''}>
      <div className="ai-relations-page">
        <div className="ai-relations-page-bar">
          <Button
            type="text"
            size="small"
            className="ai-relations-page-back"
            icon={<ArrowLeftOutlined />}
            onClick={() => {
              if (taskId) {
                navigate(`/ai-testing/function-tasks/${taskId}`)
                return
              }
              navigate(-1)
            }}
          >
            返回任务
          </Button>
          <div className="ai-relations-page-heading">
            <span className="t1">{taskQuery.data?.name || '功能测试用例生成'} · 用例图谱</span>
            <span className="t2">
              {stats ? `${stats.caseCount} 条用例 · ${stats.edgeCount} 条关联 · ${stats.pathCount} 条业务主线 · ` : ''}
              运行 {runId ? runId.slice(0, 8) : '-'}
            </span>
          </div>
          <span className="ai-relations-page-spacer" />
          <Segmented
            size="small"
            value={activeTab}
            onChange={(value) => setActiveTab(value as 'graph' | 'json')}
            options={[
              { label: '可视化', value: 'graph' },
              { label: 'json', value: 'json' },
            ]}
          />
          {activeTab === 'graph' ? (
            <>
              <Select<RelationsOrientation>
                size="small"
                value={orientation}
                onChange={setOrientation}
                style={{ width: 116 }}
                options={[
                  { value: 'horizontal', label: '横向鱼骨' },
                  { value: 'vertical', label: '纵向鱼骨' },
                ]}
              />
              <Button size="small" onClick={() => graphRef.current?.fitView()}>查看全图</Button>
              <Button size="small" disabled={!hasSelection} onClick={() => graphRef.current?.locateSelected()}>
                定位选中用例
              </Button>
            </>
          ) : null}
          <span className="ai-relations-page-legend">
            <span className="legend-item"><i className="legend-line solid" aria-hidden />主线 / 后续</span>
            <span className="legend-item"><i className="legend-line dashed" aria-hidden />分支</span>
          </span>
        </div>

        <div className="ai-relations-page-body">
          {loading ? (
            <div className="ai-relations-page-loading"><Spin /></div>
          ) : runQuery.error ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="运行记录加载失败，请返回任务页重试" />
          ) : activeTab === 'graph' ? (
            <FunctionalCaseRelationsGraph
              ref={graphRef}
              content={relationsContent}
              casesContent={run?.resultYaml}
              orientation={orientation}
              onSelectionChange={handleSelectionChange}
            />
          ) : (
            <div className="ai-relations-page-json">
              {relationsContent ? (
                <JsonEditor value={relationsContent} readOnly foldable minHeight={640} />
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

export function FunctionalCaseRelationsPage() {
  return <FunctionalCaseRelationsPageInner />
}
