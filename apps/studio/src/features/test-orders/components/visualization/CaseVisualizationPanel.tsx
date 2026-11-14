import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Alert, Button, Segmented, Spin, Tag } from 'antd'
import { usePersonalLlmChoice } from '@/features/ai-testing/hooks/usePersonalLlmChoice'
import { usePendingRequestId } from '@/shared/hooks/usePendingRequestId'
import { getErrorMessage } from '@/utils/format'
import { caseVisualizationApi, isVisualizationRunning, visualizationStatus } from '../../api/caseVisualization.api'
import type { TestOrderEntry } from '../../types'
import type { VisualizationMode } from '../../visualizationTypes'
import { TestOrderCaseContent } from '../TestOrderCaseContent'
import { BusinessDiagram } from './BusinessDiagram'
import { VisualizationSteps } from './VisualizationSteps'
import '../../styles/case-visualization.css'

type Props = { orderId: string; entryId: string; projectId?: string; snapshot: TestOrderEntry['snapshot']; caseTitle?: string; canGenerate: boolean; preferredMode: VisualizationMode; onMode: (mode: VisualizationMode) => void }

export function CaseVisualizationPanel({ orderId, entryId, projectId, snapshot, caseTitle, canGenerate, preferredMode, onMode }: Props) {
  const [mode, setMode] = useState<VisualizationMode>('text')
  const [step, setStep] = useState(0)
  const [conditionsOpen, setConditionsOpen] = useState(true)
  const firstRead = useRef(true)
  const llm = usePersonalLlmChoice(projectId)
  const pendingRequest = usePendingRequestId()
  const query = useQuery({
    queryKey: ['caseVisualization', orderId, entryId], queryFn: () => caseVisualizationApi.get(orderId, entryId),
    enabled: Boolean(orderId && entryId), retry: false,
    refetchInterval: state => isVisualizationRunning(state.state.data?.latestRun?.status) ? 2000 : false,
  })
  const effective = query.data?.effectiveArtifact
  const artifact = effective?.content
  const usable = Boolean(effective?.schemaVersion === '1.0' && artifact?.schemaVersion === '1.0' && artifact.executionEntryId === entryId && artifact.visuals?.length && artifact.visuals.every(v => ['options', 'interval', 'state', 'quantity'].includes(v.kind)))
  const running = isVisualizationRunning(query.data?.latestRun?.status)
  useEffect(() => {
    if (firstRead.current && (query.isSuccess || query.isError)) {
      firstRead.current = false
      setMode(usable ? preferredMode : 'text')
    }
  }, [query.isSuccess, query.isError, usable, preferredMode])
  const generation = useMutation({
    mutationFn: async () => {
      const connection = await llm.choose()
      const action = usable ? 'regenerate' : 'generate'
      const requestId = pendingRequest.forInput(JSON.stringify([orderId, entryId, connection, action]))
      return caseVisualizationApi.generate(orderId, entryId, connection, requestId, action)
    },
    onSuccess: async () => { pendingRequest.clear(); await query.refetch() },
  })
  const steps = snapshot?.steps ?? []
  const visibleMode = usable ? mode : 'text'
  return <div className="test-order-visualization">
    <div className="test-order-viz-toolbar">
      <div><span>阅读方式</span><Segmented aria-label="用例阅读方式" value={visibleMode} options={[{ label: '文字', value: 'text' }, { label: '可视化', value: 'visual', disabled: !usable }]} onChange={value => { const next = value as VisualizationMode; setMode(next); onMode(next) }} /></div>
      <div><Tag>本次生成：{visualizationStatus(query.data?.latestRun?.status, query.data?.latestRun?.artifactStatus)}</Tag>{canGenerate && <Button size="small" loading={generation.isPending} disabled={running || query.isLoading} onClick={() => generation.mutate()}>{usable ? '重新生成' : query.data?.latestRun?.status === 'failed' ? '重试生成' : '生成可视化'}</Button>}</div>
    </div>
    {query.isLoading && <div className="test-order-viz-status"><Spin size="small" /> 检查图解状态，原文可正常执行</div>}
    {query.error && <Alert type="warning" showIcon title="图解状态暂不可用，仍可阅读原文" action={<Button size="small" onClick={() => void query.refetch()}>重试</Button>} />}
    {generation.error && <Alert type="error" showIcon title={getErrorMessage(generation.error)} />}
    {query.data?.latestRun?.errorMessage && <Alert type="warning" showIcon title={query.data.latestRun.errorMessage} description={usable ? '已有图解继续可用。' : undefined} />}
    {query.data?.unavailableReason && <Alert type="info" title={query.data.unavailableReason} />}
    {usable && query.data?.latestRun?.runId !== effective?.runId && !query.data?.latestRun?.errorMessage && <p className="test-order-viz-disclaimer">当前图解继续可用，新结果通过校验后才会替换。</p>}
    {visibleMode === 'text' ? <TestOrderCaseContent snapshot={snapshot} /> : artifact && <>
      <div className="test-order-viz-disclaimer">AI 辅助图解 · 展示待验证的预期关系，执行判定以原文为准。</div>
      {artifact.status === 'partial' && <Alert type="warning" showIcon title="部分内容未图解" description={<ul>{artifact.limitations.map((item, index) => <li key={index}>{item.reason}</li>)}</ul>} />}
      <details className="test-order-viz-preconditions" open={conditionsOpen} onToggle={event => setConditionsOpen(event.currentTarget.open)}>
        <summary>前置条件 · {snapshot?.preconditions.length ?? 0} 项</summary>
        {snapshot?.preconditions.length ? <ol>{snapshot.preconditions.map((text, index) => <li key={index}>{text || '前置条件内容缺失'}</li>)}</ol> : <p>暂无前置条件</p>}
      </details>
      <div className="test-order-viz-layout"><div className="test-order-viz-main">
      <VisualizationSteps snapshot={snapshot} artifact={artifact} step={step} onStep={setStep} />
        <BusinessDiagram artifact={artifact} step={step} />
      </div><aside className="test-order-viz-detail" aria-label="当前步骤详情">
        <h3 className="test-order-viz-case-title">{caseTitle || '用例详情'}</h3>
        <div className="test-order-viz-detail-heading"><h3>步骤详情</h3><span>{steps.length ? `${step + 1} / ${steps.length}` : '原文详情'}</span></div>
        <div className="test-order-viz-position" aria-hidden="true">{steps.map((_, index) => <i key={index} className={index === step ? 'is-active' : ''} />)}</div>
        <h3 className="test-order-viz-detail-step">{steps.length ? `步骤 ${String(step + 1).padStart(2, '0')}` : '原文详情'}</h3>
        <h4>操作说明</h4><p>{steps[step]?.action || '操作缺失'}</p>
        <section className="test-order-viz-expected" aria-label="当前步骤预期"><h4>预期结果</h4><p>{steps[step]?.expected || '预期缺失；图解不补写预期'}</p></section>
      </aside></div>
    </>}
    {llm.dialog}
  </div>
}
