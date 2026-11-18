import { CaseNameTreeView } from './CaseNamesResultView'
import { buildGeneratedCaseTree } from '../utils/generatedCaseTree'
import { CASE_ID_FIELDS, getGeneratedCaseEditableFields, isJsonText, toDisplayText } from '@/features/ai-testing/utils/functionalOutput'
import { JsonEditor } from '@/shared/components/JsonEditor/JsonEditor'
import { CheckCircleFilled, FileTextOutlined, PlayCircleOutlined, SnippetsOutlined } from '@ant-design/icons'
import { Empty, Input, Tag } from 'antd'
import type { GeneratedTestCase } from '../utils/functionalOutput'
import { useCallback, useMemo, useState } from 'react'

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
  /** 删除测试点只在候选草稿工作台开启；版本阅读弹窗只读展示。 */
  allowDelete?: boolean
  rootTitle?: string
  selectedCaseKey?: string
  onCaseSelect?: (key: string, raw: Record<string, unknown>) => void
}

export function GeneratedCasesReviewView({ content, rootTitle = '功能测试用例', allowDelete = false, selectedCaseKey, onCaseSelect, onChange }: GeneratedCasesReviewViewProps) {
  const [localKey, setLocalKey] = useState('')
  const [selectionTick, setSelectionTick] = useState(0)
  const model = useMemo(() => buildGeneratedCaseTree(content, rootTitle), [content, rootTitle])
  const active = model.visible.find((entry) => entry.key === (selectedCaseKey || localKey)) ?? model.visible[0]
  const activeIndex = model.visible.findIndex((entry) => entry.key === active?.key)
  const testCase = active?.testCase
  const select = useCallback((key: string) => {
    const entry = model.entries.find((item) => item.key === key)
    if (!entry) return
    setSelectionTick((tick) => tick + 1)
    setLocalKey(key)
    onCaseSelect?.(key, entry.testCase.raw)
  }, [model.entries, onCaseSelect])
  const removeCase = useCallback((key: string) => {
    if (!onChange) return
    const entry = model.entries.find((item) => item.key === key)
    if (!entry) return
    const deletedIndex = entry.testCase.sourceIndex
    const parsed: unknown = JSON.parse(content)
    const cases = Array.isArray(parsed) ? parsed : (parsed as { cases?: unknown[] } | null)?.cases
    if (!Array.isArray(cases)) return
    const nextCases = cases.filter((_, index) => index !== entry.testCase.sourceIndex)
    const next = Array.isArray(parsed) ? nextCases : { ...(parsed as Record<string, unknown>), cases: nextCases }
    // 删除后用例位置会前移，选中项也可能换 key；按删除前的源位置重算，避免回落到第一条。
    const remap = (item: (typeof model.entries)[number]) => {
      const index = item.testCase.sourceIndex > deletedIndex ? item.testCase.sourceIndex - 1 : item.testCase.sourceIndex
      return `${item.testCase.moduleName}:${index}`
    }
    const current = model.entries.find((item) => item.key === (selectedCaseKey || localKey) && item.key !== key)
    if (current) {
      if (current.testCase.sourceIndex > deletedIndex) {
        const nextKey = remap(current)
        setLocalKey(nextKey)
        onCaseSelect?.(nextKey, current.testCase.raw)
      }
    } else {
      const visibleIndex = Math.max(0, model.visible.findIndex((item) => item.key === key))
      const nextVisible = model.visible.filter((item) => item.key !== key)
      const nextActive = nextVisible[Math.min(visibleIndex, nextVisible.length - 1)]
      if (nextActive) {
        const nextKey = remap(nextActive)
        setLocalKey(nextKey)
        onCaseSelect?.(nextKey, nextActive.testCase.raw)
      }
    }
    onChange(JSON.stringify(next, null, 2))
  }, [content, localKey, model.entries, model.visible, onCaseSelect, onChange, selectedCaseKey])
  if (!model.entries.length) return isJsonText(content)
    ? <JsonEditor value={content} readOnly foldable minHeight={0} />
    : <pre className="ai-task-code-block">{content}</pre>
  return <div className="ai-generated-case-browser grid h-full min-h-0 grid-cols-[minmax(0,3fr)_minmax(320px,2fr)] text-[var(--ai-text)] max-[900.01px]:grid-cols-1 max-[900.01px]:grid-rows-[minmax(220px,1fr)_minmax(220px,1fr)]">
    <section className="ai-generated-case-map flex min-h-0 min-w-0 flex-col gap-3 p-3" aria-label="用例树图">
      {model.visible.length ? <CaseNameTreeView content={content} rootTitle={rootTitle} treeData={model.tree} selectedNodeId={active?.key} selectionTick={selectionTick} onNodeSelect={select} onDeleteNode={onChange && allowDelete ? removeCase : undefined} />
        : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的用例" />}
    </section>
    <aside className="ai-generated-case-reading flex min-h-0 min-w-0 flex-col border-l border-[var(--ai-border,var(--app-frame-divider))] max-[900.01px]:border-l-0 max-[900.01px]:border-t" aria-label="选中用例详情">
      {testCase ? <>
        <div className="ai-generated-case-reading-scroll min-h-0 flex-1 overflow-auto px-6 py-5 max-[900.01px]:p-4">
          <p className="ai-generated-case-breadcrumb m-0 mb-5 text-[12px] text-[var(--ai-text-secondary)]">{testCase.moduleName} / {active.caseType}</p>
          {onChange ? <GeneratedCaseEditor key={testCase.sourceIndex} testCase={testCase} onChange={(patch) => {
            const parsed = JSON.parse(content)
            const cases = Array.isArray(parsed) ? parsed : parsed.cases
            cases[testCase.sourceIndex] = { ...cases[testCase.sourceIndex], ...patch }
            onChange(JSON.stringify(parsed, null, 2))
          }} /> : <article>
                <header>
                  <div className="ai-generated-case-meta mb-3.5 flex flex-wrap items-center gap-2 [&_.ant-tag]:m-0 [&_.ant-tag]:px-2 [&_.ant-tag]:text-[12px] [&_.ant-tag]:leading-6">
                  <span className="ai-generated-cases-review-index inline-flex h-7 w-8 flex-[0_0_32px] items-center justify-center rounded-[7px] bg-[var(--ai-accent-soft)] px-2.5 py-0.5 text-[13px] font-extrabold leading-6 text-[var(--ai-blue)]">{String(activeIndex + 1).padStart(2, '0')}</span>
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
                        {kind === 'priority' && /^\d+$/.test(tag.value) ? `P${tag.value}` : tag.value}
                      </Tag>
                    )
                  })}
                  </div>
                  <strong className="mt-3 block text-[18px] leading-[1.6]">{testCase.displayName}</strong>
                </header>
                <div className="ai-generated-cases-review-fields block">
                  {testCase.detailFields.filter((field) => !['test_model', 'testModel'].includes(field.key)).map((field) => {
                    const expected = isExpectedResultField(field.key)
                    const steps = isStepField(field.key)
                    const sectionClass = expected ? 'expected tone-green' : steps ? 'steps tone-indigo' : isPreconditionField(field.key) ? 'precondition' : ''
                    const iconClass = expected || steps ? '[&_.anticon]:text-[var(--srf-tone-text,var(--ai-blue))]' : '[&_.anticon]:text-[var(--ai-blue)]'
                    const lines = getGeneratedCaseFieldLines(field.value)
                    return (
                      <section key={field.key} className={`${sectionClass} mt-5 border-0 border-t border-[var(--ai-border,var(--app-frame-divider))] py-5`}>
                        <div className={`ai-generated-cases-review-field-title mb-[7px] flex items-center gap-[7px] border-b border-[var(--ai-border)] pb-1.5 text-[12px] leading-[18px] text-[var(--ai-text)] ${iconClass}`}>
                          {expected ? <CheckCircleFilled aria-hidden /> : steps ? <PlayCircleOutlined aria-hidden /> : isPreconditionField(field.key) ? <SnippetsOutlined aria-hidden /> : <FileTextOutlined aria-hidden />}
                          <strong>{field.label}</strong>
                        </div>
                        {lines.length > 1 ? (
                          <ol className="m-0 flex list-none flex-col gap-[3px] py-0 pl-[22px] pr-0 text-[13px] leading-[1.8] text-[var(--ai-text-secondary)] [counter-reset:ai-case-field] [overflow-wrap:anywhere]">{lines.map((line, lineIndex) => <li className="flex items-baseline gap-[5px] [counter-increment:ai-case-field]" key={`${field.key}-${lineIndex}`}>{line}</li>)}</ol>
                        ) : <p className="m-0 whitespace-pre-wrap break-words text-[13px] leading-[1.8] text-[var(--ai-text-secondary)]">{lines[0] || '-'}</p>}
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
  return <div className="ai-generated-case-editor mt-4 flex flex-col gap-4">
    {testCase.tagFields.some(({ key }) => CASE_ID_FIELDS.includes(key)) && <div className="ai-generated-case-meta mb-3.5 flex flex-wrap items-center gap-2 [&_.ant-tag]:m-0 [&_.ant-tag]:px-2 [&_.ant-tag]:text-[12px] [&_.ant-tag]:leading-6">
      {testCase.tagFields.filter(({ key }) => CASE_ID_FIELDS.includes(key)).map(({ key, value }) => <Tag key={key}>{value}</Tag>)}
    </div>}
    {fields.map(({ key, label }) => {
      const value = testCase.raw[key]
      const array = Array.isArray(value)
      return <label key={key} className="flex flex-col gap-2"><span>{label}</span><Input.TextArea aria-label={label} autoSize={{ minRows: 2, maxRows: 12 }}
        value={array ? value.join('\n') : String(value ?? '')}
        onChange={(event) => onChange({ [key]: array ? event.target.value.split('\n') : event.target.value })} /></label>
    })}
  </div>
}
