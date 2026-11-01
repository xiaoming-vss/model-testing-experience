import { Alert, Button } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { getErrorMessage } from '@/utils/format'
import { aiTestingApi } from '../api/aiTesting.api'
import { RequirementDesignConfigurationModal } from './RequirementDesignConfigurationModal'

/** 维护 API 测试当前输入，文档内容在宽敞的弹框中查看和编辑。 */
export function ApiGenerationSourcePanel({ requirementId, taskId, canWrite, busy, onSaved }: {
  requirementId: string; taskId?: string; canWrite: boolean; busy: boolean; onSaved: () => void
}) {
  const [open, setOpen] = useState(false)
  const client = useQueryClient()
  const task = useQuery({ queryKey: ['apiGenerationInputTask', taskId],
    queryFn: () => aiTestingApi.getApiCaseGenerateTask(taskId!), enabled: Boolean(taskId), retry: false })
  const source = task.data?.sourceContent
  return <section className="gc-inspector-section gc-inspector-source" aria-label="API 测试文档">
    <h3>OpenAPI / Swagger 文档</h3>
    <p>{task.isFetching ? '正在读取文档' : source ? '已配置文档' : '尚未配置文档'}</p>
    {canWrite || source ? <Button size="small" disabled={task.isFetching || Boolean(task.error) || (canWrite && busy)} onClick={() => setOpen(true)}>
      {canWrite ? (source ? '查看 / 修改文档' : '添加文档') : '查看文档'}
    </Button> : null}
    {task.error ? <Alert showIcon type="error" title={getErrorMessage(task.error)} action={<Button size="small" onClick={() => void task.refetch()}>重试读取</Button>} /> : null}
    <p className="gc-inspector-summary">文档用于下一轮生成。</p>
    {open ? <RequirementDesignConfigurationModal requirementId={requirementId} kind="api" tasks={[]} initialTaskId={taskId} readOnly={!canWrite}
      onClose={() => setOpen(false)} onSaved={() => { setOpen(false); void client.invalidateQueries({ queryKey: ['apiGenerationInputTask'] }); void client.invalidateQueries({ queryKey: ['requirementDesignConfiguration', 'api'] }); onSaved() }} /> : null}
  </section>
}
