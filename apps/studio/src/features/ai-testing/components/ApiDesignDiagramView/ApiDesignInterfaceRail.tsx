import { CheckCircleOutlined, SearchOutlined, WarningOutlined } from '@ant-design/icons'
import { Button, Input } from 'antd'
import type { ApiDesignDiagramData, ApiDesignInterfaceView } from '../../utils/apiDesignDiagram'
import { CATEGORY_ORDER, categoryMeta, METHOD_BASE, methodTone, SMALL_SECONDARY_TEXT, STRONG_TEXT } from './apiDesignClasses'

export function ApiDesignInterfaceRail({ data, filteredInterfaces, selectedKey, query, onQueryChange, onSelect, onJumpToUncovered }: {
  data: ApiDesignDiagramData
  filteredInterfaces: ApiDesignInterfaceView[]
  selectedKey: string
  query: string
  onQueryChange: (value: string) => void
  onSelect: (key: string) => void
  onJumpToUncovered: () => void
}) {
  const categories = [...CATEGORY_ORDER, ...Object.keys(data.categoryCounts).filter(category => !CATEGORY_ORDER.includes(category))]
  const totalCases = data.totalCases
  const count = query.trim() ? filteredInterfaces.length : data.interfaces.length

  return <aside aria-label="接口导航与覆盖概览"
    className="sticky top-0 z-[2] min-w-0 self-start border-r border-[var(--app-frame-divider-soft)] pr-4 max-h-[calc(100dvh-180px)] overflow-y-auto max-[1200px]:static max-[1200px]:max-h-none max-[1200px]:overflow-visible max-[1200px]:border-r-0 max-[1200px]:border-b max-[1200px]:border-[var(--app-frame-divider-soft)] max-[1200px]:pb-4">
    <div className="flex items-center gap-2">
      <h2 className="m-0 text-[13px] font-semibold text-[var(--ai-text)]">接口</h2>
      <span className="inline-flex min-w-[18px] items-center justify-center rounded-full border border-[var(--app-surface-border)] bg-[var(--app-surface)] px-1.5 font-mono text-[10px] text-[var(--ai-text-secondary)]" aria-label={`${count} 个接口`}>{count}</span>
    </div>
    <p className="mt-1 text-[11.5px] text-[var(--ai-text-secondary)]">按接口审阅用例覆盖</p>

    <section className="mt-3 rounded-[9px] border border-[var(--app-surface-border)] bg-[var(--app-surface-hover)] p-3" aria-label="用例覆盖概览">
      <div className="flex items-baseline justify-between gap-3">
        <span className={SMALL_SECONDARY_TEXT}>用例覆盖</span>
        <span className="whitespace-nowrap text-[11px] text-[var(--ai-text-secondary)]"><b className="text-[13px] font-semibold text-[var(--ai-text)]">{totalCases}</b> 条</span>
      </div>
      <div className="mt-2 flex h-1.5 gap-[3px] overflow-hidden rounded-[3px] bg-[var(--app-surface-chip)]" role="img"
        aria-label={categories.map(category => `${categoryMeta(category).label} ${data.categoryCounts[category] ?? 0} 条`).join('，')}>
        {categories.filter(category => (data.categoryCounts[category] ?? 0) > 0).map(category => <span key={category}
          className={`h-full min-w-[2px] ${categoryMeta(category).dot}`} style={{ flexGrow: data.categoryCounts[category] ?? 0 }} />)}
      </div>
      <div className="mt-2.5 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[var(--ai-text-secondary)]">
        {categories.map(category => <span className="inline-flex items-center gap-1.5 whitespace-nowrap" key={category}>
          <i className={`h-1.5 w-1.5 rounded-full ${categoryMeta(category).dot}`} aria-hidden />
          {categoryMeta(category).label} <b className={STRONG_TEXT}>{data.categoryCounts[category] ?? 0}</b>
        </span>)}
      </div>
      <div className={`mt-2.5 flex items-center gap-1.5 border-t border-[var(--app-frame-divider-soft)] pt-2.5 text-[11px] ${data.totalUncovered ? 'text-[var(--app-status-warning-text)]' : 'text-[var(--app-result-success-text)]'}`}>
        {data.totalUncovered ? <WarningOutlined aria-hidden /> : <CheckCircleOutlined aria-hidden />}
        <span>{data.totalUncovered ? `${data.totalUncovered} 条约束未覆盖` : '所有约束已覆盖'}</span>
        {data.totalUncovered ? <button type="button" className="ml-auto border-0 bg-transparent p-0 text-[11px] text-[var(--app-accent)] underline underline-offset-2 hover:text-[var(--app-accent-hover)]" onClick={onJumpToUncovered}>定位</button> : null}
      </div>
    </section>

    <Input className="mt-3 text-[12px]" allowClear prefix={<SearchOutlined aria-hidden />} placeholder="搜索名称、路径或方法"
      aria-label="搜索接口" value={query} onChange={event => onQueryChange(event.target.value)} />

    {filteredInterfaces.length ? <nav aria-label="接口列表" className="mt-3 flex flex-col gap-0.5 max-[1200px]:flex-row max-[1200px]:gap-1.5 max-[1200px]:overflow-x-auto max-[1200px]:pb-1">
      {filteredInterfaces.map(item => {
        const selected = item.key === selectedKey
        return <button type="button" key={item.key} title={`${item.method} ${item.path}`} aria-current={selected ? 'true' : 'false'}
          aria-label={`${item.method} ${item.name}，${item.path}，${item.cases.length} 条用例${item.uncovered.length ? `，${item.uncovered.length} 条约束未覆盖` : ''}`}
          onClick={() => onSelect(item.key)}
          className={`grid w-full grid-cols-[46px_minmax(0,1fr)_auto] items-center gap-2 rounded-[7px] border px-2 py-2 text-left transition-colors max-[1200px]:w-[240px] max-[1200px]:flex-none ${selected ? 'border-[var(--app-accent-border)] bg-[var(--app-accent-selection)]' : 'border-transparent hover:bg-[var(--app-surface-hover)]'}`}>
          <span className={`${METHOD_BASE} ${methodTone(item.method)}`}>{item.method}</span>
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="truncate text-[12.5px] font-medium text-[var(--ai-text)]">{item.name}</span>
            <code className="truncate font-mono text-[10.5px] text-[var(--ai-text-secondary)]">{item.path}</code>
          </span>
          <span className="flex flex-col items-end gap-1">
            <span className="whitespace-nowrap text-[10.5px] text-[var(--ai-text-secondary)]"><b className={STRONG_TEXT}>{item.cases.length}</b> 用例</span>
            {item.uncovered.length ? <span className="h-1.5 w-1.5 rounded-full bg-[var(--app-status-warning-text)]" aria-hidden /> : null}
          </span>
        </button>
      })}
    </nav> : <div className="mt-6 flex flex-col items-center gap-1.5 px-3 pb-3 text-center text-[var(--ai-text-secondary)]">
      <SearchOutlined className="mb-1 text-[20px] text-[var(--ai-text-muted)]" aria-hidden />
      <strong className="text-[12.5px] font-medium text-[var(--ai-text)]">没有匹配的接口</strong>
      <span className="text-[11.5px]">换个名称、路径或方法试试。</span>
      <Button size="small" className="mt-2" onClick={() => onQueryChange('')}>清除搜索</Button>
    </div>}

    <div className="mt-3 flex items-center justify-between gap-3 border-t border-[var(--app-frame-divider-soft)] pt-2.5 text-[10.5px] text-[var(--ai-text-muted)]">
      <span>共 {data.interfaces.length} 个接口</span>
      <span>{query.trim() ? `${filteredInterfaces.length} 个匹配` : '只读预览'}</span>
    </div>
  </aside>
}
