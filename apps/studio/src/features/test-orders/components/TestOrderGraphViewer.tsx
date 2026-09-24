import { toRecord } from '@/shared/utils/value'
import { Alert, Button, Empty, Modal, Segmented, Select, Spin, Tag, Typography } from 'antd'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  FunctionalCaseRelationsGraph,
  type FunctionalCaseRelationsGraphHandle,
} from '@/features/ai-testing/components/FunctionalCaseRelationsGraph'
import { usePersonalLlmChoice } from '@/features/ai-testing/hooks/usePersonalLlmChoice'
import {
  buildRelationsGraphModel,
  parseCaseRelationsContent,
  parseDetailedCaseMeta,
  type RelationsOrientation,
} from '@/features/ai-testing/utils/caseRelationsGraph'
import {
  getApiCaseGenerateTaskRunStatusMeta,
  isApiCaseGenerateTaskRunInProgress,
} from '@/features/ai-testing/utils/taskStatus'
import { api, listItems } from '@/services/api'
import { TestOrderGraphExecutionPanel } from './TestOrderGraphExecutionPanel'
import { getTestOrderEntryStatusMeta } from '../utils/testOrderStatus'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { message } from '@/shared/utils/feedback'
import { formatStructuredContent } from '@/shared/utils/value'
import { getErrorMessage } from '@/utils/format'
import '@/features/ai-testing/components/FunctionalCaseRelationsViewer.css'
import '../styles/graph-viewer.css'

const { Text } = Typography

// 图谱任务要跑多轮 skill 调用，运行中按固定间隔刷新。
const GRAPH_POLL_INTERVAL = 5000

/**
 * 图谱只存 case_id，节点名称要来用例本身；派发时回显在 configJson 里的 `graphInput.cases` 就是它。
 */
function getGraphCasesContent(configJson?: unknown): string {
  let parsed: unknown = configJson
  if (typeof parsed === 'string') {
    if (!parsed.trim()) return ''
    try {
      parsed = JSON.parse(parsed)
    } catch {
      return ''
    }
  }
  const cases = toRecord(toRecord(parsed)?.graphInput)?.cases
  if (!Array.isArray(cases)) return ''
  return JSON.stringify({ cases })
}

type TestOrderGraphViewerProps = {
  open: boolean
  orderId: string
  projectId?: string
  /** 派发需要 execute 权限；查看只要 read。 */
  canExecute: boolean
  currentUserId?: string
  isProjectOwner?: boolean
  onClose: () => void
}

/** 测试单图谱：取图谱输入 → 选个人 LLM 连接 → 派发，并用可视化 / json 展示累计图谱。 */
export function TestOrderGraphViewer({
  open,
  orderId,
  projectId,
  canExecute,
  currentUserId,
  isProjectOwner = false,
  onClose,
}: TestOrderGraphViewerProps) {
  const personalLlm = usePersonalLlmChoice(projectId)
  const [activeTab, setActiveTab] = useState<'graph' | 'json'>('graph')
  const [orientation, setOrientation] = useState<RelationsOrientation>('horizontal')
  const [jsonToolbar, setJsonToolbar] = useState<HTMLDivElement | null>(null)
  const [hasSelection, setHasSelection] = useState(false)
  const graphRef = useRef<FunctionalCaseRelationsGraphHandle | null>(null)

  const graphQuery = useQuery({
    queryKey: ['testOrderGraph', orderId],
    queryFn: () => api.getTestOrderGraph(orderId),
    enabled: open && Boolean(orderId),
    refetchInterval: (query) =>
      isApiCaseGenerateTaskRunInProgress(query.state.data?.run?.status)
        ? GRAPH_POLL_INTERVAL
        : false,
  })
  const entriesQuery = useQuery({
    queryKey: ['testOrderEntries', orderId],
    queryFn: () => api.getTestOrderEntries(orderId),
    enabled: open && Boolean(orderId),
  })
  const entriesByCase = useMemo(() => new Map(listItems(entriesQuery.data).map((entry) => [entry.caseId, entry])), [entriesQuery.data])
  const caseBadges = useMemo(() => Object.fromEntries(listItems(entriesQuery.data)
    .filter((entry) => entry.caseId)
    .map((entry) => [entry.caseId!, getTestOrderEntryStatusMeta(entry.status)])), [entriesQuery.data])
  const renderExecutionPanel = (caseId: string) => {
    if (entriesQuery.isPending) return <Spin tip="加载执行条目…" />
    if (entriesQuery.isError) return <Alert type="error" title="执行条目加载失败" action={<Button onClick={() => void entriesQuery.refetch()}>重试</Button>} />
    const entry = entriesByCase.get(caseId)
    if (!entry?.entryId) return <Alert type="info" title="此用例已不在当前测试单中，无法执行，请刷新或重新生成图谱" />
    return <TestOrderGraphExecutionPanel key={`${orderId}:${entry.entryId}`} orderId={orderId} entry={entry} canExecute={canExecute} currentUserId={currentUserId} isProjectOwner={isProjectOwner} />
  }
  const run = graphQuery.data?.run ?? null
  const inProgress = isApiCaseGenerateTaskRunInProgress(run?.status)
  const statusMeta = getApiCaseGenerateTaskRunStatusMeta(run?.status)
  const graphContent = useMemo(() => formatStructuredContent(run?.resultYaml), [run?.resultYaml])
  const casesContent = useMemo(() => getGraphCasesContent(run?.configJson), [run?.configJson])
  const stats = useMemo(() => {
    const data = parseCaseRelationsContent(graphContent)
    if (!data) return null
    const model = buildRelationsGraphModel(data, parseDetailedCaseMeta(casesContent))
    return { caseCount: model.nodes.length, edgeCount: model.edges.length, pathCount: model.paths.length }
  }, [graphContent, casesContent])

  const handleSelectionChange = useCallback((caseId: string | null) => setHasSelection(Boolean(caseId)), [])

  // 切到 json 页签时图谱卸载，定位按钮同步失效。
  useEffect(() => {
    if (activeTab !== 'graph') setHasSelection(false)
  }, [activeTab])

  const dispatchMutation = useMutation({
    mutationFn: async () => {
      // 图谱输入是全平台唯一一处 snake_case 契约：原样取回、原样回传，不做字段改名。
      const graphInput = await api.getTestOrderGraphInput(orderId)
      const connectionId = await personalLlm.choose()
      return api.dispatchTestOrderGraph(orderId, { graphInput, connectionId })
    },
    onSuccess: () => {
      message.success('图谱生成任务已提交')
      void graphQuery.refetch()
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  let body
  if (graphQuery.isLoading) {
    body = (
      <div className="ai-relations-page-loading">
        <Spin />
      </div>
    )
  } else if (graphQuery.error) {
    body = (
      <div className="ai-relations-page-loading">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="图谱记录加载失败，请刷新重试" />
      </div>
    )
  } else if (!run) {
    body = (
      <div className="ai-relations-page-loading">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="这张测试单还没有生成过图谱" />
      </div>
    )
  } else if (inProgress) {
    body = (
      <div className="ai-relations-page-loading test-order-graph-loading">
        <Spin />
        <Text type="secondary">图谱生成中…</Text>
      </div>
    )
  } else if (!graphContent) {
    body = (
      <div className="ai-relations-page-loading">
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前运行还没有图谱数据" />
      </div>
    )
  } else if (activeTab === 'graph') {
    body = (
      <FunctionalCaseRelationsGraph
        ref={graphRef}
        content={graphContent}
        casesContent={casesContent}
        orientation={orientation}
        onSelectionChange={handleSelectionChange}
        renderCaseDetails={renderExecutionPanel}
        caseBadges={caseBadges}
        panelWidth={420}
      />
    )
  } else {
    body = (
      <div className="ai-relations-page-json">
        <JsonEditor
          value={graphContent}
          readOnly
          foldable
          minHeight={0}
          toolbarContainer={jsonToolbar}
          ariaLabel="测试单图谱 JSON"
          downloadFileName={`test-order-graph-${orderId}.json`}
        />
      </div>
    )
  }

  return (
    <>
      <Modal
        className="test-order-graph-modal"
        title="用例图谱"
        open={open}
        onCancel={onClose}
        footer={null}
        width="92vw"
        centered
        destroyOnHidden
        styles={{
          container: { padding: 0, overflow: 'hidden' },
          header: { display: 'none' },
          body: { height: '86dvh', minHeight: 0, padding: 0, overflow: 'hidden' },
        }}
      >
        <div className="ai-relations-page">
          <div className="ai-relations-page-bar">
            <Text strong>用例图谱</Text>
            <div className="test-order-graph-status">
              {run ? <Tag color={statusMeta.color}>{statusMeta.label}</Tag> : null}
              {inProgress ? <Text type="secondary">每 5 秒自动刷新</Text> : null}
              <Text type="secondary">
                {stats ? `${stats.caseCount} 条用例 · ${stats.edgeCount} 条关联 · ${stats.pathCount} 条业务主线` : ''}
              </Text>
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
            {activeTab === 'graph' && graphContent ? (
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
                <Button size="small" onClick={() => graphRef.current?.fitView()}>
                  查看全图
                </Button>
                <Button size="small" disabled={!hasSelection} onClick={() => graphRef.current?.locateSelected()}>
                  定位选中用例
                </Button>
              </>
            ) : null}
            {activeTab === 'json' && graphContent ? (
              <div className="ai-relations-json-actions" ref={setJsonToolbar} />
            ) : null}
            {activeTab === 'graph' && graphContent ? (
              <span className="ai-relations-page-legend">
                <span className="legend-item">
                  <i className="legend-line solid" aria-hidden />主线 / 后续
                </span>
                <span className="legend-item">
                  <i className="legend-line dashed" aria-hidden />分支
                </span>
              </span>
            ) : null}
            <Button size="small" onClick={() => void graphQuery.refetch()}>
              刷新
            </Button>
            {canExecute ? (
              <Button
                type="primary"
                size="small"
                className="action-btn-create"
                loading={dispatchMutation.isPending}
                disabled={inProgress}
                onClick={() => dispatchMutation.mutate()}
              >
                {run ? '重新生成' : '生成图谱'}
              </Button>
            ) : null}
          </div>

          {run?.status === 'failed' && run.errorMessage ? (
            <Alert showIcon type="error" title={run.errorMessage} />
          ) : null}

          <div className="ai-relations-page-body">{body}</div>
        </div>
      </Modal>
      {personalLlm.dialog}
    </>
  )
}
