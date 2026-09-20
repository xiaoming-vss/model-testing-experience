import { Tag, Tooltip } from 'antd'
import { Fragment, type ReactNode } from 'react'
import { getRunPipelineModel, type RunPipelineStageKey, type RunPipelineTone } from '../utils/runPipeline'

const toneColorMap: Record<RunPipelineTone, string> = {
  processing: 'processing',
  success: 'success',
  error: 'error',
  warning: 'warning',
  purple: 'purple',
  muted: 'default',
}

type RunPipelineStatusProps = {
  run: { status?: string; reviewStatus?: string; importStatus?: string }
  /** 只展示部分阶段（如需求分析仅「生成→审核」、代码风险仅「生成」），默认三段全展示。 */
  stages?: RunPipelineStageKey[]
  repairProgress?: string | null
  stageTag?: ReactNode
}

export function RunPipelineStatus({ run, stages, repairProgress, stageTag }: RunPipelineStatusProps) {
  const model = getRunPipelineModel(run, { stages })
  return (
    <div className="ai-task-run-pipeline">
      <span className="ai-task-run-pipeline-track">
        {model.stages.map((stage, index) => {
          const previous = model.stages[index - 1]
          const linkDone = previous?.state === 'done' && (stage.state === 'done' || stage.state === 'current')
          return (
            <Fragment key={stage.key}>
              {previous ? <span className={`ai-task-run-pipeline-link${linkDone ? ' is-done' : ''}`} /> : null}
              <Tooltip title={stage.tooltip}>
                <span className={`ai-task-run-pipeline-dot is-${stage.state}`} />
              </Tooltip>
            </Fragment>
          )
        })}
      </span>
      <span className="ai-task-run-pipeline-meta">
        {repairProgress ? (
          <Tooltip title={repairProgress}>
            <span role="status" aria-label={repairProgress} className="ai-task-run-pipeline-repair">
              自动修复中
            </span>
          </Tooltip>
        ) : (
          <Tag className="ai-task-run-pipeline-label" color={toneColorMap[model.statusTone]}>
            {model.statusLabel}
          </Tag>
        )}
        {stageTag}
      </span>
    </div>
  )
}

export type RunArtifactItem = { key: string; label: string; available: boolean }

type RunArtifactsProps = {
  artifacts: RunArtifactItem[]
  onOpen?: (key: string) => void
}

export function RunArtifacts({ artifacts, onOpen }: RunArtifactsProps) {
  return (
    <span className="ai-task-run-artifacts">
      {artifacts.map((artifact) =>
        artifact.available && onOpen ? (
          <Tooltip key={artifact.key} title={`查看${artifact.label}`}>
            <button
              type="button"
              className="ai-task-run-artifact"
              onClick={(event) => {
                event.stopPropagation()
                onOpen(artifact.key)
              }}
            >
              {artifact.label}
            </button>
          </Tooltip>
        ) : (
          <Tooltip key={artifact.key} title="未生成">
            <span className="ai-task-run-artifact off">{artifact.label}</span>
          </Tooltip>
        ),
      )}
    </span>
  )
}
