import { ExperimentOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Tag } from 'antd'
import { useState } from 'react'
import { usePersonalLlmChoice } from '@/features/ai-testing/hooks/usePersonalLlmChoice'
import { usePendingRequestId } from '@/shared/hooks/usePendingRequestId'
import { getErrorMessage } from '@/utils/format'
import { caseVisualizationApi, isVisualizationRunning, visualizationStatus } from '../../api/caseVisualization.api'
import '../../styles/case-visualization.css'

type Props = { orderId: string; projectId?: string; entryIds: string[]; onSelect: (id: string) => void; compact?: boolean }
export function VisualizationBatchButton({ orderId, projectId, entryIds, onSelect, compact = false }: Props) {
  const [batchId, setBatchId] = useState('')
  const llm = usePersonalLlmChoice(projectId)
  const pending = usePendingRequestId()
  const client = useQueryClient()
  const query = useQuery({
    queryKey: ['visualizationBatch', orderId, batchId], queryFn: () => caseVisualizationApi.getBatch(orderId, batchId), enabled: Boolean(batchId),
    refetchInterval: state => state.state.data?.items.some(item => isVisualizationRunning(item.run?.status)) ? 2000 : false,
  })
  const generate = useMutation({
    mutationFn: async () => {
      // Selection is frozen when the user clicks, before choosing model credentials.
      const selected = [...entryIds]
      const connection = await llm.choose()
      return caseVisualizationApi.batch(orderId, selected, connection, pending.forInput(JSON.stringify([orderId, selected, connection])))
    },
    onSuccess: data => {
      pending.clear(); client.setQueryData(['visualizationBatch', orderId, data.batchId], data); setBatchId(data.batchId)
      void client.invalidateQueries({ queryKey: ['caseVisualization', orderId] })
    },
  })
  return <div className={`test-order-viz-batch${compact ? ' is-compact' : ''}`}>
    <Button
      size="small"
      icon={compact ? <ExperimentOutlined aria-hidden="true" /> : undefined}
      aria-label={compact ? `生成所选图解（${entryIds.length}）` : undefined}
      title={compact ? '生成所选图解' : undefined}
      onClick={() => generate.mutate()}
      loading={generate.isPending}
      disabled={!entryIds.length || entryIds.length > 100}
    >{compact ? '图解' : `生成所选图解（${entryIds.length}）`}</Button>
    {entryIds.length > 100 && <p>每批最多 100 条，请减少勾选。</p>}
    {generate.error && <Alert type="error" title={getErrorMessage(generate.error)} />}
    {query.error && <Alert type="warning" title="批量状态暂不可用" action={<Button size="small" onClick={() => void query.refetch()}>重试</Button>} />}
    {query.data && <details open><summary>本批 {query.data.total} 条 · 已有图解自动跳过</summary><div className="test-order-viz-batch-counts">{Object.entries(query.data.counts).map(([status, count]) => <Tag key={status}>{visualizationStatus(status)} {count}</Tag>)}</div><ul>{query.data.items.map(item => <li key={item.entryId}><Button size="small" type="link" onClick={() => onSelect(item.entryId)}>{item.entryId}</Button><span>{item.errorMessage || visualizationStatus(item.run?.status ?? item.disposition, item.run?.artifactStatus)}</span></li>)}</ul></details>}
    {llm.dialog}
  </div>
}
