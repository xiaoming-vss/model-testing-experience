import { DownOutlined, RightOutlined } from '@ant-design/icons'
import { Tag } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { normalizeApiConfigCases, stringifyCompact, type ApiConfigRule } from '../utils/apiConfigDiagram'
import { ArtifactModeSwitch } from './ArtifactViewTabs'
import '../styles/api-config-result.css'

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
    <div className="api-config-visual-field">
      <span>{label}</span>
      <pre>{text}</pre>
    </div>
  )
}

function ApiConfigRuleList({ title, rules, emptyText }: { title: string; rules: ApiConfigRule[]; emptyText: string }) {
  return (
    <div className="api-config-visual-rule-group">
      <div className="api-config-visual-rule-title">
        <span>{title}</span>
        <Tag color={rules.length > 0 ? 'cyan' : 'default'}>{rules.length}</Tag>
      </div>
      {rules.length > 0 ? (
        <div className="api-config-visual-rule-list">
          {rules.map((rule, index) => (
            <div key={`${rule.name}-${index}`} className="api-config-visual-rule">
              <strong>{rule.name}</strong>
              {rule.detail ? <span>{rule.detail}</span> : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="api-config-visual-empty">{emptyText}</div>
      )}
    </div>
  )
}

export function ApiConfigDiagramView({ content, defaultCollapsed = false }: { content: string; defaultCollapsed?: boolean }) {
  const diagramData = useMemo(() => normalizeApiConfigCases(content), [content])
  const [collapsedCaseKeys, setCollapsedCaseKeys] = useState<Set<string>>(
    () => new Set(defaultCollapsed ? diagramData?.cases.map((apiCase) => apiCase.key) : []),
  )

  useEffect(() => {
    setCollapsedCaseKeys(new Set(defaultCollapsed ? diagramData?.cases.map((apiCase) => apiCase.key) : []))
  }, [defaultCollapsed, diagramData])

  if (!diagramData) {
    return <div className="ai-task-run-result-popover-empty">当前中间配置无法解析为 API 链路</div>
  }

  return (
    <div className="api-config-visual-view">
      <div className="api-config-visual-stats">
        <Tag color="blue">接口 {diagramData.cases.length}</Tag>
        <Tag color="cyan">提取 {diagramData.totalExtractRules}</Tag>
        <Tag color="purple">断言 {diagramData.totalAssertRules}</Tag>
        <Tag color="green">认证头 {diagramData.authHeaderCount}</Tag>
      </div>
      <div className="api-config-visual-chain">
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
          <div key={apiCase.key} className="api-config-visual-step">
            <article className={`api-config-visual-card${collapsed ? ' collapsed' : ''}`}>
              <button
                type="button"
                className="api-config-visual-card-head"
                aria-expanded={!collapsed}
                aria-label={`${collapsed ? '展开' : '折叠'} ${apiCase.method} ${apiCase.name}`}
                onClick={toggleCase}
              >
                <div className="api-config-visual-method-line">
                  <span className="api-config-visual-collapse-icon" aria-hidden>
                    {collapsed ? <RightOutlined /> : <DownOutlined />}
                  </span>
                  <Tag color={getMethodTagColor(apiCase.method)}>{apiCase.method}</Tag>
                  <strong>{apiCase.name}</strong>
                </div>
                {apiCase.orderNo ? <span className="api-config-visual-order">#{apiCase.orderNo}</span> : null}
              </button>
              {!collapsed ? (
                <div className="api-config-visual-card-body">
                  <div className="api-config-visual-path">{apiCase.path}</div>
                  <div className="api-config-visual-variable-row">
                    {apiCase.usedVariables.map((variable) => (
                      <Tag key={`used-${variable}`} color="gold">使用 {variable}</Tag>
                    ))}
                    {apiCase.extractedVariables.map((variable) => (
                      <Tag key={`extract-${variable}`} color="success">提取 {variable}</Tag>
                    ))}
                    {apiCase.usedVariables.length === 0 && apiCase.extractedVariables.length === 0 ? (
                      <span className="api-config-visual-muted">无变量依赖</span>
                    ) : null}
                  </div>
                  <div className="api-config-visual-grid">
                    <ApiConfigPreviewField label="Headers" value={apiCase.headers} />
                    <ApiConfigPreviewField label="Query" value={apiCase.query} />
                    <ApiConfigPreviewField label="Body" value={apiCase.body} />
                    <ApiConfigPreviewField label="Response" value={apiCase.response} />
                  </div>
                  <div className="api-config-visual-rules">
                    <ApiConfigRuleList title="提取规则" rules={apiCase.extractRules} emptyText="暂无提取规则" />
                    <ApiConfigRuleList title="断言规则" rules={apiCase.assertRules} emptyText="暂无断言规则" />
                  </div>
                </div>
              ) : null}
            </article>
            {index < diagramData.cases.length - 1 ? <div className="api-config-visual-connector" /> : null}
          </div>
          )
        })}
      </div>
    </div>
  )
}

/** 查看中间配置：图预览与 JSON 原文切换。 */
export function ApiConfigResultView({ content }: { content: string }) {
  const canRenderDiagram = Boolean(normalizeApiConfigCases(content))
  const [activeView, setActiveView] = useState<'diagram' | 'json'>('diagram')

  return (
    <div className="api-config-result-tabs">
      <ArtifactModeSwitch copyText={activeView === 'json' ? content : undefined} value={activeView} onChange={(value) => setActiveView(value as 'diagram' | 'json')}
        options={[{ label: '预览', value: 'diagram' }, { label: 'JSON', value: 'json' }]} />
      <div
        id="api-config-result-panel"
        className="api-config-result-panel"
        role="region"
        aria-label="中间配置内容"
      >
        {activeView === 'diagram' ? (
          canRenderDiagram ? (
            <ApiConfigDiagramView content={content} />
          ) : (
            <div className="ai-task-run-result-popover-empty">当前中间配置无法解析为 API 链路</div>
          )
        ) : (
          <TextCodeEditor
            ariaLabel="中间配置 JSON"
            value={content}
            readOnly
            language="json"
            height="100%"
            minHeight={0}
          />
        )}
      </div>
    </div>
  )
}

/** 候选 API 用例的只读预览，默认收起每条用例的细节。 */
export function ApiCandidateResultView({ content }: { content: string }) {
  if (!normalizeApiConfigCases(content)) {
    return <div className="ai-task-run-result-popover-empty">当前候选结果无法解析为 API 用例</div>
  }

  return <ApiConfigDiagramView content={content} defaultCollapsed />
}
