import { useNavigate, useParams } from 'react-router-dom'
import { FunctionalCaseRelationsViewer } from '../components/FunctionalCaseRelationsViewer'

// 保留已有地址的访问能力；任务页的图谱入口使用弹框。
export function FunctionalCaseRelationsPage() {
  const { taskId = '', runId = '' } = useParams()
  const navigate = useNavigate()
  return <FunctionalCaseRelationsViewer taskId={taskId} runId={runId} onBack={() => navigate(`/ai-testing/function-tasks/${taskId}`)} />
}
