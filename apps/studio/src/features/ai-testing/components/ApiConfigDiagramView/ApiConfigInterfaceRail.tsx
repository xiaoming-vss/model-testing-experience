import { KeyOutlined, SafetyCertificateOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Input } from 'antd'
import type { ApiConfigCaseView, ApiConfigDiagramData } from '../../utils/apiConfigDiagram'
import type { ApiConfigContractView } from '../../utils/apiConfigContract'
import {
  METHOD_BASE,
  OVERVIEW_CARD,
  RAIL_ASIDE,
  RAIL_BADGE,
  RAIL_BADGE_AUTH,
  RAIL_BADGE_KEY,
  RAIL_ITEM_BASE,
  RAIL_ITEM_IDLE,
  RAIL_ITEM_SELECTED,
  SMALL_SECONDARY_TEXT,
  STAT_CELL,
  STAT_GRID,
  STRONG_TEXT,
  VAR_CHIP,
  methodTone,
} from './apiConfigClasses'

export function ApiConfigInterfaceRail({ data, contracts, filteredCases, selectedKey, query, onQueryChange, onSelect, showRules }: {
  data: ApiConfigDiagramData
  contracts: Map<string, ApiConfigContractView>
  filteredCases: ApiConfigCaseView[]
  selectedKey: string
  query: string
  onQueryChange: (value: string) => void
  onSelect: (key: string) => void
  showRules: boolean
}) {
  const summary = data.cases.reduce((result, apiCase) => {
    const contract = contracts.get(apiCase.key)
    result.requestFields += contract?.requestFieldCount ?? 0
    result.responseFields += contract?.responseFieldCount ?? 0
    result.keyExtractions += showRules && apiCase.extractRules.length
      ? apiCase.extractRules.length
      : contract?.keyExtractions.length ?? 0
    return result
  }, { requestFields: 0, responseFields: 0, keyExtractions: 0 })
  const variables = [...new Set(data.cases.flatMap((apiCase) => apiCase.usedVariables))]
  const count = filteredCases.length

  return <aside aria-label="接口导航与提取概览" className={RAIL_ASIDE}>
    <div className="flex items-center gap-2">
      <h2 className="m-0 text-[13px] font-semibold text-[var(--ai-text)]">接口</h2>
      <span aria-label={`${count} 个接口`} className="inline-flex min-w-[18px] items-center justify-center rounded-full border border-[var(--app-surface-border)] bg-[var(--app-surface)] px-1.5 font-mono text-[10px] text-[var(--ai-text-secondary)]">{count}</span>
    </div>
    <p className={`mt-1 ${SMALL_SECONDARY_TEXT}`}>审阅提取出的接口契约</p>

    <section className={OVERVIEW_CARD} aria-label="提取概览">
      <div className="flex items-baseline justify-between gap-3">
        <span className={SMALL_SECONDARY_TEXT}>提取概览</span>
        <span className="whitespace-nowrap text-[11px] text-[var(--ai-text-secondary)]"><b className={STRONG_TEXT}>{data.cases.length}</b> 个接口</span>
      </div>
      <div className={STAT_GRID}>
        <div className={STAT_CELL} role="group" aria-label={`请求字段 ${summary.requestFields}`}>
          <span className="text-[10px] text-[var(--ai-text-secondary)]">请求字段</span>
          <b className="text-[15px] font-semibold leading-tight text-[var(--ai-text)]">{summary.requestFields}</b>
        </div>
        <div className={STAT_CELL} role="group" aria-label={`响应字段 ${summary.responseFields}`}>
          <span className="text-[10px] text-[var(--ai-text-secondary)]">响应字段</span>
          <b className="text-[15px] font-semibold leading-tight text-[var(--ai-text)]">{summary.responseFields}</b>
        </div>
        <div className={STAT_CELL} role="group" aria-label={`认证头 ${data.authHeaderCount}`}>
          <span className="text-[10px] text-[var(--ai-text-secondary)]">认证头</span>
          <b className="text-[15px] font-semibold leading-tight text-[var(--ai-text)]">{data.authHeaderCount}</b>
        </div>
        <div className={STAT_CELL} role="group" aria-label={`关键提取 ${summary.keyExtractions}`}>
          <span className="text-[10px] text-[var(--ai-text-secondary)]">关键提取</span>
          <b className="text-[15px] font-semibold leading-tight text-[var(--ai-text)]">{summary.keyExtractions}</b>
        </div>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-[var(--app-frame-divider-soft)] pt-2.5 text-[10.5px] text-[var(--ai-text-secondary)]">
        <span>变量依赖</span>
        {variables.length ? variables.map((variable) => <span key={variable} className={VAR_CHIP}>{variable}</span>) : <span>无</span>}
      </div>
      {showRules ? <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-[var(--ai-text-secondary)]">
        <span>提取规则 <b className={STRONG_TEXT}>{data.totalExtractRules}</b></span>
        <span>断言规则 <b className={STRONG_TEXT}>{data.totalAssertRules}</b></span>
      </div> : null}
    </section>

    <Input className="mt-3 text-[12px]" allowClear prefix={<SearchOutlined aria-hidden />} placeholder="搜索名称、路径或方法"
      aria-label="搜索接口" value={query} onChange={(event) => onQueryChange(event.target.value)} />

    {filteredCases.length ? <nav aria-label="接口列表" className="mt-3 flex flex-col gap-0.5 max-[1200px]:flex-row max-[1200px]:gap-1.5 max-[1200px]:overflow-x-auto max-[1200px]:pb-1">
      {filteredCases.map((apiCase) => {
        const contract = contracts.get(apiCase.key)
        const hasRuleKeys = showRules && apiCase.extractRules.length > 0
        const keyCount = hasRuleKeys ? apiCase.extractRules.length : contract?.keyExtractions.length ?? 0
        const selected = apiCase.key === selectedKey
        const extra = [
          contract?.authHeader ? '包含认证头' : '',
          keyCount ? hasRuleKeys ? `${keyCount} 条提取规则` : `${keyCount} 个关键提取` : '',
        ].filter(Boolean).join('，')
        return <button type="button" key={apiCase.key} title={`${apiCase.method} ${apiCase.path}`}
          aria-current={selected ? 'true' : 'false'}
          aria-label={`${apiCase.method} ${apiCase.name}，${apiCase.path}，${contract?.totalFieldCount ?? 0} 个字段${extra ? `，${extra}` : ''}`}
          onClick={() => onSelect(apiCase.key)}
          className={`${RAIL_ITEM_BASE} ${selected ? RAIL_ITEM_SELECTED : RAIL_ITEM_IDLE}`}>
          <span className={`${METHOD_BASE} ${methodTone(apiCase.method)}`}>{apiCase.method}</span>
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="truncate text-[12.5px] font-medium text-[var(--ai-text)]">{apiCase.name}</span>
            <code className="truncate font-mono text-[10.5px] text-[var(--ai-text-secondary)]">{apiCase.path}</code>
          </span>
          <span className="flex flex-col items-end gap-1">
            <span className="whitespace-nowrap text-[10.5px] text-[var(--ai-text-secondary)]"><b className={STRONG_TEXT}>{contract?.totalFieldCount ?? 0}</b> 字段</span>
            <span className="flex items-center gap-0.5">
              {contract?.authHeader ? <span className={`${RAIL_BADGE} ${RAIL_BADGE_AUTH}`} title="包含认证头" aria-hidden><SafetyCertificateOutlined /></span> : null}
              {keyCount ? <span className={`${RAIL_BADGE} ${RAIL_BADGE_KEY}`} title={hasRuleKeys ? '包含提取规则' : '包含关键提取'} aria-hidden><KeyOutlined /></span> : null}
            </span>
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
      <span>共 {data.cases.length} 个接口</span>
      <span>{query.trim() ? `${filteredCases.length} 个匹配` : '只读预览'}</span>
    </div>
  </aside>
}
