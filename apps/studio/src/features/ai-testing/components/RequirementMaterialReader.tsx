import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Button, Input } from 'antd'
import {
  CheckCircleOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  LeftOutlined,
  PaperClipOutlined,
  RightOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { cx } from '@/shared/utils/cx'
import { MaterialBlockContent } from './RequirementMaterialBlockContent'
import styles from '../styles/requirement-material-reader.module.css'
import type {
  MaterialBlock,
  MaterialFeature,
  MaterialItem,
  MaterialQuestion,
  MaterialSection,
  RequirementMaterial,
} from './requirementMaterial.types'

type Tab = 'functions' | 'questions'
type SectionEntry = { section: MaterialSection; index: number }

const ROW_BETWEEN_CLASS = 'flex items-center justify-between gap-2'
const ROW_WRAP_CLASS = 'flex flex-wrap items-center gap-2'
const ROW_CLASS = 'flex items-center gap-2'
const SEMIBOLD_TEXT_CLASS = 'font-semibold text-[var(--srf-text)]'
const STATUS_DOT_CLASS = 'size-1.5 rounded-full'
const STACK_CLASS = 'flex flex-col gap-2'
const MUTED_META_CLASS = 'inline-flex items-center gap-1.5 text-[11px] text-[var(--srf-text-muted)]'

const STATUS_META: Record<string, { label: string; className: string; dot: string }> = {
  confirmed: {
    label: '明确',
    className: 'border-[var(--app-status-approved-border)] bg-[var(--app-status-approved-bg)] text-[var(--app-status-approved-text)]',
    dot: 'bg-[var(--app-status-approved-text)]',
  },
  unconfirmed: {
    label: '待确认',
    className: 'border-[var(--app-status-warning-border)] bg-[var(--app-status-warning-bg)] text-[var(--app-status-warning-text)]',
    dot: 'bg-[var(--app-status-warning-text)]',
  },
  conflicting: {
    label: '有冲突',
    className: 'border-[var(--app-danger-border)] bg-[var(--app-danger-surface-soft)] text-[var(--app-request-error-text)]',
    dot: 'bg-[var(--app-request-error-text)]',
  },
  example: {
    label: '示例',
    className: 'border-[var(--srf-accent-border)] bg-[var(--srf-accent-soft)] text-[var(--srf-accent)]',
    dot: 'bg-[var(--srf-accent)]',
  },
}

function CountBadge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'warn' | 'accent' }) {
  return <span className={cx(
    'inline-grid h-[18px] min-w-[18px] flex-none place-items-center rounded-full px-[5px] text-[9.5px] font-semibold tabular-nums',
    tone === 'warn' && 'bg-[var(--app-status-warning-bg)] text-[var(--app-status-warning-text)]',
    tone === 'accent' && 'bg-[var(--srf-accent-soft)] text-[var(--srf-accent)]',
    tone === 'neutral' && 'bg-[var(--srf-hover)] text-[var(--srf-text-muted)]',
  )}>{children}</span>
}

function StatusPill({ status }: { status: string }) {
  const meta = STATUS_META[status]
  if (!meta || status === 'confirmed') return null
  return <span className={cx('inline-flex flex-none items-center gap-1 rounded-full border px-1.5 py-px text-[10px] font-medium', meta.className)}>
    <i className={cx(STATUS_DOT_CLASS, meta.dot)} aria-hidden />
    {meta.label}
  </span>
}

function StatLine({ label, value, dot }: { label: string; value: number; dot: string }) {
  return <span className={MUTED_META_CLASS}>
    <i className={cx(STATUS_DOT_CLASS, dot)} aria-hidden />
    {label} <strong className="font-semibold tabular-nums text-[var(--srf-text)]">{value}</strong>
  </span>
}

function EvidenceSection({ blockIds, material, className }: { blockIds: string[]; material: RequirementMaterial; className?: string }) {
  return <section className={cx(STACK_CLASS, className)} aria-label="材料依据">
    <div className="flex items-center gap-2 text-[10.5px] font-semibold text-[var(--srf-text)]">
      <FileTextOutlined className="text-[var(--srf-text-muted)]" aria-hidden />
      材料依据
      <CountBadge>{blockIds.length}</CountBadge>
    </div>
    {blockIds.length
      ? <div className={STACK_CLASS}>
        {blockIds.map((id) => {
          const block = material.materialBlocks.find((item) => item.id === id)
          if (!block) return <p key={id} className="m-0 rounded-[6px] border border-dashed border-[var(--srf-card-border)] px-2.5 py-2 text-[10.5px] text-[var(--srf-text-muted)]">{id}：未找到对应材料</p>
          const source = material.sources.find((item) => item.id === block.sourceId)
          return <EvidenceBlockCard key={id} block={block} sourceName={source?.name || '来源未找到'} />
        })}
      </div>
      : <p className="m-0 text-[10.5px] text-[var(--srf-text-muted)]">暂无材料依据</p>}
  </section>
}

function EvidenceBlockCard({ block, sourceName }: { block: MaterialBlock; sourceName: string }) {
  return <article className="rounded-[6px] border border-[var(--srf-card-border)] border-l-2 border-l-[var(--srf-accent)] bg-[var(--srf-card)] px-2.5 py-2">
    <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--srf-text-muted)]">
      <strong className={SEMIBOLD_TEXT_CLASS}>{sourceName}</strong>
      <span>·</span>
      <span>{block.locator}</span>
    </div>
    <MaterialBlockContent block={block} />
  </article>
}

function computeCounts(items: MaterialItem[]) {
  const result = { confirmed: 0, unconfirmed: 0, conflicting: 0, example: 0 }
  items.forEach((item) => { if (item.status in result) result[item.status as keyof typeof result] += 1 })
  return result
}

function featureItems(feature: MaterialFeature) {
  return feature.sections.flatMap((section) => section.items)
}

function questionScope(question: MaterialQuestion, names: Map<string, string>) {
  return question.functionIds.length
    ? question.functionIds.map((id) => names.get(id) ?? id).join(' / ')
    : '整体'
}

function questionScopeCompact(question: MaterialQuestion, names: Map<string, string>) {
  if (!question.functionIds.length) return '整体'
  return question.functionIds.map((id) => names.get(id)?.match(/FR-\d+/i)?.[0] ?? id.replace(/^function-/, '')).join(' / ')
}

function itemCountByStatus(items: MaterialItem[]) {
  return computeCounts(items)
}

export function RequirementMaterialReader({ material, editable, onItemChange, onQuestionChange }: {
  material: RequirementMaterial
  editable: boolean
  onItemChange: (featureId: string, sectionIndex: number, itemIndex: number, text: string) => void
  onQuestionChange: (id: string, question: string) => void
}) {
  const [tab, setTab] = useState<Tab>('functions')
  const [activeFunctionId, setActiveFunctionId] = useState(material.functions[0]?.id ?? '')
  const [questionIndex, setQuestionIndex] = useState(0)
  const [activeSectionIndex, setActiveSectionIndex] = useState(0)
  const [expandedEvidence, setExpandedEvidence] = useState<string | null>(null)
  const [containerWidth, setContainerWidth] = useState(0)
  const [scrollResetKey, setScrollResetKey] = useState(0)
  const [scrollTarget, setScrollTarget] = useState<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)

  const activeFunction = material.functions.find((item) => item.id === activeFunctionId) ?? material.functions[0]
  const names = useMemo(() => new Map(material.functions.map((feature) => [feature.id, feature.name])), [material.functions])
  const visibleSections: SectionEntry[] = useMemo(() => (activeFunction?.sections ?? [])
    .map((section, index) => ({ section, index }))
    .filter((entry) => entry.section.items.length > 0), [activeFunction])
  const safeSectionIndex = Math.min(activeSectionIndex, Math.max(visibleSections.length - 1, 0))
  const activeSectionEntry = visibleSections[safeSectionIndex]
  const activeSection = activeSectionEntry?.section
  const activeQuestion = material.questions[Math.min(questionIndex, Math.max(material.questions.length - 1, 0))]
  const allItems = material.functions.flatMap(featureItems)
  const totals = computeCounts(allItems)
  const functionItemList = activeFunction ? featureItems(activeFunction) : []
  const functionCounts = computeCounts(functionItemList)
  const functionPending = functionItemList.filter((item) => item.status === 'unconfirmed').length
  const generalQuestions = material.questions.filter((question) => question.functionIds.length === 0).length

  useEffect(() => {
    if (!scrollResetKey) return
    const node = scrollRef.current
    if (!node) return
    if (typeof node.scrollTo === 'function') node.scrollTo({ top: 0 })
    else node.scrollTop = 0
  }, [scrollResetKey])

  useEffect(() => {
    if (scrollTarget === null) return
    const root = scrollRef.current
    const node = root?.querySelector<HTMLElement>(`[data-section-index="${scrollTarget}"]`)
    if (root && node) {
      const top = node.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop - 8
      if (typeof root.scrollTo === 'function') root.scrollTo({ top, behavior: 'smooth' })
      else root.scrollTop = top
    }
    setScrollTarget(null)
  }, [scrollTarget])

  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    setContainerWidth(root.clientWidth)
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      const width = Math.round(entries[0]?.contentRect.width ?? 0)
      if (width) setContainerWidth(width)
    })
    observer.observe(root)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (tab !== 'functions' || typeof IntersectionObserver === 'undefined') return
    const root = scrollRef.current
    if (!root) return
    const nodes = Array.from(root.querySelectorAll<HTMLElement>('[data-section-index]'))
    if (!nodes.length) return
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0]
      if (!visible) return
      const index = Number((visible.target as HTMLElement).dataset.sectionIndex)
      if (!Number.isNaN(index)) setActiveSectionIndex(index)
    }, { root, rootMargin: '-100px 0px -62% 0px', threshold: [0, 0.2, 0.6] })
    nodes.forEach((node) => observer.observe(node))
    return () => observer.disconnect()
  }, [tab, activeFunction?.id, visibleSections.length])

  const resetScroll = () => setScrollResetKey((key) => key + 1)

  const selectTab = (next: Tab) => {
    setTab(next)
    setExpandedEvidence(null)
    resetScroll()
  }

  const selectFunction = (id: string) => {
    setActiveFunctionId(id)
    setActiveSectionIndex(0)
    setExpandedEvidence(null)
    resetScroll()
  }

  const scrollToSection = (index: number) => {
    setActiveSectionIndex(index)
    setScrollTarget(index)
  }

  const stacked = containerWidth > 0 && containerWidth < 760
  const showOutline = containerWidth >= 1320
  const railWidth = stacked ? 'w-full' : containerWidth > 0 && containerWidth < 920 ? 'w-[220px]' : 'w-[252px]'

  const renderLeftRail = () => <aside
    className={cx(
      'flex flex-none flex-col border-r border-[var(--srf-card-border)] bg-[var(--srf-card)]',
      railWidth,
      stacked && 'max-h-[190px] border-b border-r-0',
    )}
    aria-label={tab === 'functions' ? '功能列表' : '待确认问题列表'}
  >
    <div className="flex flex-none flex-col gap-2 px-4 pt-4">
      <div>
        <p className="m-0 text-[10px] font-semibold tracking-[0.12em] text-[var(--srf-text-muted)]">材料整理</p>
        <h2 className="m-0 mt-1 text-[18px] font-[650] leading-6 text-[var(--srf-text)]">按功能阅读</h2>
      </div>
      <div className="inline-flex items-center gap-0.5 self-start rounded-full bg-[var(--srf-hover)] p-0.5" role="tablist" aria-label="材料整理">
        <button type="button" role="tab" aria-selected={tab === 'functions'}
          className={cx('inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[11px]', tab === 'functions' ? 'bg-[var(--srf-card)] font-medium text-[var(--srf-text)] shadow-[0_1px_2px_var(--srf-shadow-color)]' : 'bg-transparent text-[var(--srf-text-muted)] hover:text-[var(--srf-text)]')}
          onClick={() => selectTab('functions')}>
          功能说明 <CountBadge>{material.functions.length}</CountBadge>
        </button>
        <button type="button" role="tab" aria-selected={tab === 'questions'}
          className={cx('inline-flex h-7 items-center gap-1.5 rounded-full px-2.5 text-[11px]', tab === 'questions' ? 'bg-[var(--srf-card)] font-medium text-[var(--srf-text)] shadow-[0_1px_2px_var(--srf-shadow-color)]' : 'bg-transparent text-[var(--srf-text-muted)] hover:text-[var(--srf-text)]')}
          onClick={() => selectTab('questions')}>
          待确认 <CountBadge tone="warn">{material.questions.length}</CountBadge>
        </button>
      </div>
    </div>
    <div className="mt-3 min-h-0 flex-1 overflow-auto px-2 pb-2">
      {tab === 'functions' ? material.functions.map((feature) => {
        const items = featureItems(feature)
        const pending = items.filter((item) => item.status === 'unconfirmed').length
        const active = feature.id === activeFunction?.id
        return <button key={feature.id} type="button"
          className={cx(
            'flex w-full flex-col gap-1.5 rounded-[7px] border-l-2 p-2.5 text-left transition-colors [&+&]:mt-1',
            active ? 'border-l-[var(--srf-accent)] bg-[var(--srf-accent-soft)]' : 'border-l-transparent bg-transparent hover:bg-[var(--srf-hover)]',
          )}
          onClick={() => selectFunction(feature.id)}
        >
          <span className={ROW_CLASS}>
            <span className="font-mono text-[9.5px] text-[var(--srf-accent)]">{feature.id}</span>
            {pending ? <span className="ml-auto rounded-full bg-[var(--app-status-warning-bg)] px-1.5 py-px text-[9.5px] text-[var(--app-status-warning-text)]">{pending} 待确认</span> : null}
          </span>
          <span className="line-clamp-2 text-[12px] font-[550] leading-[1.55] text-[var(--srf-text)] [overflow-wrap:anywhere]">{feature.name || '未命名功能'}</span>
          <span className="text-[9.5px] text-[var(--srf-text-muted)]">{feature.sections.length} 章 · {items.length} 条</span>
        </button>
      }) : material.questions.map((question, index) => {
        const active = index === Math.min(questionIndex, material.questions.length - 1)
        return <button key={`${question.id}-${index}`} type="button"
          className={cx(
            'flex w-full flex-col gap-1.5 rounded-[7px] border-l-2 p-2.5 text-left transition-colors [&+&]:mt-1',
            active ? 'border-l-[var(--app-status-warning-text)] bg-[var(--app-status-warning-bg)]' : 'border-l-transparent bg-transparent hover:bg-[var(--srf-hover)]',
          )}
          onClick={() => { setQuestionIndex(index); setExpandedEvidence(null); resetScroll() }}
        >
          <span className={ROW_CLASS}>
            <span className="font-mono text-[9.5px] text-[var(--app-status-warning-text)]">{question.id || `Q${index + 1}`}</span>
            <span className="ml-auto rounded-full border border-[var(--srf-card-border)] px-1.5 py-px text-[9px] text-[var(--srf-text-muted)]">{questionScopeCompact(question, names)}</span>
          </span>
          <span className="line-clamp-3 text-[11.5px] leading-[1.6] text-[var(--srf-text)] [overflow-wrap:anywhere]">{question.question || '未记录问题'}</span>
        </button>
      })}
    </div>
    <footer className="flex flex-none items-center justify-between gap-2 border-t border-[var(--srf-card-border)] px-4 py-2.5 text-[9.5px] text-[var(--srf-text-muted)]">
      <span>{tab === 'functions' ? `共 ${material.functions.length} 个功能` : `共 ${material.questions.length} 个问题`}</span>
      <span>{tab === 'functions' ? `${allItems.length} 条说明` : `${generalQuestions} 个整体问题`}</span>
    </footer>
  </aside>

  const renderFunctionArticle = () => {
    if (!activeFunction) return <div className="m-8 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-8 text-center text-[12px] text-[var(--srf-text-muted)]">暂无功能说明</div>
    if (!activeSection) return <div className="m-8 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-8 text-center text-[12px] text-[var(--srf-text-muted)]">该功能暂无内容</div>
    return <article
      role="region"
      aria-label="功能说明详情"
      className="px-[56px] pb-8 pt-[52px] max-[900px]:px-8 max-[900px]:pb-9 max-[900px]:pt-9"
    >
      <header>
        <div className={ROW_WRAP_CLASS}>
          <span className="rounded-[4px] bg-[var(--srf-accent-soft)] px-1.5 py-0.5 text-[9.5px] font-semibold text-[var(--srf-accent)]">功能说明</span>
          <span className="font-mono text-[9.5px] text-[var(--srf-text-muted)]">{activeFunction.id}</span>
          {functionPending
            ? <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-[var(--app-status-warning-border)] bg-[var(--app-status-warning-bg)] px-2 py-0.5 text-[10px] text-[var(--app-status-warning-text)]"><WarningOutlined aria-hidden /> {functionPending} 个待确认</span>
            : <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-[var(--app-status-approved-text)]"><CheckCircleOutlined aria-hidden /> 全部明确</span>}
        </div>
        <h1 className="m-0 mt-3 text-[24px] font-[650] leading-[1.4] text-[var(--srf-text)] [overflow-wrap:anywhere] max-[900px]:text-[20px]">{activeFunction.name || '未命名功能'}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10.5px] text-[var(--srf-text-muted)]">
          <span>{activeFunction.sections.length} 个章节</span>
          <span>{functionItemList.length} 条说明</span>
          <span>{functionCounts.example} 条示例</span>
          <span className="ml-auto">来源：{material.sources.length} 份需求材料</span>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 border-y border-[var(--srf-divider)] py-3">
          <StatLine label="明确" value={functionCounts.confirmed} dot="bg-[var(--app-status-approved-text)]" />
          <StatLine label="待确认" value={functionCounts.unconfirmed} dot="bg-[var(--app-status-warning-text)]" />
          <StatLine label="有冲突" value={functionCounts.conflicting} dot="bg-[var(--app-request-error-text)]" />
          <StatLine label="示例" value={functionCounts.example} dot="bg-[var(--srf-accent)]" />
        </div>
      </header>

      {visibleSections.map(({ section, index: sectionIndex }, displayIndex) => {
        const counts = itemCountByStatus(section.items)
        return <section
          key={`${section.title}-${sectionIndex}`}
          data-section-index={displayIndex}
          className="mt-8 scroll-mt-5"
        >
          <div className="flex flex-wrap items-end gap-x-2 gap-y-1 border-b border-[var(--srf-card-border)] pb-2">
            <span className="font-mono text-[10px] tabular-nums text-[var(--srf-text-muted)]">{String(displayIndex + 1).padStart(2, '0')}</span>
            <h2 className="m-0 text-[16px] font-[650] text-[var(--srf-text)]">{section.title || '未命名章节'}</h2>
            <CountBadge>{section.items.length}</CountBadge>
            <span className="ml-auto text-[10px] text-[var(--srf-text-muted)]">
              明确 {counts.confirmed}{counts.unconfirmed ? ` · 待确认 ${counts.unconfirmed}` : ''}{counts.example ? ` · 示例 ${counts.example}` : ''}
            </span>
          </div>
          <div>
            {section.items.map((item, itemIndex) => {
              const evidenceKey = `${activeFunction.id}:${sectionIndex}:${itemIndex}`
              const evidenceOpen = expandedEvidence === evidenceKey
              return <div key={evidenceKey} className="grid grid-cols-[34px_minmax(0,1fr)] gap-3 border-b border-[var(--srf-divider)] py-4 last:border-b-0 max-[900px]:grid-cols-[24px_minmax(0,1fr)]">
                <span className="pt-0.5 text-right font-mono text-[10px] tabular-nums text-[var(--srf-text-muted)]">{String(itemIndex + 1).padStart(2, '0')}</span>
                <div className="min-w-0">
                  {editable
                    ? <Input.TextArea
                      className="w-full text-[12.5px] leading-[1.8]"
                      aria-label={`${activeFunction.name} ${section.title} 内容 ${itemIndex + 1}`}
                      autoSize
                      value={item.text}
                      onChange={(event) => onItemChange(activeFunction.id, sectionIndex, itemIndex, event.target.value)}
                    />
                    : <p className="m-0 whitespace-pre-wrap text-[13px] leading-[1.9] text-[var(--srf-text)] [overflow-wrap:anywhere]">{item.text}</p>}
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <StatusPill status={item.status} />
                    {item.materialBlockIds.length ? <button
                      type="button"
                      className="inline-flex items-center gap-1 rounded-full border border-transparent px-1.5 py-0.5 text-[10px] font-medium text-[var(--srf-accent)] hover:border-[var(--srf-accent-border)] hover:bg-[var(--srf-accent-soft)]"
                      aria-expanded={evidenceOpen}
                      onClick={() => setExpandedEvidence(evidenceOpen ? null : evidenceKey)}
                    >
                      <PaperClipOutlined aria-hidden />
                      依据 {item.materialBlockIds.length}
                      {evidenceOpen ? <span className="text-[9px]">收起</span> : null}
                    </button> : null}
                  </div>
                  {evidenceOpen ? <EvidenceSection blockIds={item.materialBlockIds} material={material} className="mt-3 rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] bg-[var(--srf-hover)] p-3" /> : null}
                </div>
              </div>
            })}
          </div>
        </section>
      })}

      <footer className="mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--srf-card-border)] pt-4 text-[10px] text-[var(--srf-text-muted)]">
        <span>共 {visibleSections.length} 章 · {functionItemList.length} 条说明</span>
        <span>材料已整理为可阅读结构，依据可逐条展开</span>
      </footer>
    </article>
  }

  const renderQuestionArticle = () => {
    if (!activeQuestion) return <div className="m-8 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-8 text-center text-[12px] text-[var(--srf-text-muted)]">暂无待确认问题</div>
    const index = Math.min(questionIndex, material.questions.length - 1)
    return <article
      role="region"
      aria-label="待确认详情"
      className="px-[56px] pb-8 pt-[52px] max-[900px]:px-8 max-[900px]:pb-9 max-[900px]:pt-9"
    >
      <div className={ROW_WRAP_CLASS}>
        <span className="inline-flex items-center gap-1 rounded-[4px] bg-[var(--app-status-warning-bg)] px-1.5 py-0.5 text-[9.5px] font-semibold text-[var(--app-status-warning-text)]"><WarningOutlined aria-hidden /> 待确认</span>
        <span className="font-mono text-[9.5px] text-[var(--srf-text-muted)]">{activeQuestion.id || '问题'}</span>
        <span className="ml-auto rounded-full border border-[var(--app-surface-border)] bg-[var(--srf-hover)] px-2 py-0.5 text-[10px] text-[var(--srf-text-muted)]">{questionScope(activeQuestion, names)}</span>
      </div>
      {editable
        ? <label className="mt-3 flex flex-col gap-1.5">
          <span className="text-[10px] text-[var(--srf-text-muted)]">问题</span>
          <Input.TextArea
            aria-label={`待确认问题 ${index + 1}`}
            autoSize
            value={activeQuestion.question}
            onChange={(event) => onQuestionChange(activeQuestion.id, event.target.value)}
          />
        </label>
        : <h1 className="m-0 mt-3 text-[23px] font-[650] leading-[1.55] text-[var(--srf-text)] [overflow-wrap:anywhere] max-[900px]:text-[19px]">{activeQuestion.question || '未记录问题'}</h1>}

      {activeQuestion.reason ? <section className="mt-6 rounded-[var(--srf-radius-control)] border border-[var(--app-status-warning-border)] bg-[var(--app-status-warning-bg)] px-4 py-3" aria-label="原因">
        <div className="mb-1 flex items-center gap-1.5 text-[10.5px] font-semibold text-[var(--app-status-warning-text)]"><InfoCircleOutlined aria-hidden /> 原因</div>
        <p className="m-0 text-[13px] leading-[1.8] text-[var(--srf-text)] [overflow-wrap:anywhere]">{activeQuestion.reason}</p>
      </section> : null}

      {activeQuestion.functionIds.length ? <section className="mt-6" aria-label="关联功能">
        <h2 className="m-0 text-[11px] font-semibold text-[var(--srf-text)]">关联功能</h2>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {activeQuestion.functionIds.map((id) => {
            const name = names.get(id)
            return <span key={id} className="max-w-full rounded-[6px] border border-[var(--srf-card-border)] bg-[var(--srf-hover)] px-2 py-1 text-[10.5px] leading-[1.5] text-[var(--srf-text-secondary)]">
              <span className="font-mono text-[9px] text-[var(--srf-accent)]">{name ? `${id} ${name}` : id}</span>
            </span>
          })}
        </div>
      </section> : null}

      <EvidenceSection blockIds={activeQuestion.materialBlockIds} material={material} className="mt-6" />

      <footer className="mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--srf-card-border)] pt-4">
        <span className="text-[10px] text-[var(--srf-text-muted)]">问题 {index + 1} / {material.questions.length}</span>
        <div className={ROW_CLASS}>
          <Button size="small" disabled={index === 0} icon={<LeftOutlined />} onClick={() => { setQuestionIndex(index - 1); resetScroll() }}>上一个</Button>
          <Button size="small" disabled={index >= material.questions.length - 1} onClick={() => { setQuestionIndex(index + 1); resetScroll() }}>下一个 <RightOutlined /></Button>
        </div>
      </footer>
    </article>
  }

  const renderOutline = () => {
    if (tab === 'questions') {
      return <aside className="flex w-[208px] flex-none flex-col overflow-y-auto border-l border-[var(--srf-card-border)] bg-[var(--srf-card)] px-4 py-4" aria-label="问题信息">
        <p className="m-0 text-[10px] font-semibold text-[var(--srf-text-muted)]">问题信息</p>
        <div className="mt-3 flex flex-col gap-2 text-[10.5px] text-[var(--srf-text-muted)]">
          <div className={ROW_BETWEEN_CLASS}><span>范围</span><strong className="text-right font-medium text-[var(--srf-text)]">{activeQuestion ? questionScopeCompact(activeQuestion, names) : '—'}</strong></div>
          <div className={ROW_BETWEEN_CLASS}><span>关联功能</span><strong className="font-medium text-[var(--srf-text)]">{activeQuestion?.functionIds.length ?? 0}</strong></div>
          <div className={ROW_BETWEEN_CLASS}><span>材料依据</span><strong className="font-medium text-[var(--srf-text)]">{activeQuestion?.materialBlockIds.length ?? 0}</strong></div>
          <div className={ROW_BETWEEN_CLASS}><span>问题编号</span><strong className="font-mono text-[9.5px] font-medium text-[var(--srf-text)]">{activeQuestion?.id || '—'}</strong></div>
        </div>
        <div className="mt-5 border-t border-[var(--srf-divider)] pt-4">
          <p className="m-0 text-[10px] font-semibold text-[var(--srf-text-muted)]">全部问题</p>
          <div className="mt-2 flex flex-col gap-1">
            {material.questions.map((question, index) => <button key={`${question.id}-${index}`} type="button"
              className={cx('rounded-[5px] px-2 py-1.5 text-left text-[10px] leading-[1.5]', index === Math.min(questionIndex, material.questions.length - 1) ? 'bg-[var(--app-status-warning-bg)] text-[var(--app-status-warning-text)]' : 'bg-transparent text-[var(--srf-text-muted)] hover:bg-[var(--srf-hover)] hover:text-[var(--srf-text)]')}
              onClick={() => { setQuestionIndex(index); resetScroll() }}>
              {index + 1}. {question.question.slice(0, 30)}{question.question.length > 30 ? '…' : ''}
            </button>)}
          </div>
        </div>
      </aside>
    }
    return <aside className="flex w-[208px] flex-none flex-col overflow-y-auto border-l border-[var(--srf-card-border)] bg-[var(--srf-card)] px-4 py-4" aria-label="章节目录">
      <p className="m-0 text-[10px] font-semibold text-[var(--srf-text-muted)]">本页目录</p>
      <div className="mt-2 flex flex-col">
        {visibleSections.map(({ section }, index) => {
          const active = index === safeSectionIndex
          return <button key={`${section.title}-${index}`} type="button"
            className={cx('flex items-start gap-2 border-l-2 py-1.5 pl-2 text-left text-[10.5px] transition-colors', active ? 'border-l-[var(--srf-accent)] font-medium text-[var(--srf-accent)]' : 'border-l-transparent text-[var(--srf-text-muted)] hover:text-[var(--srf-text)]')}
            onClick={() => scrollToSection(index)}>
            <span className="pt-px font-mono text-[9px] tabular-nums">{String(index + 1).padStart(2, '0')}</span>
            <span className="min-w-0 flex-1 leading-[1.5]">{section.title || '未命名章节'}</span>
            <span className="flex-none text-[9px] tabular-nums">{section.items.length}</span>
          </button>
        })}
      </div>
      <div className="mt-auto border-t border-[var(--srf-divider)] pt-4">
        <p className="m-0 text-[10px] font-semibold text-[var(--srf-text-muted)]">材料状态</p>
        <div className="mt-2 flex flex-col gap-1.5 text-[10px] text-[var(--srf-text-muted)]">
          <span className={ROW_BETWEEN_CLASS}><span>说明条目</span><strong className="font-medium tabular-nums text-[var(--srf-text)]">{allItems.length}</strong></span>
          <span className={ROW_BETWEEN_CLASS}><span>明确</span><strong className="font-medium tabular-nums text-[var(--app-status-approved-text)]">{totals.confirmed}</strong></span>
          <span className={ROW_BETWEEN_CLASS}><span>待确认</span><strong className="font-medium tabular-nums text-[var(--app-status-warning-text)]">{totals.unconfirmed}</strong></span>
          <span className={ROW_BETWEEN_CLASS}><span>示例</span><strong className="font-medium tabular-nums text-[var(--srf-accent)]">{totals.example}</strong></span>
        </div>
      </div>
    </aside>
  }

  return <div ref={rootRef} className={`${styles.root} tp-surface flex min-h-0 flex-1 flex-col`} role="region" aria-label="材料整理结果">
    <div className={cx('flex min-h-0 flex-1', stacked && 'flex-col')}>
      {renderLeftRail()}
      <div ref={scrollRef} role="tabpanel" aria-label={tab === 'functions' ? '功能说明' : '待确认'} className="min-w-0 flex-1 overflow-auto bg-[var(--app-shell-bg)]">
        {tab === 'functions' ? renderFunctionArticle() : renderQuestionArticle()}
      </div>
      {showOutline ? renderOutline() : null}
    </div>
  </div>
}
