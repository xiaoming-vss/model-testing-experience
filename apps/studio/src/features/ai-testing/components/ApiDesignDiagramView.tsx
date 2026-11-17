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
  return <div className="api-design-visual-state">
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<div className="api-design-visual-state-copy"><strong>{title}</strong><span>{description}</span></div>} />
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

  return <div className="api-design-visual-view">
    <div className="api-design-visual-stats">
      <Tag color="blue">接口 {data.interfaces.length}</Tag>
      <Tag color="cyan">用例 {data.totalCases}</Tag>
      <Tag color="green">正向 {data.categoryCounts.positive ?? 0}</Tag>
      <Tag color="red">反向 {data.categoryCounts.negative ?? 0}</Tag>
      <Tag color="orange">边界 {data.categoryCounts.boundary ?? 0}</Tag>
      <Tag color={data.totalUncovered ? 'gold' : 'default'}>未覆盖 {data.totalUncovered}</Tag>
      <Button size="small" type="text" className="api-design-visual-toggle-all" onClick={toggleAll}>
        {allCollapsed ? '展开全部' : '收起全部'}
      </Button>
    </div>
    <div className="api-design-visual-list">
      {data.interfaces.map(item => <article className="api-design-visual-interface" key={item.key}>
        <header className="api-design-visual-interface-head">
          <Tag color={methodColor(item.method)}>{item.method}</Tag>
          <div><strong>{item.name}</strong><span>{item.path}</span></div>
          <span className="api-design-visual-count">
            {item.cases.length} 条用例
            {item.categoryCounts.positive ? ` · 正 ${item.categoryCounts.positive}` : ''}
            {item.categoryCounts.negative ? ` · 反 ${item.categoryCounts.negative}` : ''}
            {item.categoryCounts.boundary ? ` · 边 ${item.categoryCounts.boundary}` : ''}
          </span>
        </header>
        <div className="api-design-visual-cases">
          {item.cases.map(apiCase => {
            const collapsed = collapsedCaseKeys.has(apiCase.key)
            return <section className={`api-design-visual-case${collapsed ? ' is-collapsed' : ''}`} key={apiCase.key}>
              <button type="button" className="api-design-visual-case-head"
                aria-expanded={!collapsed}
                aria-label={`${collapsed ? '展开' : '收起'}用例 ${apiCase.title}`}
                onClick={() => toggleCase(apiCase.key)}>
                <span className="api-design-visual-case-toggle" aria-hidden>{collapsed ? <RightOutlined /> : <DownOutlined />}</span>
                <Tag color={categoryColor(apiCase.category)}>{apiCase.categoryLabel}</Tag>
                {apiCase.priority ? <Tag color={priorityColor(apiCase.priority)}>{apiCase.priority}</Tag> : null}
                <strong>{apiCase.title}</strong>
                {apiCase.statusClass ? <Tag color={statusColor(apiCase.statusClass)}>{apiCase.statusClass}</Tag> : null}
              </button>
              {apiCase.intent ? <p className="api-design-visual-intent">{apiCase.intent}</p> : null}
              {!collapsed ? <div className="api-design-visual-case-body">
                <div className="api-design-visual-basis"><span>设计依据</span><code>{apiCase.basisLabel}</code></div>
                {apiCase.patchOps.length ? <ul className="api-design-visual-patches">
                  {apiCase.patchOps.map(patch => <li className={`is-${patch.op}`} key={`${apiCase.key}-${patch.key}`}>
                    <Tag color={patchOpColor(patch.op)}>{patch.opLabel}</Tag>
                    <code>{patch.target}</code>
                    {patch.valueLabel ? <code className="api-design-visual-patch-value">{patch.valueLabel}</code> : null}
                  </li>)}
                </ul> : <div className="api-design-visual-patch-empty">无参数变异，使用提取基线请求</div>}
                {apiCase.assertions.length ? <div className="api-design-visual-assertions">
                  <span>业务断言</span>
                  {apiCase.assertions.map((assertion, index) => <code key={`${apiCase.key}-assert-${index}`}>{assertion}</code>)}
                </div> : <div className="api-design-visual-assertions is-empty">
                  <span>业务断言</span>
                  <em>{apiCase.statusClass === '4xx' ? '仅校验状态区间' : '无额外业务断言'}</em>
                </div>}
              </div> : null}
            </section>
          })}
        </div>
        {item.uncovered.length ? <div className="api-design-visual-uncovered">
          <strong>未覆盖约束</strong>
          {item.uncovered.map(row => <div className="api-design-visual-uncovered-row" key={row.key}>
            <Tag>{row.kindLabel}</Tag>
            <code>{row.fieldLabel}{row.constraint ? ` · ${row.constraint}` : ''}</code>
            <em>{row.reasonLabel}</em>
          </div>)}
        </div> : null}
      </article>)}
    </div>
  </div>
}
