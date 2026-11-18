import { useMemo } from 'react'
import { diffArtifact, splitDiffLines, type DiffCell } from '../utils/chainArtifact'

function Cell({ cell, side }: { cell?: DiffCell; side: 'before' | 'after' }) {
  const tone = !cell ? 'is-empty bg-[var(--app-shell-bg)]' : cell.changed ? side === 'before' ? 'is-remove bg-[var(--app-danger-surface-soft)] text-[var(--app-profile-danger-text)]' : 'is-add bg-[var(--app-testing-success-tag-bg)] text-[var(--app-result-success-text)]' : ''
  return <td className={`gc-diff-cell p-0 align-top text-[var(--app-surface-text)]${side === 'after' ? ' border-l border-[var(--app-surface-border)]' : ''} ${tone}`}>
    {cell ? <div className="gc-diff-line flex min-h-5 gap-2 px-2">
      <span className="gc-diff-number flex-[0_0_4ch] select-none text-right tabular-nums text-[var(--app-surface-text-muted)]" aria-hidden="true">{cell.lineNumber}</span>
      <span className="gc-diff-sign flex-[0_0_10px] select-none text-center" aria-label={cell.changed ? side === 'before' ? '删除' : '新增' : undefined}>{cell.changed ? side === 'before' ? '−' : '+' : ' '}</span>
      <code className="min-w-0 whitespace-pre-wrap break-words font-[inherit] text-[inherit] [tab-size:2]">{cell.text || ' '}</code>
    </div> : null}
  </td>
}

export function GenerationArtifactDiff({ before, after, beforeLabel, afterLabel }: {
  before: string
  after: string
  beforeLabel: string
  afterLabel: string
}) {
  const rows = useMemo(() => splitDiffLines(diffArtifact(before, after)), [before, after])
  return <table className="gc-diff w-full min-w-[640px] table-fixed border-spacing-0 font-mono text-[12px] leading-[1.65]" aria-label="版本差异">
    <thead><tr><th scope="col" className="sticky top-0 z-[1] border-b border-[var(--app-surface-border)] bg-[var(--app-surface)] px-3 py-2.5 text-left font-[var(--app-font-sans)] font-semibold text-[var(--app-surface-text)] [&_span]:ml-2 [&_span]:text-[11px] [&_span]:font-normal [&_span]:text-[var(--app-surface-text-muted)]">{beforeLabel}<span>旧版本</span></th><th scope="col" className="sticky top-0 z-[1] border-b border-l border-[var(--app-surface-border)] bg-[var(--app-surface)] px-3 py-2.5 text-left font-[var(--app-font-sans)] font-semibold text-[var(--app-surface-text)] [&_span]:ml-2 [&_span]:text-[11px] [&_span]:font-normal [&_span]:text-[var(--app-surface-text-muted)]">{afterLabel}<span>当前内容</span></th></tr></thead>
    <tbody>{rows.length ? rows.map((row, index) => <tr key={index}>
      <Cell cell={row.before} side="before" /><Cell cell={row.after} side="after" />
    </tr>) : <tr><td colSpan={2} className="gc-diff-empty p-6 text-center text-[var(--app-surface-text-muted)]">两侧暂无内容</td></tr>}</tbody>
  </table>
}
