import { useState } from 'react'
import { createPortal } from 'react-dom'
import { RequirementAnalysisTaskDetailPage } from '../pages/RequirementAnalysisTaskDetailPage'
import { FunctionalCaseGenerateTaskDetailPage } from '../pages/FunctionalCaseGenerateTaskDetailPage'
import { ApiCaseGenerateTaskDetailPage } from '../pages/ApiCaseGenerateTaskDetailPage'
import { UiCaseGenerateTaskDetailPage } from '../pages/UiCaseGenerateTaskDetailPage'
import type { RequirementDesignKind } from '../api/requirementDesign.api'
import type { TaskRunDialogRequest } from '../hooks/useTaskRunDialog'

const controllers = {
  requirement_analysis: RequirementAnalysisTaskDetailPage,
  function: FunctionalCaseGenerateTaskDetailPage,
  api: ApiCaseGenerateTaskDetailPage,
  ui: UiCaseGenerateTaskDetailPage,
}

export function RequirementTaskRunDialogs({ kind, request }: { kind: RequirementDesignKind; request: TaskRunDialogRequest }) {
  // Controllers keep their page markup for direct task URLs. Mount that markup
  // off the workspace; their Ant Design dialogs still portal into document.body.
  const [host] = useState(() => document.createDocumentFragment())
  const Controller = controllers[kind]
  return createPortal(<Controller key={`${kind}:${request.taskId}:${request.runId}:${request.artifact}:${request.mode}`} dialogRequest={request} />, host)
}
