import { useMemo, useState } from 'react'
import { Empty, Tag } from 'antd'
import { cx } from '@/shared/utils/cx'
import {
  CheckCircleFilled,
  ExclamationCircleFilled,
  LinkOutlined,
  WarningFilled,
} from '@ant-design/icons'
import { parseDesign, stepHasExcluded, type DesignAction, type DesignExpectation, type DesignStep } from './uiStageVisualUtils'
import { VisualEmpty, VisualParseError } from './VisualStates'
import {
  uisvBlockquoteClass,
  uisvInspectorHeadBodyClass,
  uisvInspectorHeadClass,
  uisvInspectorHeadCodeClass,
  uisvInspectorHeadCompactClass,
  uisvInspectorHeadTitleClass,
  uisvInspectorNoteClass,
  uisvInspectorParagraphClass,
  uisvInspectorScrollClass,
  uisvInspectorSectionClass,
  uisvInspectorSectionCountClass,
  uisvInspectorSectionTitleClass,
  uisvNoteBoxAmberClass,
  uisvNoteBoxClass,
  uisvNoteBoxIconClass,
  uisvPillAmberClass,
  uisvPillClass,
  uisvPillCompactClass,
  uisvPillGreenClass,
  uisvPillSlateClass,
  uisvStepBadgeClass,
  uisvTraceIndexAssertClass,
  uisvTraceIndexClass,
  uisvTraceItemClass,
  uisvTraceItemExcludedClass,
} from './uiStageVisualClasses'

function coveragePill(coverage: string) {
  return coverage === 'full'
    ? <span className={cx(uisvPillClass, uisvPillGreenClass)}>完整覆盖</span>
    : <span className={cx(uisvPillClass, uisvPillAmberClass)}>部分覆盖</span>
}

function StatusPill({ status }: { status: string }) {
  if (status === 'excluded') return <span className={cx(uisvPillClass, uisvPillCompactClass, uisvPillAmberClass)}>excluded</span>
  if (status === 'bookkeeping') return <span className={cx(uisvPillClass, uisvPillCompactClass, uisvPillSlateClass)}>记录</span>
  return <span className={cx(uisvPillClass, uisvPillCompactClass, uisvPillGreenClass)}>included</span>
}

function TraceItem({ index, operation, target, value, status, reason, assertion }: {
  index: number
  operation?: string
  target: string
  value: string
  status: string
  reason: string
  assertion?: string
}) {
  return <div className={cx(uisvTraceItemClass, status === 'excluded' && uisvTraceItemExcludedClass)}>
    <span className={cx(uisvTraceIndexClass, assertion && uisvTraceIndexAssertClass)}>{index}</span>
    <div className="uisv-trace-copy flex min-w-0 flex-1 flex-col gap-px [&_em]:text-[11.5px] [&_em]:not-italic [&_em]:leading-[1.5] [&_em]:text-[var(--uisv-b45309)] [&_span]:overflow-hidden [&_span]:text-ellipsis [&_span]:whitespace-nowrap [&_span]:text-[11.5px] [&_span]:text-[var(--uisv-94a3b8)] [&_strong]:text-[11.5px] [&_strong]:text-[var(--uisv-334155)]"><strong>{operation ?? assertion ?? 'item'}</strong><span>{target}{value ? ` · ${value}` : ''}</span>{status === 'excluded' && reason ? <em>{reason}</em> : null}</div>
    <StatusPill status={status} />
  </div>
}

function StepInspector({ step, limitations }: { step: DesignStep; limitations: string[] }) {
  return <div className={uisvInspectorScrollClass}>
    <div className={cx(uisvInspectorHeadClass, uisvInspectorHeadCompactClass)}><span className={uisvStepBadgeClass}>S{step.sourceStepNo}</span><div className={uisvInspectorHeadBodyClass}><h3 className={uisvInspectorHeadTitleClass}>步骤 {step.sourceStepNo}</h3><code className={uisvInspectorHeadCodeClass}>{step.actions.length} 操作 · {step.expectations.length} 断言</code></div></div>
    <section className={uisvInspectorSectionClass}><h4 className={uisvInspectorSectionTitleClass}>源操作原文</h4><blockquote className={uisvBlockquoteClass}>{step.sourceAction || '没有记录源操作原文'}</blockquote></section>
    <section className={uisvInspectorSectionClass}><h4 className={uisvInspectorSectionTitleClass}>拆解操作 <span className={uisvInspectorSectionCountClass}>{step.actions.length}</span></h4>{step.actions.length ? step.actions.map((action: DesignAction, index) => <TraceItem key={action.actionId} index={index + 1} operation={action.operation} target={action.target} value={action.value} status={action.status} reason={action.reason} />) : <p className={cx('uisv-muted', uisvInspectorParagraphClass)}>没有拆解出操作。</p>}</section>
    <section className={uisvInspectorSectionClass}><h4 className={uisvInspectorSectionTitleClass}>可执行断言 <span className={uisvInspectorSectionCountClass}>{step.expectations.length}</span></h4>{step.expectations.length ? step.expectations.map((expectation: DesignExpectation, index) => <TraceItem key={expectation.expectationId} index={index + 1} assertion={expectation.assertion} target={expectation.target} value={expectation.value} status={expectation.status} reason={expectation.reason} />) : <p className={cx('uisv-muted', uisvInspectorParagraphClass)}>没有拆解出断言。</p>}</section>
    {limitations.length ? <section className={uisvInspectorSectionClass}><h4 className={uisvInspectorSectionTitleClass}>本用例限制 <span className={uisvInspectorSectionCountClass}>{limitations.length}</span></h4>{limitations.slice(0, 2).map(limitation => <div className={cx(uisvNoteBoxClass, uisvNoteBoxAmberClass, uisvNoteBoxIconClass)} key={limitation}><WarningFilled /><span>{limitation}</span></div>)}</section> : null}
    <div className={uisvInspectorNoteClass}><LinkOutlined /> 每个操作和断言都保留 sourceQuote；审核时可直接对照源功能用例，不需要在 JSON 和页面之间来回切换。</div>
  </div>
}

export function DesignVisual({ content, onShowRaw }: { content: string; onShowRaw: () => void }) {
  const data = useMemo(() => parseDesign(content), [content])
  const [caseId, setCaseId] = useState('')
  const [stepNo, setStepNo] = useState(0)
  if (!data) return <VisualParseError label="UI 用例设计 JSON" onShowRaw={onShowRaw} />
  if (data.cases.length === 0) {
    return <VisualEmpty title="暂无可视化的 UI 场景" description="当前产物里没有 cases；可以切换到 JSON 查看原文。" onShowRaw={onShowRaw} />
  }

  const activeCase = data.cases.find(candidate => candidate.caseId === caseId) ?? data.cases[0]
  const activeStep = activeCase.steps.find(step => step.sourceStepNo === stepNo) ?? activeCase.steps[0]
  const excludedCount = activeCase.steps.reduce((total, step) => total + step.actions.filter(action => action.status === 'excluded').length + step.expectations.filter(expectation => expectation.status === 'excluded').length, 0)

  return <div className="uisv uisv-design grid h-full min-h-0 grid-cols-[230px_minmax(0,1fr)_344px] gap-2.5 text-[13px] max-[1200.01px]:grid-cols-[190px_minmax(0,1fr)]">
    <aside className="uisv-pane uisv-nav flex min-h-0 flex-col overflow-hidden rounded-[10px] border border-[var(--uisv-e3eaf3)] bg-[var(--uisv-fff)]">
      <div className="uisv-pane-head flex flex-none items-center justify-between px-3 pb-[9px] pt-3 text-[13.5px] font-bold text-[var(--uisv-334155)]"><span>UI 场景</span><em className="inline-flex h-[19px] min-w-[21px] items-center justify-center rounded-[5px] bg-[var(--uisv-f1f5f9)] px-[5px] text-[11px] not-italic text-[var(--uisv-64748b)]">{data.cases.length}</em></div>
      <div className="uisv-case-list min-h-0 flex-1 overflow-auto px-1.5">
        {data.cases.map(candidate => {
          const hasExcluded = candidate.steps.some(stepHasExcluded)
          const active = candidate.caseId === activeCase.caseId
          return <button type="button" key={candidate.caseId} className={`uisv-case-item flex w-full cursor-pointer items-center gap-2 rounded-[7px] border-0 p-2 text-left font-[inherit] [&+&]:mt-px ${active ? 'active bg-[var(--uisv-eff6ff)]' : 'bg-transparent hover:bg-[var(--uisv-f8fafc)]'}`} onClick={() => { setCaseId(candidate.caseId); setStepNo(0) }}>
            <span className={`uisv-case-dot ${candidate.coverage === 'full' ? 'green' : 'amber'} h-1.5 w-1.5 flex-[0_0_6px] rounded-full ${candidate.coverage === 'full' ? 'bg-[var(--uisv-22c55e)]' : 'bg-[var(--uisv-f59e0b)]'}`} />
            <span className="uisv-case-copy flex min-w-0 flex-1 flex-col gap-px"><strong className="overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-semibold text-[var(--uisv-1e293b)]" title={candidate.name}>{candidate.name}</strong><small className="overflow-hidden text-ellipsis whitespace-nowrap text-[11.5px] text-[var(--uisv-94a3b8)]">{candidate.steps.length} 步 · {candidate.coverage === 'full' ? '完整覆盖' : '部分覆盖'}</small></span>
            {hasExcluded ? <span className="uisv-case-flag text-[10px] text-[var(--uisv-d97706)]"><ExclamationCircleFilled /></span> : null}
          </button>
        })}
      </div>
      <div className="uisv-nav-foot m-2 flex-none rounded-[8px] bg-[var(--uisv-f8fafc)] p-2"><div className="uisv-nav-foot-title mb-[5px] text-[12px] font-semibold text-[var(--uisv-64748b)]">本页统计</div><div className="uisv-nav-stats grid grid-cols-[auto_1fr_auto_1fr] items-center gap-1"><strong className="text-[19px] text-[var(--uisv-0f172a)]">{data.cases.filter(item => item.coverage === 'full').length}</strong><span className="text-[11px] text-[var(--uisv-94a3b8)]">完整</span><strong className="text-[19px] text-[var(--uisv-0f172a)]">{data.cases.filter(item => item.coverage !== 'full').length}</strong><span className="text-[11px] text-[var(--uisv-94a3b8)]">部分</span></div><div className="uisv-cover-note mt-[5px] text-[11px] leading-[1.5] text-[var(--uisv-94a3b8)]">{data.assertions.length} 种断言 · {data.operations.length} 种操作</div></div>
    </aside>

    <main className="uisv-pane uisv-main flex min-h-0 flex-col overflow-hidden rounded-[10px] border border-[var(--uisv-e3eaf3)] bg-[var(--uisv-fff)]">
      <div className="uisv-main-head flex flex-none items-start justify-between gap-2.5 px-3 pb-2 pt-3">
        <div><h3 className="m-0 overflow-hidden text-ellipsis whitespace-nowrap text-[15.5px] font-bold text-[var(--uisv-0f172a)]">{activeCase.name}</h3><p className="m-0 mt-1 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] leading-[1.45] text-[var(--uisv-94a3b8)]">{activeCase.goal || activeCase.sourceTitle || '没有用例目标'}</p></div>
        <div className="uisv-head-tags flex flex-none items-center gap-1 [&_.ant-tag]:m-0 [&_.ant-tag]:text-[11px] [&_.ant-tag]:leading-[17px]">{coveragePill(activeCase.coverage)}<Tag variant="filled">{activeCase.steps.length} 步</Tag>{excludedCount ? <Tag variant="filled" color="warning">{excludedCount} 排除</Tag> : null}</div>
      </div>
      {activeCase.preconditions.length ? <div className="uisv-precondition-strip mx-3 mb-2 flex flex-none items-center gap-[7px] overflow-hidden rounded-[7px] border border-[var(--uisv-e6f4ea)] bg-[var(--uisv-f7fdf9)] px-[9px] py-2 text-[11.5px] text-[var(--uisv-4b7a5a)] [&_.anticon]:flex-none [&_.anticon]:text-[12px] [&_.anticon]:text-[var(--uisv-16a34a)] [&_span]:overflow-hidden [&_span]:text-ellipsis [&_span]:whitespace-nowrap [&_strong]:whitespace-nowrap [&_strong]:text-[11.5px] [&_strong]:text-[var(--uisv-166534)]"><CheckCircleFilled /><strong>前置条件 {activeCase.preconditions.length} 项</strong><span title={activeCase.preconditions[0]}>{activeCase.preconditions[0]}{activeCase.preconditions.length > 1 ? ` · 另有 ${activeCase.preconditions.length - 1} 项` : ''}</span></div> : null}
      {activeCase.steps.length === 0 ? <div className="uisv-inline-empty flex min-h-0 flex-1 items-center justify-center"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="这条场景还没有步骤" /></div> : (
        <div className="uisv-table-wrap min-h-0 flex-1 overflow-auto border-t border-[var(--uisv-eef2f7)]">
          <div className="uisv-table uisv-design-table min-w-[620px]">
            <div className="uisv-thead uisv-design-grid grid h-9 grid-cols-[38px_minmax(0,1fr)_48px_48px_80px] items-center gap-[7px] bg-[var(--uisv-f8fafc)] px-[11px] text-[11.5px] font-semibold text-[var(--uisv-7b8799)]"><span>#</span><span>源操作</span><span>操作</span><span>断言</span><span>检查结论</span></div>
            {activeCase.steps.map(step => {
              const selected = step.sourceStepNo === activeStep?.sourceStepNo
              return <button type="button" key={step.sourceStepNo} className={`uisv-row uisv-design-grid grid min-h-[72px] w-full cursor-pointer grid-cols-[38px_minmax(0,1fr)_48px_48px_80px] items-center gap-[7px] border-0 border-t border-[var(--uisv-f3f6fa)] px-[11px] text-left font-[inherit] text-[13px] text-[var(--uisv-334155)] ${selected ? 'selected bg-[var(--uisv-eff6ff)] shadow-[inset_3px_0_0_var(--uisv-2563eb)]' : 'bg-[var(--uisv-fff)] hover:bg-[var(--uisv-fbfdff)]'}`} onClick={() => setStepNo(step.sourceStepNo)}>
              <span className="uisv-step-no text-[11px] tabular-nums text-[var(--uisv-94a3b8)]">{String(step.sourceStepNo).padStart(2, '0')}</span>
              <span className="uisv-step-source line-clamp-2 overflow-hidden text-[12.5px] leading-[1.45] text-[var(--uisv-475569)]">{step.sourceAction || '—'}</span>
              <span className="uisv-step-count text-[11.5px] text-[var(--uisv-94a3b8)]"><strong className="text-[13px] text-[var(--uisv-334155)]">{step.actions.length}</strong> 个</span>
              <span className="uisv-step-count text-[11.5px] text-[var(--uisv-94a3b8)]"><strong className="text-[13px] text-[var(--uisv-334155)]">{step.expectations.length}</strong> 个</span>
              <span>{stepHasExcluded(step) ? <span className="uisv-pill amber inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded-[5px] bg-[var(--uisv-fff8eb)] px-[7px] text-[11.5px] font-semibold text-[var(--uisv-b45309)]">含排除项</span> : <span className="uisv-pill green inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded-[5px] bg-[var(--uisv-f0fdf4)] px-[7px] text-[11.5px] font-semibold text-[var(--uisv-15803d)]">可执行</span>}</span>
            </button>
            })}
          </div>
        </div>
      )}
      <div className="uisv-design-summary mx-[11px] mb-1.5 flex flex-none items-center gap-3 rounded-[7px] border border-[var(--uisv-e0e7ff)] bg-[var(--uisv-f8faff)] px-[9px] py-2 text-[11.5px] text-[var(--uisv-64748b)] [&_em]:min-w-0 [&_em]:flex-1 [&_em]:overflow-hidden [&_em]:text-ellipsis [&_em]:whitespace-nowrap [&_em]:text-right [&_em]:text-[11.5px] [&_em]:not-italic [&_span]:inline-flex [&_span]:items-baseline [&_span]:gap-[3px] [&_span]:whitespace-nowrap [&_span.warn_strong]:text-[var(--uisv-b45309)] [&_strong]:text-[15px] [&_strong]:tabular-nums [&_strong]:text-[var(--uisv-1e3a8a)]">
        <span><strong>{activeCase.steps.length}</strong> 步骤</span>
        <span><strong>{activeCase.steps.reduce((total, step) => total + step.actions.length, 0)}</strong> 操作</span>
        <span><strong>{activeCase.steps.reduce((total, step) => total + step.expectations.length, 0)}</strong> 断言</span>
        <span className={excludedCount ? 'warn' : ''}><strong>{excludedCount}</strong> 排除</span>
        <em>所有步骤均保留 sourceQuote；排除项需在审核备注中说明。</em>
      </div>
      <div className="uisv-table-foot flex flex-[0_0_32px] items-center justify-between border-t border-[var(--uisv-eef2f7)] bg-[var(--uisv-fbfcfe)] px-3 text-[11px] text-[var(--uisv-94a3b8)]"><span>步骤 {activeCase.steps.length} 个</span><span>点击步骤查看原文映射</span></div>
    </main>

    <aside className="uisv-pane uisv-inspector flex min-h-0 flex-col overflow-hidden rounded-[10px] border border-[var(--uisv-e3eaf3)] bg-[var(--uisv-fff)] max-[1200.01px]:hidden">
      {activeStep ? <StepInspector step={activeStep} limitations={activeCase.limitations} /> : <div className="uisv-inline-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择步骤查看拆解" /></div>}
    </aside>
  </div>
}
