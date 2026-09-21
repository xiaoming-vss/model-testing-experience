import '@/features/ai-testing/styles/functional-import-confirm.css'
import '@/features/ai-testing/styles/index.css'
import type { GeneratedTestCase } from '@/features/ai-testing/utils/functionalOutput'
import { CASE_ID_FIELDS, formatCaseIdTag, isJsonText, parseGeneratedCases, toDisplayText } from '@/features/ai-testing/utils/functionalOutput'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { CheckCircleFilled, FileTextOutlined, LeftOutlined, PlayCircleOutlined, RightOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Empty, Input, Tag } from 'antd'
import { useEffect, useMemo, useState } from 'react'

function getGeneratedCaseReviewCategory(testCase: GeneratedTestCase): string {
  for (const key of ['case_type', 'caseType', 'type']) {
    const value = testCase.tagFields.find((field) => field.key === key)?.value.trim()
    if (value) return value
  }
  return '未分类'
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

function isExpectedResultField(key: string) {
  return ['expected_results', 'expectedResult', 'expectedResults', 'expected_result'].includes(key)
}

export function GeneratedCasesReviewView({ content }: { content: string }) {
  const moduleGroups = useMemo(() => parseGeneratedCases(content), [content])
  const [query, setQuery] = useState('')
  const [activeFilter, setActiveFilter] = useState<string | null>(null)
  const [selectedModule, setSelectedModule] = useState('')
  const totalCases = useMemo(() => moduleGroups.reduce((sum, group) => sum + group.cases.length, 0), [moduleGroups])
  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>()
    moduleGroups.forEach((group) => group.cases.forEach((testCase) => {
      const category = getGeneratedCaseReviewCategory(testCase)
      counts.set(category, (counts.get(category) ?? 0) + 1)
    }))
    return counts
  }, [moduleGroups])
  const currentFilter = activeFilter !== null && categoryCounts.has(activeFilter) ? activeFilter : null
  const filters = [
    { key: null, label: '全部', count: totalCases },
    ...Array.from(categoryCounts, ([key, count]) => ({ key, label: key, count })),
  ]
  const visibleGroups = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return moduleGroups.map((group) => ({
      ...group,
      cases: group.cases.filter((testCase) => {
        const matchesFilter = currentFilter === null || getGeneratedCaseReviewCategory(testCase) === currentFilter
        const matchesQuery = !normalizedQuery || group.moduleName.toLowerCase().includes(normalizedQuery) || testCase.displayName.toLowerCase().includes(normalizedQuery)
        return matchesFilter && matchesQuery
      }),
    })).filter((group) => group.cases.length > 0)
  }, [currentFilter, moduleGroups, query])
  const visibleCaseCount = visibleGroups.reduce((sum, group) => sum + group.cases.length, 0)

  useEffect(() => {
    if (visibleGroups.length === 0) {
      setSelectedModule('')
      return
    }
    if (!visibleGroups.some((group) => group.moduleName === selectedModule)) {
      setSelectedModule(visibleGroups[0].moduleName)
    }
  }, [selectedModule, visibleGroups])

  if (moduleGroups.length === 0) {
    return isJsonText(content) ? (
      <JsonEditor value={content} readOnly foldable minHeight={520} />
    ) : (
      <pre className="ai-task-code-block">{content}</pre>
    )
  }

  const activeGroup = visibleGroups.find((group) => group.moduleName === selectedModule) ?? visibleGroups[0]
  const activeGroupIndex = activeGroup ? visibleGroups.indexOf(activeGroup) : -1
  const caseStartIndex = activeGroup
    ? visibleGroups.slice(0, activeGroupIndex).reduce((sum, group) => sum + group.cases.length, 0)
    : 0

  return (
    <div className="ai-generated-cases-review">
      <aside className="ai-generated-cases-review-sidebar">
        <div className="ai-generated-cases-review-sidebar-head">
          <strong>用例分组</strong>
          <Input
            allowClear
            prefix={<SearchOutlined aria-hidden />}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索模块或场景"
            aria-label="搜索模块或场景"
          />
          <div className="ai-generated-cases-review-filters" aria-label="用例类型筛选">
            {filters.map((filter) => {
              return (
                <button
                  key={filter.key === null ? 'all' : `type:${filter.key}`}
                  type="button"
                  className={currentFilter === filter.key ? 'active' : ''}
                  aria-pressed={currentFilter === filter.key}
                  onClick={() => setActiveFilter(filter.key)}
                >
                  {filter.label} <span>{filter.count}</span>
                </button>
              )
            })}
          </div>
        </div>
        <div className="ai-generated-cases-review-groups">
          {visibleGroups.length > 0 ? visibleGroups.map((group) => (
            <button
              key={group.moduleName}
              type="button"
              className={group.moduleName === activeGroup?.moduleName ? 'active' : ''}
              aria-current={group.moduleName === activeGroup?.moduleName ? 'true' : undefined}
              onClick={() => setSelectedModule(group.moduleName)}
            >
              <span className="ai-generated-cases-review-group-name"><RightOutlined aria-hidden />{group.moduleName}</span>
              <span className="ai-generated-cases-review-count">{group.cases.length}</span>
            </button>
          )) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的用例分组" />}
        </div>
      </aside>

      <section className="ai-generated-cases-review-detail">
        {activeGroup ? (
          <>
            <header className="ai-generated-cases-review-detail-head">
              <div>
                <strong>{activeGroup.moduleName}</strong>
                <span>第 {caseStartIndex + 1}–{caseStartIndex + activeGroup.cases.length} 条，共 {visibleCaseCount} 条</span>
              </div>
              <div className="ai-generated-cases-review-pager">
                <Button
                  aria-label="上一个用例分组"
                  icon={<LeftOutlined />}
                  disabled={activeGroupIndex <= 0}
                  onClick={() => setSelectedModule(visibleGroups[activeGroupIndex - 1].moduleName)}
                />
                <Button
                  aria-label="下一个用例分组"
                  icon={<RightOutlined />}
                  disabled={activeGroupIndex >= visibleGroups.length - 1}
                  onClick={() => setSelectedModule(visibleGroups[activeGroupIndex + 1].moduleName)}
                />
              </div>
            </header>
            <div className="ai-generated-cases-review-card-list">
              {activeGroup.cases.map((testCase, caseIndex) => (
                <article key={`${activeGroup.moduleName}-${caseIndex}`} className="ai-generated-cases-review-card">
                  <header>
                    <span className="ai-generated-cases-review-index">{String(caseStartIndex + caseIndex + 1).padStart(2, '0')}</span>
                    {testCase.tagFields.map((tag) => {
                      const isCaseId = CASE_ID_FIELDS.includes(tag.key)
                      return (
                        <Tag key={tag.key} color="orange" title={isCaseId ? tag.value : undefined}>
                          {isCaseId ? formatCaseIdTag(tag.value) : tag.value}
                        </Tag>
                      )
                    })}
                    <strong>{testCase.displayName}</strong>
                  </header>
                  <div className="ai-generated-cases-review-fields">
                    {testCase.detailFields.map((field) => {
                      const expected = isExpectedResultField(field.key)
                      const lines = getGeneratedCaseFieldLines(field.value)
                      return (
                        <section key={field.key} className={expected ? 'expected' : ''}>
                          <div className="ai-generated-cases-review-field-title">
                            {expected ? <CheckCircleFilled aria-hidden /> : field.label === '测试步骤' ? <PlayCircleOutlined aria-hidden /> : <FileTextOutlined aria-hidden />}
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
          </>
        ) : <Empty description="请选择用例分组" />}
      </section>
    </div>
  )
}
