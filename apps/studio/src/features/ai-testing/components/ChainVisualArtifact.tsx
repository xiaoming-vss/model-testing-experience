import { useMemo } from 'react'
import { buildVisualGroups } from '../utils/chainArtifact'

/** Generic structured preview for chain versions; raw JSON/YAML stays one switch away. */
export function ChainVisualArtifact({ content, emptyText = '暂无可视化内容' }: { content: string; emptyText?: string }) {
  const groups = useMemo(() => buildVisualGroups(content), [content])
  if (!content.trim()) return <div className="gc-visual-empty">{emptyText}</div>
  if (!groups.length) {
    return <div className="gc-visual-empty">当前产物无法结构化展示，请切换到原始内容查看。</div>
  }
  return <div className="gc-visual-groups">
    {groups.map(group => <section className="gc-visual-group" key={group.key}>
      <header>
        <span className="gc-visual-kind">{group.kind}</span>
        <strong>{group.title}</strong>
        {group.subtitle ? <small>{group.subtitle}</small> : null}
      </header>
      <div className="gc-visual-rows">
        {group.rows.map((row, index) => <div className="gc-visual-row" key={`${group.key}-${index}`}>
          <span>{row.label}</span>
          {row.value ? <p>{row.value}</p> : null}
        </div>)}
      </div>
    </section>)}
  </div>
}
