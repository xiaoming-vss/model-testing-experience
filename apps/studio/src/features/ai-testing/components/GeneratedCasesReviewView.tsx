import '@/features/ai-testing/styles/functional-import-confirm.css'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/generated-cases-review.css'
import { CASE_ID_FIELDS, formatCaseIdTag, isJsonText, parseGeneratedCases, toDisplayText } from '@/features/ai-testing/utils/functionalOutput'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { CheckCircleFilled, FileTextOutlined, PlayCircleOutlined, SearchOutlined, SnippetsOutlined } from '@ant-design/icons'
import { Empty, Input, Tag } from 'antd'
import { useEffect, useMemo, useState } from 'react'

function getGeneratedCaseTagKind(key: string): 'id' | 'type' | 'priority' | 'default' {
  if (CASE_ID_FIELDS.includes(key)) return 'id'
  if (['case_type', 'caseType', 'type'].includes(key)) return 'type'
  if (key === 'priority') return 'priority'
  return 'default'
}

function getPriorityTagColor(value: string): string | undefined {
  const normalized = value.trim().toUpperCase()
  if (['P0', 'P1', '0', '1', '高', 'HIGH', 'CRITICAL'].includes(normalized)) return 'red'
  if (['P2', '2', '中', 'MEDIUM'].includes(normalized)) return 'blue'
  return undefined
}

function getGeneratedCaseFieldLines(value: string): string[] {
  try {
    const parsed = JSON.parse(value)
    if (Array.isArray(parsed)) return parsed.map(toDisplayText).filter(Boolean)
  } catch {
    // 普通文本按换行展示，避免在预览中暴露 JSON 字符串形式。
  }
  return value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
}

function isPreconditionField(key: string) {
  return ['precondition', 'preconditions', 'preCondition'].includes(key)
}

function isStepField(key: string) {
  return ['steps', 'test_steps', 'testSteps', 'operation'].includes(key)
}

function isExpectedResultField(key: string) {
  return ['expected_results', 'expectedResult', 'expectedResults', 'expected_result'].includes(key)
}

type GeneratedCasesReviewViewProps = {
  content: string
  selectedCaseKey?: string
  onCaseSelect?: (key: string, raw: Record<string, unknown>) => void
}

export function GeneratedCasesReviewView({ content, selectedCaseKey, onCaseSelect }: GeneratedCasesReviewViewProps) {
  const moduleGroups = useMemo(() => parseGeneratedCases(content), [content])
  const [query, setQuery] = useState('')
  const [selectedModule, setSelectedModule] = useState('')
  const visibleGroups = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return moduleGroups.map((group) => ({
      ...group,
      cases: group.cases.filter((testCase) => {
        const matchesQuery = !normalizedQuery || group.moduleName.toLowerCase().includes(normalizedQuery) || testCase.displayName.toLowerCase().includes(normalizedQuery)
        return matchesQuery
      }),
    })).filter((group) => group.cases.length > 0)
  }, [moduleGroups, query])

  useEffect(() => {
    // 未选中模块时展示全部用例；仅当所选模块被搜索过滤掉时才回退到全量。
    if (selectedModule && !visibleGroups.some((group) => group.moduleName === selectedModule)) {
      setSelectedModule('')
    }
  }, [selectedModule, visibleGroups])

  if (moduleGroups.length === 0) {
    return isJsonText(content) ? (
      <JsonEditor value={content} readOnly foldable minHeight={520} />
    ) : (
      <pre className="ai-task-code-block">{content}</pre>
    )
  }

  const activeGroups = selectedModule
    ? visibleGroups.filter((group) => group.moduleName === selectedModule)
    : visibleGroups
  const groupStartIndexes = new Map<string, number>()
  let runningCaseCount = 0
  for (const group of visibleGroups) {
    groupStartIndexes.set(group.moduleName, runningCaseCount)
    runningCaseCount += group.cases.length
  }

  return (
    <div className={`ai-generated-cases-review${moduleGroups.length === 1 ? ' is-single-group' : ''}`}>
      <aside className="ai-generated-cases-review-sidebar">
        <div className="ai-generated-cases-review-sidebar-head">
          <Input
            allowClear
            prefix={<SearchOutlined aria-hidden />}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索模块或场景"
            aria-label="搜索模块或场景"
          />
          {visibleGroups.length > 0 ? (
            <div className="ai-generated-cases-review-groups" aria-label="用例分组">
              {visibleGroups.map((group) => (
                <button
                  key={group.moduleName}
                  type="button"
                  className={group.moduleName === selectedModule ? 'active' : ''}
                  aria-current={group.moduleName === selectedModule ? 'true' : undefined}
                  onClick={() => setSelectedModule(group.moduleName === selectedModule ? '' : group.moduleName)}
                >
                  <span className="ai-generated-cases-review-group-name">{group.moduleName}</span>
                  <span className="ai-generated-cases-review-count">{group.cases.length}</span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </aside>

      <section className="ai-generated-cases-review-detail">
        {activeGroups.length > 0 ? activeGroups.map((group) => (
          <div key={group.moduleName} className="ai-generated-cases-review-card-list">
            {group.cases.map((testCase, caseIndex) => (
              <article
                key={`${group.moduleName}-${caseIndex}`}
                className={`ai-generated-cases-review-card${selectedCaseKey === `${group.moduleName}:${caseIndex}` ? ' is-selected' : ''}`}
                onClick={() => onCaseSelect?.(`${group.moduleName}:${caseIndex}`, testCase.raw)}
              >
                <header>
                  <span className="ai-generated-cases-review-index">{String((groupStartIndexes.get(group.moduleName) ?? 0) + caseIndex + 1).padStart(2, '0')}</span>
                  {testCase.tagFields.map((tag) => {
                    const kind = getGeneratedCaseTagKind(tag.key)
                    const isCaseId = kind === 'id'
                    const color = kind === 'type' ? 'gold' : kind === 'priority' ? getPriorityTagColor(tag.value) : undefined
                    return (
                      <Tag
                        key={tag.key}
                        color={color}
                        className={`ai-generated-cases-review-tag is-${kind}`}
                        title={isCaseId ? tag.value : undefined}
                      >
                        {isCaseId ? formatCaseIdTag(tag.value) : tag.value}
                      </Tag>
                    )
                  })}
                  <strong>{testCase.displayName}</strong>
                </header>
                <div className="ai-generated-cases-review-fields">
                  {testCase.detailFields.map((field) => {
                    const expected = isExpectedResultField(field.key)
                    const sectionClass = expected ? 'expected tone-green' : isStepField(field.key) ? 'steps tone-indigo' : isPreconditionField(field.key) ? 'precondition' : ''
                    const lines = getGeneratedCaseFieldLines(field.value)
                    return (
                      <section key={field.key} className={sectionClass}>
                        <div className="ai-generated-cases-review-field-title">
                          {expected ? <CheckCircleFilled aria-hidden /> : isStepField(field.key) ? <PlayCircleOutlined aria-hidden /> : isPreconditionField(field.key) ? <SnippetsOutlined aria-hidden /> : <FileTextOutlined aria-hidden />}
                          <strong>{field.label}</strong>
                        </div>
                        {lines.length > 1 ? (
                          <ol>{lines.map((line, lineIndex) => <li key={`${field.key}-${lineIndex}`}>{line}</li>)}</ol>
                        ) : <p>{lines[0] || '-'}</p>}
                      </section>
                    )
                  })}
                </div>
              </article>
            ))}
          </div>
        )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的用例分组" />}
      </section>
    </div>
  )
}
