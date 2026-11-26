import { Alert, Button, Spin } from 'antd'
import type { ReactNode } from 'react'
import type { GenerationChainKind } from '../api/generationChain.api'
import type { GenerationChainWorkspace } from '../hooks/useRequirementGenerationChain'
import { getErrorMessage } from '@/utils/format'
import { CandidateStageWorkspace } from './CandidateStageWorkspace'
import { GenerationArtifactFrame } from './GenerationArtifactFrame'
import { ARTIFACT_MODAL_WIDTH } from './artifactModalLayout'
import type { UiGenerationSourceOptionsState } from './UiGenerationSourceConfig'

/** Present the current stage through the candidate workflow. */
export function GenerationChainModal({ workspace, requirementId, projectId, open, onClose, onOpenLegacy, embedded = false, inspectorContainer, inspectorActionContainer, uiSourceOptions, onOpenProfile, chooseGitlab, gitlabDialog }: {
  workspace: GenerationChainWorkspace
  requirementId: string
  projectId: string
  open: boolean
  onClose: () => void
  onOpenLegacy: (kind: GenerationChainKind) => void
  embedded?: boolean
  inspectorContainer?: HTMLElement | null
  inspectorActionContainer?: HTMLElement | null
  uiSourceOptions?: UiGenerationSourceOptionsState
  onOpenProfile?: () => void
  chooseGitlab?: (projectId: string) => Promise<string>
  gitlabDialog?: ReactNode
}) {
  const { chain, stage, selected, detail } = workspace
  if (!selected) return null
  if (stage && chain?.candidateMode) {
    return <CandidateStageWorkspace key={`${selected.kind}:${selected.stage}`} requirementId={requirementId}
      projectId={projectId} kind={selected.kind} stage={stage} open={open} embedded={embedded} onClose={onClose}
      inspectorContainer={inspectorContainer} inspectorActionContainer={inspectorActionContainer}
      chooseConnection={() => workspace.personalLlm.chooseRun(false, { label: '生成要求（选填）', placeholder: '补充本次生成需要关注的内容' })}
      uiSourceOptions={uiSourceOptions} onOpenProfile={onOpenProfile} chooseGitlab={chooseGitlab} gitlabDialog={gitlabDialog} />
  }
  return <GenerationArtifactFrame embedded={embedded} open={open} onCancel={onClose} footer={null}
    width={ARTIFACT_MODAL_WIDTH} centered className="generation-chain-modal" title={stage?.label ?? '阶段详情'}>
    {detail.isPending ? <div className="flex min-h-0 flex-1 items-center justify-center"><Spin /></div>
      : detail.error ? <Alert showIcon type="error" title="阶段详情读取失败" description={getErrorMessage(detail.error)}
          action={<Button onClick={() => void detail.refetch()}>重试</Button>} />
        : <Alert showIcon type="info" title="请先完成生成设置"
            action={<Button type="primary" onClick={() => onOpenLegacy(selected.kind)}>前往设置</Button>} />}
  </GenerationArtifactFrame>
}
