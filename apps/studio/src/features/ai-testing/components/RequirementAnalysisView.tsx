import { toRecordArray, toRecord } from '@/shared/utils/value'
import '@/features/ai-testing/styles/functional-import-confirm.css'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/requirement-analysis.css'
import '@/features/ai-testing/styles/run-result.css'
import type { RequirementAnalysisSection } from '@/features/ai-testing/utils/functionalOutput'
import { formatRoleConcerns, formatTextList, isJsonText, parseRequirementAnalysisContent, toDisplayText } from '@/features/ai-testing/utils/functionalOutput'
import { AnalysisContentBrowser } from './AnalysisContentBrowser'
import { AnalysisFactorBrowser } from './AnalysisFactorBrowser'
import { AnalysisScenarioDetails } from './AnalysisScenarioDetails'
import { AnalysisRuleDetails } from './AnalysisRuleDetails'
import { AnalysisOverview } from './AnalysisOverview'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { DownOutlined, RightOutlined } from '@ant-design/icons'
import { Empty, Tabs, Tag, type TabsProps } from 'antd'
import { useMemo, useState, type ReactNode } from 'react'
import { ArtifactViewTabs } from './ArtifactViewTabs'

export type RequirementAnalysisViewMode = 'json' | 'diagram'

function RequirementAnalysisCollapsibleSection({
  title,
  count,
  color,
  children,
}: {
  title: string
  count: number
  color: string
  children: ReactNode
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <section className="ai-requirement-analysis-section">
      <button
        type="button"
        className="ai-requirement-analysis-section-head"
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        <span className="ai-requirement-analysis-section-title">
          {expanded ? <DownOutlined aria-hidden /> : <RightOutlined aria-hidden />}
          <span>{title}</span>
        </span>
        <Tag color={color}>{count}</Tag>
      </button>
      {expanded ? children : null}
    </section>
  )
}

const analysisDetailLabels: Record<string, string> = {
  purpose: '功能目的', actors: '参与角色', applicableObjects: '适用对象',
  explicitExclusions: '明确排除范围', category: '规则分类', trigger: '触发操作',
  preconditions: '前置条件', applicableObject: '适用对象', expectedBehavior: '预期行为',
  prohibitedOrSkippedBehavior: '禁止或跳过的行为', observableOutcome: '可观察结果',
  confirmationStatus: '确认状态', sourceReferences: '来源依据', relatedRuleIds: '关联规则',
  relatedQuestionIds: '关联待确认项', confirmedValues: '已确认取值', defaultValue: '默认值',
  clarificationNeeded: '待澄清内容', conditions: '场景条件', derivationType: '推导类型',
  verificationObjective: '验证目标', blockingReason: '阻塞原因',
  question: '待确认问题', blockedWork: '阻塞工作', affectedScope: '影响范围',
  path: '入口路径', action: '操作',
}

function AnalysisDetails({ item, fields }: { item: Record<string, unknown>; fields: string[] }) {
  return fields.map((field) => (
    <div className={`ai-requirement-analysis-field${field === 'expectedBehavior' || field === 'verificationObjective' ? ' ai-analysis-focus-field' : ''}`} key={field}>
      <span>{analysisDetailLabels[field]}</span>
      <p>{formatTextList(item[field]) || (Array.isArray(item[field]) ? '无' : '未明确')}</p>
    </div>
  ))
}

function StructuredAnalysisSections({ parsed }: { parsed: RequirementAnalysisSection }) {
  const [activeCategory, setActiveCategory] = useState<string>()
  const overview = toRecord(parsed.functionalOverview)
  const sections = [
    {
      title: '业务规则', color: 'blue', items: toRecordArray(parsed.businessRules), id: 'ruleId',
      fields: ['category', 'applicableObject', 'preconditions', 'trigger', 'expectedBehavior', 'prohibitedOrSkippedBehavior', 'observableOutcome', 'confirmationStatus', 'sourceReferences', 'relatedQuestionIds']
    },
    {
      title: '场景因素', color: 'cyan', items: toRecordArray(parsed.scenarioFactors), id: 'factorId',
      fields: ['confirmedValues', 'defaultValue', 'clarificationNeeded']
    },
    {
      title: '场景拆解', color: 'purple', items: toRecordArray(parsed.scenarioBreakdown), id: 'scenarioId',
      fields: ['conditions', 'trigger', 'verificationObjective', 'derivationType', 'relatedRuleIds', 'relatedQuestionIds', 'blockingReason']
    },
    {
      title: '待确认项', color: 'orange', items: toRecordArray(parsed.openQuestions), id: 'questionId',
      fields: ['question', 'affectedScope', 'blockedWork']
    },
  ]
  const items: TabsProps['items'] = []
  if (overview) {
    items.push({
      key: 'overview',
      label: <span className="ai-requirement-analysis-category-label">功能概览<Tag color="geekblue">1</Tag></span>,
      children: <AnalysisOverview overview={overview} />,
    })
  }
  for (const { title, color, items: entries, id, fields } of sections) {
    if (!entries.length) continue
    items.push({
      key: id,
      label: <span className="ai-requirement-analysis-category-label">{title}<Tag color={color}>{entries.length}</Tag></span>,
      children: id === 'factorId' ? <AnalysisFactorBrowser entries={entries} /> : (
        <AnalysisContentBrowser title={title} compact={id === 'ruleId' || id === 'scenarioId'} filterStatus={id === 'scenarioId'} entries={entries.map((item, index) => ({
          key: `${toDisplayText(item[id])}-${index}`,
          code: toDisplayText(item[id]) || `${index + 1}`,
          directoryTitle: id === 'scenarioId' ? formatTextList(item.verificationObjective) || undefined : undefined,
          title: toDisplayText(item.name) || (id === 'scenarioId' ? `场景 ${index + 1}` : id === 'questionId' ? toDisplayText(item.question) || title : title),
          searchText: Object.values(item).map(formatTextList).join(' '),
          status: item.readyForTestPointGeneration === true ? 'ready' : item.readyForTestPointGeneration === false ? 'blocked' : 'unknown',
          badge: id === 'ruleId' ? <Tag>{formatTextList(item.confirmationStatus) || '确认状态未明确'}</Tag> : id === 'scenarioId' ? <Tag color={item.readyForTestPointGeneration === true ? 'green' : 'orange'}>
            {item.readyForTestPointGeneration === true ? '可生成测试点' : item.readyForTestPointGeneration === false ? '暂不可生成测试点' : '生成就绪状态未明确'}
          </Tag> : undefined,
          content: id === 'ruleId' ? <AnalysisRuleDetails item={item} /> : id === 'scenarioId' ? <AnalysisScenarioDetails item={item} /> : <AnalysisDetails item={item} fields={fields} />,
        }))} />
      ),
    })
  }
  return items.length ? (
    <Tabs className="ai-requirement-analysis-tabs ai-requirement-analysis-category-tabs" size="small" items={items}
      activeKey={items.some((item) => item.key === activeCategory) ? activeCategory : items[0].key}
      onChange={setActiveCategory} />
  ) : null
}

export function RequirementAnalysisDiagramView({ content }: { content: string }) {
  const parsed = useMemo(() => parseRequirementAnalysisContent(content), [content])

  if (!parsed) {
    return isJsonText(content) ? (
      <JsonEditor value={content} readOnly foldable minHeight={640} />
    ) : (
      <pre className="ai-task-code-block">{content}</pre>
    )
  }

  const coreFunctions = toRecordArray(parsed.Platform_core_functions)
  const targetUnderstanding = toRecord(parsed.Target_understanding)
  const legacyTargets = toRecordArray(parsed.Target_understanding)
  const targetSections = targetUnderstanding
    ? [
      { key: 'business_goal', title: '业务目标', content: formatTextList(targetUnderstanding.business_goal) },
      { key: 'test_goal', title: '测试目标', content: formatTextList(targetUnderstanding.test_goal) },
      { key: 'user_roles_and_concerns', title: '用户角色与关注点', content: formatRoleConcerns(targetUnderstanding.user_roles_and_concerns) },
      { key: 'quality_attributes', title: '质量属性', content: formatTextList(targetUnderstanding.quality_attributes) },
    ].filter((item) => item.content)
    : []
  const risks = toRecordArray(parsed.Risk_point_prediction)
  const flows = toRecordArray(parsed.function_flow)
  const scenes = toRecordArray(parsed.Scene_Design)

  const hasStructuredContent = toRecord(parsed.functionalOverview) ||
    [parsed.businessRules, parsed.scenarioFactors, parsed.scenarioBreakdown, parsed.openQuestions]
      .some((value) => toRecordArray(value).length > 0)
  if (!hasStructuredContent && !coreFunctions.length && !targetSections.length && !legacyTargets.length && !risks.length && !flows.length && !scenes.length) {
    return <Empty description="暂无可展示的测试需求分析内容，请在 json 页签查看原始数据" />
  }

  return (
    <div className="ai-requirement-analysis-view">
      <StructuredAnalysisSections parsed={parsed} />
      {coreFunctions.length > 0 ? (
        <RequirementAnalysisCollapsibleSection title="平台核心功能" count={coreFunctions.length} color="blue">
          <div className="ai-requirement-analysis-grid two-col">
            {coreFunctions.map((item, index) => (
              <article key={`core-${index}`} className="ai-requirement-analysis-card">
                <div className="ai-requirement-analysis-card-title">{toDisplayText(item.function_name ?? item.function) || `功能 ${index + 1}`}</div>
                <div className="ai-requirement-analysis-field">
                  <span>能力说明</span>
                  <p>{toDisplayText(item.function_description ?? item.description) || '-'}</p>
                </div>
                <div className="ai-requirement-analysis-field accent">
                  <span>业务价值</span>
                  <p>{toDisplayText(item.business_value) || '-'}</p>
                </div>
              </article>
            ))}
          </div>
        </RequirementAnalysisCollapsibleSection>
      ) : null}

      {targetSections.length > 0 || legacyTargets.length > 0 ? (
        <RequirementAnalysisCollapsibleSection title="目标理解" count={targetSections.length || legacyTargets.length} color="cyan">
          <div className="ai-requirement-analysis-list">
            {targetSections.length > 0 ? targetSections.map((item, index) => (
              <article key={`target-${item.key}`} className="ai-requirement-analysis-row-card">
                <div className="ai-requirement-analysis-row-index">{index + 1}</div>
                <div className="ai-requirement-analysis-row-body">
                  <div className="ai-requirement-analysis-card-title">{item.title}</div>
                  <p>{item.content}</p>
                </div>
              </article>
            )) : legacyTargets.map((item, index) => (
              <article key={`target-${index}`} className="ai-requirement-analysis-row-card">
                <div className="ai-requirement-analysis-row-index">{index + 1}</div>
                <div className="ai-requirement-analysis-row-body">
                  <div className="ai-requirement-analysis-card-title">{toDisplayText(item.target) || `目标 ${index + 1}`}</div>
                  <p>{toDisplayText(item.description) || '-'}</p>
                </div>
              </article>
            ))}
          </div>
        </RequirementAnalysisCollapsibleSection>
      ) : null}

      {risks.length > 0 ? (
        <RequirementAnalysisCollapsibleSection title="风险点预测" count={risks.length} color="volcano">
          <div className="ai-requirement-analysis-grid two-col">
            {risks.map((item, index) => (
              <article key={`risk-${index}`} className="ai-requirement-analysis-card risk">
                <div className="ai-requirement-analysis-card-title">{toDisplayText(item.risk_category ?? item.risk_area) || `风险 ${index + 1}`}</div>
                <div className="ai-requirement-analysis-field">
                  <span>风险说明</span>
                  <p>{formatTextList(item.risk_points ?? item.risk_description) || '-'}</p>
                </div>
                <div className="ai-requirement-analysis-field accent danger">
                  <span>影响链路</span>
                  <p>{formatTextList(item.affected_links ?? item.impact) || '-'}</p>
                </div>
              </article>
            ))}
          </div>
        </RequirementAnalysisCollapsibleSection>
      ) : null}

      {flows.length > 0 ? (
        <RequirementAnalysisCollapsibleSection title="功能流程" count={flows.length} color="geekblue">
          <div className="ai-requirement-analysis-flow-list">
            {flows.map((item, index) => (
              <article key={`flow-${index}`} className="ai-requirement-analysis-flow-card">
                <div className="ai-requirement-analysis-flow-step">0{index + 1}</div>
                <div className="ai-requirement-analysis-flow-body">
                  <div className="ai-requirement-analysis-card-title">{toDisplayText(item.flow_name) || `流程 ${index + 1}`}</div>
                  <div className="ai-requirement-analysis-field">
                    <span>流程和依赖链</span>
                    <p>{toDisplayText(item.description) || '-'}</p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </RequirementAnalysisCollapsibleSection>
      ) : null}

      {scenes.length > 0 ? (
        <RequirementAnalysisCollapsibleSection title="场景设计" count={scenes.length} color="purple">
          <div className="ai-requirement-analysis-scene-groups">
            {scenes.map((scene, index) => {
              const subCategories = toRecordArray(scene.subcategories ?? scene.sub_category)
              return (
                <article key={`scene-${index}`} className="ai-requirement-analysis-scene-group">
                  <div className="ai-requirement-analysis-scene-head">
                    <div className="ai-requirement-analysis-card-title">{toDisplayText(scene.scene_type) || `场景 ${index + 1}`}</div>
                    <Tag color="default">{subCategories.length} 项</Tag>
                  </div>
                  <div className="ai-requirement-analysis-grid two-col">
                    {subCategories.map((item, subIndex) => (
                      <article key={`scene-${index}-sub-${subIndex}`} className="ai-requirement-analysis-card nested">
                        <div className="ai-requirement-analysis-card-title">{toDisplayText(item.name ?? item.scene_type) || `子场景 ${subIndex + 1}`}</div>
                        <div className="ai-requirement-analysis-field">
                          <span>场景说明</span>
                          <p>{toDisplayText(item.description) || '-'}</p>
                        </div>
                      </article>
                    ))}
                  </div>
                </article>
              )
            })}
          </div>
        </RequirementAnalysisCollapsibleSection>
      ) : null}
    </div>
  )
}

export function RequirementAnalysisView({ content }: { content: string }) {
  const [activeView, setActiveView] = useState<RequirementAnalysisViewMode>('diagram')
  const parsed = useMemo(() => parseRequirementAnalysisContent(content), [content])
  const isDiagramAvailable = Boolean(parsed)

  return (
    <ArtifactViewTabs jsonCopyText={content}
      className="ai-requirement-analysis-tabs"
      size="small"
      activeKey={activeView}
      onChange={(key) => setActiveView(key as RequirementAnalysisViewMode)}
      items={[
        {
          key: 'diagram',
          label: '可视化',
          children: isDiagramAvailable ? (
            <RequirementAnalysisDiagramView content={content} />
          ) : (
            <div className="ai-task-run-result-popover-empty">当前内容无法解析为结构化测试需求分析</div>
          ),
        },
        {
          key: 'json',
          label: 'json',
          children: isJsonText(content) ? (
            <JsonEditor value={content} showCopy={false} readOnly foldable minHeight={640} />
          ) : (
            <pre className="ai-task-code-block">{content}</pre>
          ),
        },
      ]}
    />
  )
}
