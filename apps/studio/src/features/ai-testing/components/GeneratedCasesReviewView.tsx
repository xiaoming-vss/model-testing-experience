import '@/features/ai-testing/styles/functional-import-confirm.css'
import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/generated-cases-review.css'
import '../styles/generated-case-browser.css'
import { CaseNameTreeView } from './CaseNamesResultView'
import { buildGeneratedCaseTree } from '../utils/generatedCaseTree'
import { CASE_ID_FIELDS, formatCaseIdTag, getGeneratedCaseEditableFields, isJsonText, toDisplayText } from '@/features/ai-testing/utils/functionalOutput'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { CheckCircleFilled, FileTextOutlined, PlayCircleOutlined, SnippetsOutlined } from '@ant-design/icons'
import { Empty, Input, Tag } from 'antd'
import type { GeneratedTestCase } from '../utils/functionalOutput'
import { useMemo, useState } from 'react'

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
  onChange?: (content: string) => void
  pointsContent?: string
  rootTitle?: string
  selectedCaseKey?: string
  onCaseSelect?: (key: string, raw: Record<string, unknown>) => void
}

export function GeneratedCasesReviewView({ content, pointsContent = '', rootTitle = '功能测试用例', selectedCaseKey, onCaseSelect, onChange }: GeneratedCasesReviewViewProps) {
  const [localKey, setLocalKey] = useState('')
  const model = useMemo(() => buildGeneratedCaseTree(content, pointsContent, rootTitle), [content, pointsContent, rootTitle])
  const active = model.visible.find((entry) => entry.key === (selectedCaseKey || localKey)) ?? model.visible[0]
  const activeIndex = model.visible.findIndex((entry) => entry.key === active?.key)
  const testCase = active?.testCase
  const select = (key: string) => {
    const entry = model.entries.find((item) => item.key === key)
    if (!entry) return
    setLocalKey(key)
    onCaseSelect?.(key, entry.testCase.raw)
  }
  if (!model.entries.length) return isJsonText(content)
    ? <JsonEditor value={content} readOnly foldable minHeight={0} />
    : <pre className="ai-task-code-block">{content}</pre>
  return <div className="ai-generated-case-browser">
    <section className="ai-generated-case-map" aria-label="用例树图">
      {model.visible.length ? <CaseNameTreeView content={content} rootTitle={rootTitle} treeData={model.tree} selectedNodeId={active?.key} onNodeSelect={select} />
        : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的用例" />}
    </section>
    <aside className="ai-generated-case-reading" aria-label="选中用例详情">
      {testCase ? <>
        <div className="ai-generated-case-reading-scroll">
          <p className="ai-generated-case-breadcrumb">{testCase.moduleName} / {active.scene}</p>
          {onChange ? <GeneratedCaseEditor key={testCase.sourceIndex} testCase={testCase} onChange={(patch) => {
            const parsed = JSON.parse(content)
            const cases = Array.isArray(parsed) ? parsed : parsed.cases
            cases[testCase.sourceIndex] = { ...cases[testCase.sourceIndex], ...patch }
            onChange(JSON.stringify(parsed, null, 2))
          }} /> : <article>
                <header>
                  <div className="ai-generated-case-meta">
                  <span className="ai-generated-cases-review-index">{String(activeIndex + 1).padStart(2, '0')}</span>
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
                        {isCaseId ? formatCaseIdTag(tag.value) : kind === 'priority' && /^\d+$/.test(tag.value) ? `P${tag.value}` : tag.value}
                      </Tag>
                    )
                  })}
                  </div>
                  <strong>{testCase.displayName}</strong>
                </header>
                <div className="ai-generated-cases-review-fields">
                  {testCase.detailFields.filter((field) => !['test_model', 'testModel'].includes(field.key)).map((field) => {
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

          </article>}
        </div>

      </> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请选择用例" />}
    </aside>
  </div>
}

function GeneratedCaseEditor({ testCase, onChange }: { testCase: GeneratedTestCase; onChange: (patch: Record<string, unknown>) => void }) {
  const fields = getGeneratedCaseEditableFields(testCase)
  return <div className="ai-generated-case-editor">
    {testCase.tagFields.some(({ key }) => CASE_ID_FIELDS.includes(key)) && <div className="ai-generated-case-meta">
      {testCase.tagFields.filter(({ key }) => CASE_ID_FIELDS.includes(key)).map(({ key, value }) => <Tag key={key} title={value}>{formatCaseIdTag(value)}</Tag>)}
    </div>}
    <p>修改同步到当前草稿，点击底部“保存当前修改”后保存。</p>
    {fields.map(({ key, label }) => {
      const value = testCase.raw[key]
      const array = Array.isArray(value)
      return <label key={key}><span>{label}</span><Input.TextArea aria-label={label} autoSize={{ minRows: 2, maxRows: 12 }}
        value={array ? value.join('\n') : String(value ?? '')}
        onChange={(event) => onChange({ [key]: array ? event.target.value.split('\n') : event.target.value })} /></label>
    })}
  </div>
}
