import type { MaterialBlock } from './requirementMaterial.types'

export function MaterialBlockContent({ block }: { block: MaterialBlock }) {
  const value = block.content
  if (block.kind === 'table' && Array.isArray(value.rows)) {
    const spans = Array.isArray(value.spans) ? value.spans as { row: number; column: number; rowSpan: number; columnSpan: number }[] : []
    return <div className="mt-2 overflow-x-auto"><table><tbody>{value.rows.map((row, i) => <tr key={i}>{Array.isArray(row) && row.map((cell, j) => {
      const span = spans.find(s => s.row === i && s.column === j)
      if (!span && spans.some(s => i >= s.row && i < s.row + s.rowSpan && j >= s.column && j < s.column + s.columnSpan)) return null
      return <td key={j} className="border border-app-surface-border px-2 py-1.5" rowSpan={span?.rowSpan} colSpan={span?.columnSpan}>{typeof cell === 'string' ? cell : '无法识别'}</td>
    })}</tr>)}</tbody></table></div>
  }
  if (block.kind === 'list' && Array.isArray(value.items)) return <ul className="m-0 pl-[18px] text-[11px] leading-[1.7] text-app-surface-text">{value.items.map((item, i) => <li key={i}>{String(item)}</li>)}</ul>
  if (block.kind === 'image') return <><p className="m-0 whitespace-pre-wrap text-[11px] leading-[1.6] text-app-surface-text [overflow-wrap:anywhere]">{typeof value.description === 'string' ? value.description : '图片内容未识别'}</p>{value.readStatus !== 'complete' && <small className="mt-1 block text-[10px] text-app-surface-text-muted">图片内容可能未完整识别，请核对原始材料。</small>}</>
  return <p className="m-0 whitespace-pre-wrap text-[11px] leading-[1.6] text-app-surface-text [overflow-wrap:anywhere]">{typeof value.text === 'string' ? value.text : '材料内容不可读取'}</p>
}
