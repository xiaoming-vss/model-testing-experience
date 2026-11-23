import { useId } from 'react'
import type { ApiConfigFieldView } from '../../utils/apiConfigContract'
import { ApiConfigFieldTable } from './ApiConfigFieldTable'
import {
  GROUP_COUNT,
  GROUP_HEAD,
  GROUP_TITLE,
  RAW_BODY,
  REQUEST_GRID,
  SECTION,
  SECTION_COUNT,
  SECTION_DESC,
  SECTION_HEAD,
  SECTION_TITLE,
  requestGroupLayout,
} from './apiConfigClasses'

export type ApiConfigRequestGroup = {
  key: string
  title: string
  rows: ApiConfigFieldView[]
  variant: 'header' | 'field'
  rawBody?: string
}

function groupFieldCount(group: ApiConfigRequestGroup) {
  return group.rows.filter((row) => row.kind === 'field').length || (group.rawBody ? 1 : 0)
}

export function ApiConfigRequestSection({ groups, caseKey, idPrefix, collapsedPaths, onTogglePath }: {
  groups: ApiConfigRequestGroup[]
  caseKey: string
  idPrefix: string
  collapsedPaths: Set<string>
  onTogglePath: (path: string) => void
}) {
  const titleId = useId()
  const total = groups.reduce((sum, group) => sum + groupFieldCount(group), 0)
  const hint = groups.map((group) => {
    const count = groupFieldCount(group)
    return group.title === '请求头' ? `${count} 个请求头` : `${count} 个 ${group.title} 字段`
  }).join(' · ')

  return <section className={SECTION} aria-labelledby={titleId}>
    <header className={SECTION_HEAD}>
      <h2 id={titleId} className={SECTION_TITLE}>请求</h2>
      <span className={SECTION_COUNT}>{total} 个字段</span>
      <span className={SECTION_DESC}>{hint}</span>
    </header>
    <div className={REQUEST_GRID[groups.length] ?? REQUEST_GRID[1]}>
      {groups.map((group, index) => <section key={group.key} className={`min-w-0 ${requestGroupLayout(index, groups.length)}`} aria-label={group.title}>
        <header className={GROUP_HEAD}>
          <h3 className={GROUP_TITLE}>{group.title}</h3>
          <span className={GROUP_COUNT}>{groupFieldCount(group)}</span>
        </header>
        {group.rawBody
          ? <pre className={RAW_BODY}>{group.rawBody}</pre>
          : <ApiConfigFieldTable rows={group.rows} variant={group.variant}
            label={group.title === '请求头' ? '请求头字段' : `${group.title} 字段`} caseKey={caseKey} section={group.key}
            idPrefix={idPrefix} collapsedPaths={collapsedPaths} onTogglePath={onTogglePath} />}
      </section>)}
    </div>
  </section>
}
