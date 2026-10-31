import { useMemo, useState } from 'react'
import { Empty, Tag } from 'antd'
import {
  CheckCircleFilled,
  ExclamationCircleFilled,
  LinkOutlined,
  WarningFilled,
} from '@ant-design/icons'
import { parseDesign, stepHasExcluded, type DesignAction, type DesignExpectation, type DesignStep } from './uiStageVisualUtils'
import { VisualEmpty, VisualParseError } from './VisualStates'

function coveragePill(coverage: string) {
  return coverage === 'full'
    ? <span className="uisv-pill green">完整覆盖</span>
    : <span className="uisv-pill amber">部分覆盖</span>
}

function StatusPill({ status }: { status: string }) {
  if (status === 'excluded') return <span className="uisv-pill amber">excluded</span>
  if (status === 'bookkeeping') return <span className="uisv-pill slate">记录</span>
  return <span className="uisv-pill green">included</span>
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
  return <div className={`uisv-trace-item${status === 'excluded' ? ' excluded' : ''}`}>
    <span className={`uisv-trace-index${assertion ? ' assert' : ''}`}>{index}</span>
    <div className="uisv-trace-copy"><strong>{operation ?? assertion ?? 'item'}</strong><span>{target}{value ? ` · ${value}` : ''}</span>{status === 'excluded' && reason ? <em>{reason}</em> : null}</div>
    <StatusPill status={status} />
  </div>
}

function StepInspector({ step, limitations }: { step: DesignStep; limitations: string[] }) {
  return <div className="uisv-inspector-scroll">
    <div className="uisv-inspector-head compact"><span className="uisv-step-badge">S{step.sourceStepNo}</span><div><h3>步骤 {step.sourceStepNo}</h3><code>{step.actions.length} 操作 · {step.expectations.length} 断言</code></div></div>
    <section><h4>源操作原文</h4><blockquote>{step.sourceAction || '没有记录源操作原文'}</blockquote></section>
    <section><h4>拆解操作 <span>{step.actions.length}</span></h4>{step.actions.length ? step.actions.map((action: DesignAction, index) => <TraceItem key={action.actionId} index={index + 1} operation={action.operation} target={action.target} value={action.value} status={action.status} reason={action.reason} />) : <p className="uisv-muted">没有拆解出操作。</p>}</section>
    <section><h4>可执行断言 <span>{step.expectations.length}</span></h4>{step.expectations.length ? step.expectations.map((expectation: DesignExpectation, index) => <TraceItem key={expectation.expectationId} index={index + 1} assertion={expectation.assertion} target={expectation.target} value={expectation.value} status={expectation.status} reason={expectation.reason} />) : <p className="uisv-muted">没有拆解出断言。</p>}</section>
    {limitations.length ? <section><h4>本用例限制 <span>{limitations.length}</span></h4>{limitations.slice(0, 2).map(limitation => <div className="uisv-note-box amber" key={limitation}><WarningFilled /><span>{limitation}</span></div>)}</section> : null}
    <div className="uisv-inspector-note"><LinkOutlined /> 每个操作和断言都保留 sourceQuote；审核时可直接对照源功能用例，不需要在 JSON 和页面之间来回切换。</div>
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

  return <div className="uisv uisv-design">
    <aside className="uisv-pane uisv-nav">
      <div className="uisv-pane-head"><span>UI 场景</span><em>{data.cases.length}</em></div>
      <div className="uisv-case-list">
        {data.cases.map(candidate => {
          const hasExcluded = candidate.steps.some(stepHasExcluded)
          return <button type="button" key={candidate.caseId} className={`uisv-case-item${candidate.caseId === activeCase.caseId ? ' active' : ''}`} onClick={() => { setCaseId(candidate.caseId); setStepNo(0) }}>
            <span className={`uisv-case-dot ${candidate.coverage === 'full' ? 'green' : 'amber'}`} />
            <span className="uisv-case-copy"><strong title={candidate.name}>{candidate.name}</strong><small>{candidate.steps.length} 步 · {candidate.coverage === 'full' ? '完整覆盖' : '部分覆盖'}</small></span>
            {hasExcluded ? <span className="uisv-case-flag"><ExclamationCircleFilled /></span> : null}
          </button>
        })}
      </div>
      <div className="uisv-nav-foot"><div className="uisv-nav-foot-title">本页统计</div><div className="uisv-nav-stats"><strong>{data.cases.filter(item => item.coverage === 'full').length}</strong><span>完整</span><strong>{data.cases.filter(item => item.coverage !== 'full').length}</strong><span>部分</span></div><div className="uisv-cover-note">{data.assertions.length} 种断言 · {data.operations.length} 种操作</div></div>
    </aside>

    <main className="uisv-pane uisv-main">
      <div className="uisv-main-head">
        <div><h3>{activeCase.name}</h3><p>{activeCase.goal || activeCase.sourceTitle || '没有用例目标'}</p></div>
        <div className="uisv-head-tags">{coveragePill(activeCase.coverage)}<Tag variant="filled">{activeCase.steps.length} 步</Tag>{excludedCount ? <Tag variant="filled" color="warning">{excludedCount} 排除</Tag> : null}</div>
      </div>
      {activeCase.preconditions.length ? <div className="uisv-precondition-strip"><CheckCircleFilled /><strong>前置条件 {activeCase.preconditions.length} 项</strong><span title={activeCase.preconditions[0]}>{activeCase.preconditions[0]}{activeCase.preconditions.length > 1 ? ` · 另有 ${activeCase.preconditions.length - 1} 项` : ''}</span></div> : null}
      {activeCase.steps.length === 0 ? <div className="uisv-inline-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="这条场景还没有步骤" /></div> : (
        <div className="uisv-table-wrap">
          <div className="uisv-table uisv-design-table">
            <div className="uisv-thead uisv-design-grid"><span>#</span><span>源操作</span><span>操作</span><span>断言</span><span>检查结论</span></div>
            {activeCase.steps.map(step => <button type="button" key={step.sourceStepNo} className={`uisv-row uisv-design-grid${step.sourceStepNo === activeStep?.sourceStepNo ? ' selected' : ''}`} onClick={() => setStepNo(step.sourceStepNo)}>
              <span className="uisv-step-no">{String(step.sourceStepNo).padStart(2, '0')}</span>
              <span className="uisv-step-source">{step.sourceAction || '—'}</span>
              <span className="uisv-step-count"><strong>{step.actions.length}</strong> 个</span>
              <span className="uisv-step-count"><strong>{step.expectations.length}</strong> 个</span>
              <span>{stepHasExcluded(step) ? <span className="uisv-pill amber">含排除项</span> : <span className="uisv-pill green">可执行</span>}</span>
            </button>)}
          </div>
        </div>
      )}
      <div className="uisv-design-summary">
        <span><strong>{activeCase.steps.length}</strong> 步骤</span>
        <span><strong>{activeCase.steps.reduce((total, step) => total + step.actions.length, 0)}</strong> 操作</span>
        <span><strong>{activeCase.steps.reduce((total, step) => total + step.expectations.length, 0)}</strong> 断言</span>
        <span className={excludedCount ? 'warn' : ''}><strong>{excludedCount}</strong> 排除</span>
        <em>所有步骤均保留 sourceQuote；排除项需在审核备注中说明。</em>
      </div>
      <div className="uisv-table-foot"><span>步骤 {activeCase.steps.length} 个</span><span>点击步骤查看原文映射</span></div>
    </main>

    <aside className="uisv-pane uisv-inspector">
      {activeStep ? <StepInspector step={activeStep} limitations={activeCase.limitations} /> : <div className="uisv-inline-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择步骤查看拆解" /></div>}
    </aside>
  </div>
}
