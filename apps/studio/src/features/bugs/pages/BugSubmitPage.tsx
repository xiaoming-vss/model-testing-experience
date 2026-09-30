import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { BugFormModal } from '../components/BugFormModal'
import type { BugFormSource } from '../types'

/**
 * 从用例执行记录提交 Bug：通过 URL 参数带入测试单 / 用例 / 执行记录与所属需求，
 * 提交后跳到 Bug 详情。用路由而不是弹窗，避免跨 feature 引用组件。
 */
export function BugSubmitPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const activeProjectId = useWorkbenchStore((state) => state.activeProjectId)

  const source = useMemo<BugFormSource>(() => ({
    orderId: params.get('orderId') ?? '',
    entryId: params.get('entryId') ?? '',
    caseId: params.get('caseId') ?? undefined,
    requirementId: params.get('requirementId') ?? undefined,
    defaultTitle: params.get('title') ?? '',
    defaultDescription: params.get('description') ?? '',
  }), [params])
  const defaultSprintId = params.get('sprintId')

  function back() {
    if (window.history.length > 1) {
      navigate(-1)
      return
    }
    navigate('/testing?tab=bugs')
  }

  return (
    <BugFormModal
      open
      source={source}
      projectId={params.get('projectId') ?? activeProjectId}
      defaultSprintId={defaultSprintId}
      onClose={back}
      onSaved={(bug) => navigate(`/bugs/${bug.bugId}`, { replace: true })}
    />
  )
}
