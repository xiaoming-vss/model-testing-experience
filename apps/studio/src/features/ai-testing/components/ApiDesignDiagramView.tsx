import { DownOutlined, RightOutlined } from '@ant-design/icons'
import { Button, Empty, Tag } from 'antd'
import { useMemo, useState } from 'react'
import { normalizeApiDesign } from '../utils/apiDesignDiagram'

function methodColor(method: string) {
  if (method === 'GET') return 'blue'
  if (method === 'POST') return 'green'
  if (method === 'PUT' || method === 'PATCH') return 'orange'
  if (method === 'DELETE') return 'red'
  return 'default'
}

function categoryColor(category: string) {
  if (category === 'positive') return 'green'
  if (category === 'negative') return 'red'
  if (category === 'boundary') return 'orange'
  return 'default'
}

function priorityColor(priority: string) {
  if (priority === 'P0') return 'magenta'
  if (priority === 'P1') return 'blue'
  return 'default'
}

function statusColor(statusClass: string) {
  return statusClass === '2xx' ? 'green' : statusClass === '4xx' ? 'red' : 'default'
}

function patchOpColor(op: string) {
  if (op === 'add') return 'green'
  if (op === 'remove') return 'red'
  if (op === 'replace') return 'orange'
  return 'default'
}

function DesignState({ title, description, onShowRaw }: { title: string; description: string; onShowRaw?: () => void }) {
  return <div className="api-design-visual-state flex min-h-[240px] flex-col items-center justify-center gap-3 p-6">
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<div className="api-design-visual-state-copy flex flex-col gap-1"><strong className="text-[13px] text-[var(--ai-text)]">{title}</strong><span className="text-[12px] text-[var(--ai-text-secondary)]">{description}</span></div>} />
    {onShowRaw ? <Button size="small" onClick={onShowRaw}>查看原文</Button> : null}
  </div>
}

export function ApiDesignDiagramView({ content, onShowRaw }: { content: string; onShowRaw?: () => void }) {
  const data = useMemo(() => normalizeApiDesign(content), [content])
  const [collapsedCaseKeys, setCollapsedCaseKeys] = useState<Set<string>>(() => new Set())
  const allCaseKeys = useMemo(
    () => data?.interfaces.flatMap(item => item.cases.map(apiCase => apiCase.key)) ?? [],
    [data],
  )
  const allCollapsed = allCaseKeys.length > 0 && allCaseKeys.every(key => collapsedCaseKeys.has(key))
  const toggleCase = (key: string) => {
    setCollapsedCaseKeys(current => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }
  const toggleAll = () => {
    setCollapsedCaseKeys(allCollapsed ? new Set() : new Set(allCaseKeys))
  }

  if (!data) {
    return <DesignState title="当前设计产物无法解析" description="内容可能是正在编辑的中间态，或不是合法的 API 用例设计 JSON。" onShowRaw={onShowRaw} />
  }
  if (data.totalCases === 0) {
    return <DesignState title="暂无可视化的接口用例设计" description="当前设计产物还没有任何用例，请重新生成或切换到原文检查。" onShowRaw={onShowRaw} />
  }

  return <div className="api-design-visual-view min-h-0 text-[var(--ai-text)]">
    <div className="api-design-visual-stats sticky top-0 z-[2] flex flex-wrap items-center gap-2 bg-[var(--ai-popover-surface)] pb-3">
      <Tag color="blue">接口 {data.interfaces.length}</Tag>
      <Tag color="cyan">用例 {data.totalCases}</Tag>
      <Tag color="green">正向 {data.categoryCounts.positive ?? 0}</Tag>
      <Tag color="red">反向 {data.categoryCounts.negative ?? 0}</Tag>
      <Tag color="orange">边界 {data.categoryCounts.boundary ?? 0}</Tag>
      <Tag color={data.totalUncovered ? 'gold' : 'default'}>未覆盖 {data.totalUncovered}</Tag>
      <Button size="small" type="text" className="api-design-visual-toggle-all ms-auto text-[11px] text-[var(--ai-text-secondary)]" onClick={toggleAll}>
        {allCollapsed ? '展开全部' : '收起全部'}
      </Button>
    </div>
    <div className="api-design-visual-list flex flex-col gap-3.5 pb-1">
      {data.interfaces.map(item => <article className="api-design-visual-interface min-w-0 overflow-hidden rounded-[10px] border border-[var(--app-review-outline)] bg-[linear-gradient(180deg,var(--app-glass-surface-92),var(--app-review-muted-bg)),var(--ai-card)] shadow-[0_10px_24px_var(--app-glass-request-shadow-selected)]" key={item.key}>
        <header className="api-design-visual-interface-head flex items-center gap-2.5 border-b border-[var(--app-frame-divider-soft)] bg-[var(--app-picker-header-bg)] px-3 py-2.5">
          <Tag color={methodColor(item.method)}>{item.method}</Tag>
          <div className="flex min-w-0 flex-auto flex-col gap-0.5"><strong className="overflow-hidden text-ellipsis whitespace-nowrap text-[13px]">{item.name}</strong><span className="overflow-hidden text-ellipsis whitespace-nowrap text-[11px] text-[var(--ai-text-secondary)]">{item.path}</span></div>
          <span className="api-design-visual-count max-w-[50%] overflow-hidden text-ellipsis whitespace-nowrap text-[11px] text-[var(--ai-text-secondary)]">
            {item.cases.length} 条用例
            {item.categoryCounts.positive ? ` · 正 ${item.categoryCounts.positive}` : ''}
            {item.categoryCounts.negative ? ` · 反 ${item.categoryCounts.negative}` : ''}
            {item.categoryCounts.boundary ? ` · 边 ${item.categoryCounts.boundary}` : ''}
          </span>
        </header>
        <div className="api-design-visual-cases flex flex-col">
          {item.cases.map(apiCase => {
            const collapsed = collapsedCaseKeys.has(apiCase.key)
            return <section className={`api-design-visual-case flex flex-col gap-[7px] border-b border-[var(--app-frame-divider-soft)] px-3 py-[11px] last:border-b-0${collapsed ? ' is-collapsed' : ''}`} key={apiCase.key}>
              <button type="button" className="api-design-visual-case-head flex w-full cursor-pointer flex-wrap items-center gap-1.5 border-0 bg-transparent p-0 text-left font-[inherit] text-inherit hover:[&_strong]:text-[var(--ai-accent)] focus-visible:rounded-[4px] focus-visible:outline-2 focus-visible:outline-offset-[3px] focus-visible:outline-[var(--app-review-focus-ring)] focus-visible:[&_strong]:text-[var(--ai-accent)]"
                aria-expanded={!collapsed}
                aria-label={`${collapsed ? '展开' : '收起'}用例 ${apiCase.title}`}
                onClick={() => toggleCase(apiCase.key)}>
                <span className="api-design-visual-case-toggle inline-flex flex-none items-center text-[10px] text-[var(--ai-text-secondary)]" aria-hidden>{collapsed ? <RightOutlined /> : <DownOutlined />}</span>
                <Tag color={categoryColor(apiCase.category)}>{apiCase.categoryLabel}</Tag>
                {apiCase.priority ? <Tag color={priorityColor(apiCase.priority)}>{apiCase.priority}</Tag> : null}
                <strong className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[12px]">{apiCase.title}</strong>
                {apiCase.statusClass ? <Tag color={statusColor(apiCase.statusClass)}>{apiCase.statusClass}</Tag> : null}
              </button>
              {apiCase.intent ? <p className="api-design-visual-intent m-0 text-[12px] leading-[1.5] text-[var(--ai-text-secondary)]">{apiCase.intent}</p> : null}
              {!collapsed ? <div className="api-design-visual-case-body flex flex-col gap-[7px]">
                <div className="api-design-visual-basis flex flex-wrap items-baseline gap-1.5 text-[11px]"><span className="flex-none text-[var(--ai-text-secondary)]">设计依据</span><code className="rounded-[5px] border border-[var(--app-review-outline)] bg-[var(--app-glass-surface-68)] px-1.5 py-px font-mono text-[11px]">{apiCase.basisLabel}</code></div>
                {apiCase.patchOps.length ? <ul className="api-design-visual-patches m-0 flex list-none flex-col gap-1 rounded-[7px] border border-[var(--app-review-outline)] bg-[var(--app-glass-surface-68)] px-2.5 py-[7px]">
                  {apiCase.patchOps.map(patch => <li className={`is-${patch.op} flex flex-wrap items-center gap-1.5 text-[11px] leading-[1.5]`} key={`${apiCase.key}-${patch.key}`}>
                    <Tag color={patchOpColor(patch.op)}>{patch.opLabel}</Tag>
                    <code className="rounded-[5px] border border-[var(--app-review-outline)] bg-[var(--app-glass-surface-68)] px-1.5 py-px font-mono text-[11px]">{patch.target}</code>
                    {patch.valueLabel ? <code className="api-design-visual-patch-value rounded-[5px] border border-[var(--app-review-outline)] bg-[var(--app-glass-surface-68)] px-1.5 py-px font-mono text-[11px] text-[var(--ai-text-secondary)]">{patch.valueLabel}</code> : null}
                  </li>)}
                </ul> : <div className="api-design-visual-patch-empty text-[11px] not-italic text-[var(--ai-text-secondary)]">无参数变异，使用提取基线请求</div>}
                {apiCase.assertions.length ? <div className="api-design-visual-assertions flex flex-wrap items-baseline gap-1.5 text-[11px]">
                  <span className="flex-none text-[var(--ai-text-secondary)]">业务断言</span>
                  {apiCase.assertions.map((assertion, index) => <code className="rounded-[5px] border border-[var(--app-review-outline)] bg-[var(--app-glass-surface-68)] px-1.5 py-px font-mono text-[11px]" key={`${apiCase.key}-assert-${index}`}>{assertion}</code>)}
                </div> : <div className="api-design-visual-assertions is-empty flex flex-wrap items-baseline gap-1.5 text-[11px]">
                  <span>业务断言</span>
                  <em className="not-italic text-[var(--ai-text-secondary)]">{apiCase.statusClass === '4xx' ? '仅校验状态区间' : '无额外业务断言'}</em>
                </div>}
              </div> : null}
            </section>
          })}
        </div>
        {item.uncovered.length ? <div className="api-design-visual-uncovered flex flex-col gap-1.5 border-t border-dashed border-[var(--app-review-outline)] bg-[var(--app-glass-surface-68)] px-3 py-2.5">
          <strong className="text-[11px] text-[var(--ai-text-secondary)]">未覆盖约束</strong>
          {item.uncovered.map(row => <div className="api-design-visual-uncovered-row flex flex-wrap items-center gap-1.5 text-[11px]" key={row.key}>
            <Tag>{row.kindLabel}</Tag>
            <code className="rounded-[5px] border border-[var(--app-review-outline)] bg-[var(--app-glass-surface-68)] px-1.5 py-px font-mono text-[11px]">{row.fieldLabel}{row.constraint ? ` · ${row.constraint}` : ''}</code>
            <em className="not-italic text-[var(--ai-text-secondary)]">{row.reasonLabel}</em>
          </div>)}
        </div> : null}
      </article>)}
    </div>
  </div>
}
