import { useMemo } from 'react'
import { diffArtifact, splitDiffLines, type DiffCell } from '../utils/chainArtifact'

function Cell({ cell, side }: { cell?: DiffCell; side: 'before' | 'after' }) {
  return <td className={`gc-diff-cell${cell?.changed ? side === 'before' ? ' is-remove' : ' is-add' : ''}${!cell ? ' is-empty' : ''}`}>
    {cell ? <div className="gc-diff-line">
      <span className="gc-diff-number" aria-hidden="true">{cell.lineNumber}</span>
      <span className="gc-diff-sign" aria-label={cell.changed ? side === 'before' ? '删除' : '新增' : undefined}>{cell.changed ? side === 'before' ? '−' : '+' : ' '}</span>
      <code>{cell.text || ' '}</code>
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
  return <table className="gc-diff" aria-label="版本差异">
    <thead><tr><th scope="col">{beforeLabel}<span>旧版本</span></th><th scope="col">{afterLabel}<span>当前内容</span></th></tr></thead>
    <tbody>{rows.length ? rows.map((row, index) => <tr key={index}>
      <Cell cell={row.before} side="before" /><Cell cell={row.after} side="after" />
    </tr>) : <tr><td colSpan={2} className="gc-diff-empty">两侧暂无内容</td></tr>}</tbody>
  </table>
}
