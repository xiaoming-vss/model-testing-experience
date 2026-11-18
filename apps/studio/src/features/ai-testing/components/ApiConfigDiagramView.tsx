import { DownOutlined, RightOutlined } from '@ant-design/icons'
import { Tag } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { normalizeApiConfigCases, stringifyCompact, type ApiConfigRule } from '../utils/apiConfigDiagram'

function getMethodTagColor(method: string) {
  const normalizedMethod = method.toUpperCase()
  if (normalizedMethod === 'GET') return 'blue'
  if (normalizedMethod === 'POST') return 'green'
  if (normalizedMethod === 'PUT' || normalizedMethod === 'PATCH') return 'orange'
  if (normalizedMethod === 'DELETE') return 'red'
  return 'default'
}

function ApiConfigPreviewField({ label, value }: { label: string; value: unknown }) {
  const text = stringifyCompact(value)
  if (!text) return null

  return (
    <div className="api-config-visual-field min-w-0 rounded-[8px] border border-[var(--app-frame-divider-soft)] bg-[var(--app-glass-surface-68)] p-2.5">
      <span className="text-[12px] font-bold leading-[18px] text-[var(--ai-text-secondary)]">{label}</span>
      <pre className="mt-1.5 max-h-[132px] overflow-auto whitespace-pre-wrap font-mono text-[12px] leading-[18px] text-[var(--ai-text)] [overflow-wrap:anywhere]">{text}</pre>
    </div>
  )
}

function ApiConfigRuleList({ title, rules, emptyText }: { title: string; rules: ApiConfigRule[]; emptyText: string }) {
  return (
    <div className="api-config-visual-rule-group min-w-0 rounded-[8px] border border-[var(--app-frame-divider-soft)] bg-[var(--app-picker-header-bg)] p-2.5">
      <div className="api-config-visual-rule-title flex items-center justify-between gap-2">
        <span className="text-[12px] font-bold leading-[18px] text-[var(--ai-text-secondary)]">{title}</span>
        <Tag color={rules.length > 0 ? 'cyan' : 'default'}>{rules.length}</Tag>
      </div>
      {rules.length > 0 ? (
        <div className="api-config-visual-rule-list mt-2 flex flex-col gap-2">
          {rules.map((rule, index) => (
            <div key={`${rule.name}-${index}`} className="api-config-visual-rule flex min-w-0 flex-col gap-[3px] border-l-2 border-[var(--app-frame-card-border-hover)] pl-2">
              <strong className="text-[12px] leading-[18px] text-[var(--ai-text)] [overflow-wrap:anywhere]">{rule.name}</strong>
              {rule.detail ? <span className="text-[12px] leading-[18px] text-[var(--ai-text-secondary)] [overflow-wrap:anywhere]">{rule.detail}</span> : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="api-config-visual-empty mt-2 text-[12px] leading-[18px] text-[var(--ai-text-secondary)] [overflow-wrap:anywhere]">{emptyText}</div>
      )}
    </div>
  )
}

export function ApiConfigDiagramView({
  content,
  defaultCollapsed = false,
  showRules = false,
}: {
  content: string
  defaultCollapsed?: boolean
  showRules?: boolean
}) {
  const diagramData = useMemo(() => normalizeApiConfigCases(content), [content])
  const [collapsedCaseKeys, setCollapsedCaseKeys] = useState<Set<string>>(
    () => new Set(defaultCollapsed ? diagramData?.cases.map((apiCase) => apiCase.key) : []),
  )

  useEffect(() => {
    setCollapsedCaseKeys(new Set(defaultCollapsed ? diagramData?.cases.map((apiCase) => apiCase.key) : []))
  }, [defaultCollapsed, diagramData])

  if (!diagramData) {
    return <div className="ai-task-run-result-popover-empty flex min-h-[120px] items-center justify-center text-[13px] leading-5 text-[var(--ai-text-secondary)]">当前中间配置无法解析为 API 链路</div>
  }

  return (
    <div className="api-config-visual-view min-h-0 text-[var(--ai-text)]">
      <div className="api-config-visual-stats sticky top-0 z-[2] flex flex-wrap gap-2 bg-[var(--ai-popover-surface)] pb-3">
        <Tag color="blue">接口 {diagramData.cases.length}</Tag>
        {showRules ? <Tag color="cyan">提取 {diagramData.totalExtractRules}</Tag> : null}
        {showRules ? <Tag color="purple">断言 {diagramData.totalAssertRules}</Tag> : null}
        <Tag color="green">认证头 {diagramData.authHeaderCount}</Tag>
      </div>
      <div className="api-config-visual-chain flex flex-col gap-0 pb-1">
        {diagramData.cases.map((apiCase, index) => {
          const collapsed = collapsedCaseKeys.has(apiCase.key)
          const toggleCase = () => {
            setCollapsedCaseKeys((current) => {
              const next = new Set(current)
              if (next.has(apiCase.key)) next.delete(apiCase.key)
              else next.add(apiCase.key)
              return next
            })
          }

          return (
          <div key={apiCase.key} className="api-config-visual-step flex flex-col items-stretch">
            <article className={`api-config-visual-card min-w-0 overflow-hidden rounded-[10px] border border-[var(--app-review-outline)] bg-[linear-gradient(180deg,var(--app-glass-surface-92),var(--app-review-muted-bg)),var(--ai-card)] shadow-[0_10px_24px_var(--app-glass-request-shadow-selected)]${collapsed ? ' collapsed' : ''}`}>
              <button
                type="button"
                className="api-config-visual-card-head flex w-full min-w-0 cursor-pointer items-center justify-between gap-3 rounded-none border-0 bg-transparent px-4 py-3.5 text-left font-[inherit] text-inherit transition-colors duration-150 hover:bg-[var(--app-review-accent-bg)] focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--app-review-focus-ring)]"
                aria-expanded={!collapsed}
                aria-label={`${collapsed ? '展开' : '折叠'} ${apiCase.method} ${apiCase.name}`}
                onClick={toggleCase}
              >
                <div className="api-config-visual-method-line flex min-w-0 items-center gap-2">
                  <span className="api-config-visual-collapse-icon inline-flex w-3.5 flex-[0_0_14px] items-center justify-center text-[11px] text-[var(--ai-text-secondary)]" aria-hidden>
                    {collapsed ? <RightOutlined /> : <DownOutlined />}
                  </span>
                  <Tag color={getMethodTagColor(apiCase.method)}>{apiCase.method}</Tag>
                  <strong className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[14px] leading-[22px] text-[var(--ai-text)]">{apiCase.name}</strong>
                </div>
                {apiCase.orderNo ? <span className="api-config-visual-order flex-none text-[12px] leading-5 text-[var(--ai-text-secondary)]">#{apiCase.orderNo}</span> : null}
              </button>
              {!collapsed ? (
                <div className="api-config-visual-card-body px-4 pb-3.5">
                  <div className="api-config-visual-path mt-2 rounded-[8px] bg-[var(--app-request-card-shadow-hover)] px-2.5 py-2 font-mono text-[12px] leading-5 text-[var(--ai-text)] [overflow-wrap:anywhere]">{apiCase.path}</div>
                  <div className="api-config-visual-variable-row mt-2.5 flex min-h-6 flex-wrap items-center gap-1.5">
                    {apiCase.usedVariables.map((variable) => (
                      <Tag key={`used-${variable}`} color="gold">使用 {variable}</Tag>
                    ))}
                    {showRules ? apiCase.extractedVariables.map((variable) => (
                      <Tag key={`extract-${variable}`} color="success">提取 {variable}</Tag>
                    )) : null}
                    {apiCase.usedVariables.length === 0 && apiCase.extractedVariables.length === 0 ? (
                      <span className="api-config-visual-muted flex-none text-[12px] leading-5 text-[var(--ai-text-secondary)]">无变量依赖</span>
                    ) : null}
                  </div>
                  <div className="api-config-visual-grid mt-3 grid grid-cols-2 gap-2.5">
                    <ApiConfigPreviewField label="Headers" value={apiCase.headers} />
                    <ApiConfigPreviewField label="Query" value={apiCase.query} />
                    <ApiConfigPreviewField label="Body" value={apiCase.body} />
                    <ApiConfigPreviewField label="Response" value={apiCase.response} />
                  </div>
                  {showRules ? <div className="api-config-visual-rules mt-3 grid grid-cols-2 gap-2.5">
                    <ApiConfigRuleList title="提取规则" rules={apiCase.extractRules} emptyText="暂无提取规则" />
                    <ApiConfigRuleList title="断言规则" rules={apiCase.assertRules} emptyText="暂无断言规则" />
                  </div> : null}
                </div>
              ) : null}
            </article>
            {index < diagramData.cases.length - 1 ? <div className="api-config-visual-connector ml-7 h-[22px] w-0.5 bg-[linear-gradient(180deg,var(--app-review-scrollbar),var(--app-terminal-scrollbar-active))]" /> : null}
          </div>
          )
        })}
      </div>
    </div>
  )
}

/** 候选 API 用例的只读预览，默认收起每条用例的细节。 */
export function ApiCandidateResultView({ content }: { content: string }) {
  if (!normalizeApiConfigCases(content)) {
    return <div className="ai-task-run-result-popover-empty flex min-h-[120px] items-center justify-center text-[13px] leading-5 text-[var(--ai-text-secondary)]">当前候选结果无法解析为 API 用例</div>
  }

  return <ApiConfigDiagramView content={content} defaultCollapsed showRules />
}
