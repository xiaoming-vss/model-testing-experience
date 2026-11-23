import { Tooltip } from 'antd'

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
