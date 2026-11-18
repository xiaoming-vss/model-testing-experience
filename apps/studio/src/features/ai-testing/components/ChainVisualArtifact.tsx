import { useMemo } from 'react'
import { buildVisualGroups } from '../utils/chainArtifact'

/** Generic structured preview for chain versions; raw JSON/YAML stays one switch away. */
export function ChainVisualArtifact({ content, emptyText = '暂无可视化内容' }: { content: string; emptyText?: string }) {
  const groups = useMemo(() => buildVisualGroups(content), [content])
  if (!content.trim()) return <div className="gc-visual-empty px-3 py-7 text-center text-[12px] text-[var(--app-surface-text-muted)]">{emptyText}</div>
  if (!groups.length) {
    return <div className="gc-visual-empty px-3 py-7 text-center text-[12px] text-[var(--app-surface-text-muted)]">当前产物无法结构化展示，请切换到原始内容查看。</div>
  }
  return <div className="gc-visual-groups flex flex-col gap-2 pt-[9px]">
    {groups.map(group => <section className="gc-visual-group overflow-hidden rounded-[10px] border border-[var(--app-surface-border)] bg-[var(--app-surface)]" key={group.key}>
      <header className="flex items-baseline gap-2 border-b border-[var(--app-surface-divider)] bg-[var(--app-list-toolbar-bg)] px-[11px] py-2">
        <span className="gc-visual-kind flex-none rounded-[4px] bg-[var(--app-accent-surface)] px-[5px] text-[10px] text-[var(--app-accent)]">{group.kind}</span>
        <strong className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12px]">{group.title}</strong>
        {group.subtitle ? <small className="ml-auto text-[11px] text-[var(--app-surface-text-muted)]">{group.subtitle}</small> : null}
      </header>
      <div className="gc-visual-rows flex flex-col">
        {group.rows.map((row, index) => <div className="gc-visual-row grid grid-cols-[minmax(86px,24%)_minmax(0,1fr)] gap-2.5 border-t border-[var(--app-surface-divider)] px-[11px] py-1.5 text-[12px] first:border-t-0 [&>p]:m-0 [&>p]:break-words [&>p]:leading-[1.55] [&>p]:text-[var(--app-surface-text)] [&>span]:text-[var(--app-surface-text-muted)]" key={`${group.key}-${index}`}>
          <span>{row.label}</span>
          {row.value ? <p>{row.value}</p> : null}
        </div>)}
      </div>
    </section>)}
  </div>
}
