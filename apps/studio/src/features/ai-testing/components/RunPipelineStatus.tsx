import { Tag, Tooltip } from 'antd'
import { Fragment, type ReactNode } from 'react'
import { getRunPipelineModel, type RunPipelineStageKey, type RunPipelineTone } from '../utils/runPipeline'

const toneColorMap: Record<RunPipelineTone, string> = {
  processing: 'cyan',
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
    <div className="ai-task-run-pipeline inline-flex flex-col items-start gap-1.5">
      <span className="ai-task-run-pipeline-track inline-flex items-center">
        {model.stages.map((stage, index) => {
          const previous = model.stages[index - 1]
          const linkDone = previous?.state === 'done' && (stage.state === 'done' || stage.state === 'current')
          const dotClass = stage.state === 'done' ? 'bg-[var(--app-pipeline-done)]'
            : stage.state === 'fail' ? 'bg-[var(--app-pipeline-failed)]'
              : stage.state === 'current' ? 'h-[7px] w-[7px] border-2 border-[var(--app-pipeline-current)] bg-[var(--ai-card)]'
                : 'bg-[var(--app-pipeline-idle)]'
          return (
            <Fragment key={stage.key}>
              {previous ? <span className={`ai-task-run-pipeline-link mx-1 h-0.5 w-5 ${linkDone ? 'is-done bg-[var(--app-pipeline-link)] opacity-75' : 'bg-[var(--app-pipeline-idle)] opacity-60'}`} /> : null}
              <Tooltip title={stage.tooltip}>
                <span className={`ai-task-run-pipeline-dot is-${stage.state} h-2 w-2 flex-none rounded-full ${dotClass}`} />
              </Tooltip>
            </Fragment>
          )
        })}
      </span>
      <span className="ai-task-run-pipeline-meta inline-flex min-h-[22px] flex-wrap items-center gap-1.5">
        {repairProgress ? (
          <Tooltip title={repairProgress}>
            <span role="status" aria-label={repairProgress} className="ai-task-run-pipeline-repair cursor-help whitespace-nowrap text-[12px] leading-[18px] text-[var(--app-result-warning-text)]">
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
    <span className="ai-task-run-artifacts inline-flex flex-wrap items-center gap-1.5">
      {artifacts.map((artifact) =>
        artifact.available && onOpen ? (
          <Tooltip key={artifact.key} title={`查看${artifact.label}`}>
            <button
              type="button"
              className="ai-task-run-artifact inline-flex h-5 cursor-pointer items-center rounded-[10px] border border-transparent bg-[var(--ai-panel-soft)] px-[9px] text-[11px] leading-[18px] text-[var(--ai-text-secondary)] transition-colors hover:bg-[var(--ai-accent-soft)] hover:text-[var(--ai-hover-text)]"
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
            <span className="ai-task-run-artifact off inline-flex h-5 items-center rounded-[10px] border border-dashed border-[var(--ai-border-strong)] bg-transparent px-[9px] text-[11px] leading-[18px] text-[var(--ai-text-muted)]">{artifact.label}</span>
          </Tooltip>
        ),
      )}
    </span>
  )
}
