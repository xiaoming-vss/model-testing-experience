import { useMemo, useState } from 'react'
import { Alert, Empty, Progress, Tag } from 'antd'
import { cx } from '@/shared/utils/cx'
import {
  CheckCircleFilled,
  ExclamationCircleFilled,
} from '@ant-design/icons'
import { parseYaml, type YamlMissing, type YamlStep } from './uiStageVisualUtils'
import { VisualEmpty, VisualParseError } from './VisualStates'
import {
  uisvFixListClass,
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
  uisvMissingBoxClass,
  uisvMissingHeadClass,
  uisvMissingHeadCodeClass,
  uisvMissingHeadStrongClass,
  uisvMissingParagraphClass,
  uisvMissingValueClass,
  uisvMissingValueCodeClass,
  uisvMissingValueTextClass,
  uisvNoteBoxClass,
  uisvNoteBoxGreenClass,
  uisvNoteBoxIconClass,
  uisvStepBadgeAmberClass,
  uisvStepBadgeClass,
  uisvValueGridClass,
  uisvValueGridCodeClass,
  uisvValueGridItemClass,
  uisvValueGridLabelClass,
} from './uiStageVisualClasses'

function keywordClass(keyword: string): string {
  if (['click', 'assert_visible', 'assert_hidden', 'assert_text', 'open', 'wait_text', 'input'].includes(keyword)) return keyword
  return 'other'
}

function MissingInspector({ step }: { step: YamlStep }) {
  return <div className={uisvInspectorScrollClass}>
    <div className={cx(uisvInspectorHeadClass, uisvInspectorHeadCompactClass)}>
      <span className={cx(uisvStepBadgeClass, uisvStepBadgeAmberClass)}>S{step.orderNo}</span>
      <div className={uisvInspectorHeadBodyClass}><h3 className={uisvInspectorHeadTitleClass}>{step.name}</h3><code className={uisvInspectorHeadCodeClass}>orderNo {step.orderNo} · {step.keyword}</code></div>
      {step.missing.length ? <Tag variant="filled" color="warning">{step.missing.length} 项待补</Tag> : <Tag variant="filled" color="green">就绪</Tag>}
    </div>
    <section className={uisvInspectorSectionClass}><h4 className={uisvInspectorSectionTitleClass}>当前步骤</h4><p className={uisvInspectorParagraphClass}>{step.locatorValue || step.operationValue || '没有额外定位或值。'}</p><div className={uisvValueGridClass}>{step.locatorType ? <span className={uisvValueGridItemClass}><em className={uisvValueGridLabelClass}>定位类型</em><code className={uisvValueGridCodeClass}>{step.locatorType}</code></span> : null}{step.operationValue ? <span className={uisvValueGridItemClass}><em className={uisvValueGridLabelClass}>操作值</em><code className={uisvValueGridCodeClass}>{step.operationValue}</code></span> : null}</div></section>
    <section className={uisvInspectorSectionClass}><h4 className={uisvInspectorSectionTitleClass}>需要补齐的字段 <span className={uisvInspectorSectionCountClass}>{step.missing.length}</span></h4>
      {step.missing.length ? step.missing.map((missing: YamlMissing, index) => <div className={uisvMissingBoxClass} key={`${missing.target}-${index}`}>
        <div className={uisvMissingHeadClass}>{missing.fields.map(field => <code className={uisvMissingHeadCodeClass} key={field}>{field}</code>)}<strong className={uisvMissingHeadStrongClass}>{missing.target || missing.operation || '未命名缺口'}</strong></div>
        <p className={uisvMissingParagraphClass}>{missing.reason}</p>
        {missing.value ? <div className={uisvMissingValueClass}><span className={uisvMissingValueTextClass}>当前值</span><code className={uisvMissingValueCodeClass}>{missing.value}</code></div> : null}
      </div>) : <div className={cx(uisvNoteBoxClass, uisvNoteBoxGreenClass, uisvNoteBoxIconClass)}><CheckCircleFilled /><span>这个步骤没有声明字段缺口；仍需核对测试数据、设计冲突与定位正确性。</span></div>}
    </section>
    <section className={uisvInspectorSectionClass}><h4 className={uisvInspectorSectionTitleClass}>如何补齐</h4><ol className={uisvFixListClass}><li>优先补行级定位：按业务主键定位行，再定位行内单元格或控件。</li><li>页面地址和期望文本属于测试数据，可以按环境批量填写。</li><li>补齐后切换回 YAML 修改原文，或继续使用当前原文编辑。</li></ol></section>
    <div className={uisvInspectorNoteClass}><ExclamationCircleFilled /> 当前步骤来自真实 YAML 产物；可视化视图只读，修改请切换到 YAML。</div>
  </div>
}

export function YamlVisual({ content, onShowRaw }: { content: string; onShowRaw: () => void }) {
  const parsed = useMemo(() => parseYaml(content), [content])
  const [caseIndex, setCaseIndex] = useState(0)
  const [stepNo, setStepNo] = useState(0)
  if (parsed.error) return <VisualParseError label="用例 YAML" onShowRaw={onShowRaw} />
  if (parsed.cases.length === 0) {
    return <VisualEmpty title="暂无可视化的 UI 用例" description="当前 YAML 里没有可解析的用例；可以切换到 YAML 查看原文。" onShowRaw={onShowRaw} />
  }
  const activeCase = parsed.cases[caseIndex] ?? parsed.cases[0]
  const activeStep = activeCase.steps.find(step => step.orderNo === stepNo) ?? activeCase.steps[0]
  const ready = activeCase.steps.length - activeCase.missingSteps
  const percent = activeCase.steps.length ? Math.round(ready / activeCase.steps.length * 100) : 0
  const totalMissing = parsed.cases.reduce((total, candidate) => total + candidate.missingSteps, 0)
  const totalSteps = parsed.cases.reduce((total, candidate) => total + candidate.steps.length, 0)

  return <div className="uisv uisv-yaml grid h-full min-h-0 grid-cols-[230px_minmax(0,1fr)_344px] gap-2.5 text-[13px] max-[1200.01px]:grid-cols-[190px_minmax(0,1fr)]">
    <aside className="uisv-pane uisv-nav flex min-h-0 flex-col overflow-hidden rounded-[10px] border border-[var(--uisv-e3eaf3)] bg-[var(--uisv-fff)]">
      <div className="uisv-pane-head flex flex-none items-center justify-between px-3 pb-[9px] pt-3 text-[13.5px] font-bold text-[var(--uisv-334155)]"><span>UI 用例</span><em className="inline-flex h-[19px] min-w-[21px] items-center justify-center rounded-[5px] bg-[var(--uisv-f1f5f9)] px-[5px] text-[11px] not-italic text-[var(--uisv-64748b)]">{parsed.cases.length}</em></div>
      <div className="uisv-case-list min-h-0 flex-1 overflow-auto px-1.5">
        {parsed.cases.map((candidate, index) => {
          const candidateReady = candidate.steps.length - candidate.missingSteps
          const active = index === caseIndex
          return <button type="button" key={`${candidate.name}-${index}`} className={`uisv-case-item flex w-full cursor-pointer items-center gap-2 rounded-[7px] border-0 p-2 text-left font-[inherit] [&+&]:mt-px ${active ? 'active bg-[var(--uisv-eff6ff)]' : 'bg-transparent hover:bg-[var(--uisv-f8fafc)]'}`} onClick={() => { setCaseIndex(index); setStepNo(0) }}>
            <span className={`uisv-case-dot ${candidate.missingSteps || candidate.completionIssues.length ? 'amber' : 'green'} h-1.5 w-1.5 flex-[0_0_6px] rounded-full ${candidate.missingSteps || candidate.completionIssues.length ? 'bg-[var(--uisv-f59e0b)]' : 'bg-[var(--uisv-22c55e)]'}`} />
            <span className="uisv-case-copy flex min-w-0 flex-1 flex-col gap-px"><strong className="overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-semibold text-[var(--uisv-1e293b)]" title={candidate.name}>{candidate.name}</strong><small className="overflow-hidden text-ellipsis whitespace-nowrap text-[11.5px] text-[var(--uisv-94a3b8)]">{candidateReady}/{candidate.steps.length} 步字段完整</small></span>
            <span className={`uisv-missing-count${candidate.missingSteps ? '' : ' ready'} inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-[4px] px-1 text-[11px] tabular-nums ${candidate.missingSteps ? 'bg-[var(--uisv-fff8eb)] text-[var(--uisv-b45309)]' : 'bg-[var(--uisv-f0fdf4)] text-[var(--uisv-15803d)]'}`}>{candidate.missingSteps || candidate.completionIssues.length || '✓'}</span>
          </button>
        })}
      </div>
      <div className="uisv-nav-foot m-2 flex-none rounded-[8px] bg-[var(--uisv-f8fafc)] p-2"><div className="uisv-nav-foot-title mb-[5px] text-[12px] font-semibold text-[var(--uisv-64748b)]">缺口总览</div><div className="uisv-nav-stats grid grid-cols-[auto_1fr_auto_1fr] items-center gap-1"><strong className="text-[19px] text-[var(--uisv-0f172a)]">{totalSteps}</strong><span className="text-[11px] text-[var(--uisv-94a3b8)]">步骤</span><strong className="text-[19px] text-[var(--uisv-0f172a)]">{totalMissing}</strong><span className="text-[11px] text-[var(--uisv-94a3b8)]">待补</span></div><div className="uisv-cover-note mt-[5px] text-[11px] leading-[1.5] text-[var(--uisv-94a3b8)]">{parsed.cases.length} 条用例 · {totalMissing || parsed.cases.some(candidate => candidate.completionIssues.length) ? '仍有待处理内容' : '未声明缺口，采用前仍需人工检查'}</div></div>
    </aside>

    <main className="uisv-pane uisv-main flex min-h-0 flex-col overflow-hidden rounded-[10px] border border-[var(--uisv-e3eaf3)] bg-[var(--uisv-fff)]">
      <div className="uisv-main-head flex flex-none items-start justify-between gap-2.5 px-3 pb-2 pt-3">
        <div><h3 className="m-0 overflow-hidden text-ellipsis whitespace-nowrap text-[15.5px] font-bold text-[var(--uisv-0f172a)]">{activeCase.name}</h3><p className="m-0 mt-1 overflow-hidden text-ellipsis whitespace-nowrap text-[12px] leading-[1.45] text-[var(--uisv-94a3b8)]">{activeCase.steps.length} 个步骤 · {ready} 个字段完整 · {activeCase.missingSteps} 个含缺口</p></div>
        <div className="uisv-head-tags flex flex-none items-center gap-1 [&_.ant-tag]:m-0 [&_.ant-tag]:text-[11px] [&_.ant-tag]:leading-[17px]"><Tag variant="filled" color={activeCase.enabled ? 'green' : 'default'}>{activeCase.enabled ? '启用' : '停用'}</Tag><Tag variant="filled" color={activeCase.missingSteps ? 'warning' : 'green'}>{activeCase.missingSteps ? `${activeCase.missingSteps} 步待补` : activeCase.completionIssues.length ? '有待处理内容' : '字段完整'}</Tag></div>
      </div>
      {activeCase.completionIssues.length ? <Alert className="ui-yaml-issues mx-3 mb-2 flex-none [&_summary]:cursor-pointer [&_ul]:max-h-40 [&_ul]:overflow-auto [&_ul]:ps-5" type="warning" showIcon title="此用例仍有待处理内容"
        description={<details><summary>查看 {activeCase.completionIssues.length} 项待补数据与设计冲突</summary><ul>{activeCase.completionIssues.map((issue, index) => <li key={index}>{issue}</li>)}</ul></details>} /> : null}
      <div className="uisv-readiness-strip mx-3 mb-2 grid flex-none grid-cols-[130px_minmax(0,1fr)_auto] items-center gap-[9px] rounded-[7px] border border-[var(--uisv-fde8c3)] bg-[var(--uisv-fffaf0)] px-[9px] py-2">
        <div className="uisv-readiness-copy flex flex-col gap-px"><strong className="text-[12px] text-[var(--uisv-92400e)]">字段完整度 {percent}%</strong><span className="text-[11px] text-[var(--uisv-a16207)]">{ready} / {activeCase.steps.length} 步</span></div>
        <Progress percent={percent} showInfo={false} strokeColor={activeCase.missingSteps ? 'var(--ant-color-warning)' : 'var(--ant-color-success)'} railColor="var(--ant-color-fill-secondary)" />
        <div className="uisv-readiness-legend flex gap-[7px] whitespace-nowrap text-[11px] text-[var(--uisv-64748b)] [&_i]:h-[5px] [&_i]:w-[5px] [&_i]:rounded-full [&_span]:inline-flex [&_span]:items-center [&_span]:gap-[3px] [&_.ready]:bg-[var(--uisv-16a34a)] [&_.gap]:bg-[var(--uisv-d97706)]"><span><i className="ready" />字段完整 {ready}</span><span><i className="gap" />待补 {activeCase.missingSteps}</span></div>
      </div>
      {activeCase.steps.length === 0 ? <div className="uisv-inline-empty flex min-h-0 flex-1 items-center justify-center"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="这条用例还没有步骤" /></div> : (
        <div className="uisv-table-wrap min-h-0 flex-1 overflow-auto border-t border-[var(--uisv-eef2f7)]">
          <div className="uisv-table uisv-yaml-table min-w-[620px]">
            <div className="uisv-thead uisv-yaml-grid grid h-9 grid-cols-[34px_78px_minmax(0,1fr)_minmax(0,1.15fr)_78px] items-center gap-[7px] bg-[var(--uisv-f8fafc)] px-[11px] text-[11.5px] font-semibold text-[var(--uisv-7b8799)]"><span>#</span><span>关键字</span><span>步骤</span><span>定位 / 值</span><span>缺口</span></div>
            {activeCase.steps.map(step => {
              const selected = step.orderNo === activeStep?.orderNo
              const gap = step.missing.length > 0
              return <button type="button" key={step.orderNo} className={`uisv-row uisv-yaml-grid grid min-h-[52px] w-full cursor-pointer grid-cols-[34px_78px_minmax(0,1fr)_minmax(0,1.15fr)_78px] items-center gap-[7px] border-0 border-t border-[var(--uisv-f3f6fa)] px-[11px] text-left font-[inherit] text-[13px] text-[var(--uisv-334155)] ${selected ? 'selected bg-[var(--uisv-eff6ff)] shadow-[inset_3px_0_0_var(--uisv-2563eb)]' : gap ? 'gap bg-[var(--uisv-fffdf8)] shadow-[inset_3px_0_0_var(--uisv-f59e0b)]' : 'bg-[var(--uisv-fff)] hover:bg-[var(--uisv-fbfdff)]'}`} onClick={() => setStepNo(step.orderNo)}>
              <span className="uisv-step-no text-[11px] tabular-nums text-[var(--uisv-94a3b8)]">{String(step.orderNo).padStart(2, '0')}</span>
              <span><span className={`uisv-keyword uisv-kw-${keywordClass(step.keyword)} inline-flex h-[21px] items-center justify-center rounded-[4px] px-1.5 font-mono text-[11px] font-semibold whitespace-nowrap ${keywordClass(step.keyword) === 'click' ? 'bg-[var(--uisv-eff6ff)] text-[var(--uisv-1d4ed8)]' : keywordClass(step.keyword).startsWith('assert_visible') || keywordClass(step.keyword).startsWith('assert_hidden') ? 'bg-[var(--uisv-f5f3ff)] text-[var(--uisv-6d28d9)]' : keywordClass(step.keyword) === 'assert_text' ? 'bg-[var(--uisv-ecfeff)] text-[var(--uisv-0e7490)]' : keywordClass(step.keyword) === 'open' ? 'bg-[var(--uisv-f0fdfa)] text-[var(--uisv-0f766e)]' : keywordClass(step.keyword) === 'wait_text' ? 'bg-[var(--uisv-fff8eb)] text-[var(--uisv-b45309)]' : 'bg-[var(--uisv-f1f5f9)] text-[var(--uisv-475569)]'}`}>{step.keyword}</span></span>
              <span className="uisv-step-source line-clamp-2 overflow-hidden text-[12.5px] leading-[1.45] text-[var(--uisv-475569)]">{step.name}</span>
              <span className="uisv-yaml-locator flex min-w-0 items-center gap-1 overflow-hidden [&_.ant-tag]:m-0 [&_.ant-tag]:text-[11.5px] [&_.ant-tag]:leading-[18px] [&_code]:overflow-hidden [&_code]:text-ellipsis [&_code]:whitespace-nowrap [&_code]:text-[11.5px] [&_code]:text-[var(--uisv-64748b)] [&_em]:text-[11.5px] [&_em]:not-italic [&_em]:text-[var(--uisv-94a3b8)]">{step.locatorType ? <><Tag variant="filled">{step.locatorType}</Tag><code title={step.locatorValue}>{step.locatorValue || '—'}</code></> : <em>{step.operationValue || '—'}</em>}</span>
              <span>{step.missing.length ? <span className="uisv-pill amber inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded-[5px] bg-[var(--uisv-fff8eb)] px-[7px] text-[11.5px] font-semibold text-[var(--uisv-b45309)]">{step.missing.length} 项待补</span> : <span className="uisv-pill green inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded-[5px] bg-[var(--uisv-f0fdf4)] px-[7px] text-[11.5px] font-semibold text-[var(--uisv-15803d)]">就绪</span>}</span>
            </button>
            })}
          </div>
        </div>
      )}
      <div className="uisv-table-foot flex flex-[0_0_32px] items-center justify-between border-t border-[var(--uisv-eef2f7)] bg-[var(--uisv-fbfcfe)] px-3 text-[11px] text-[var(--uisv-94a3b8)]"><span>步骤 {activeCase.steps.length} 个</span><span>{activeCase.missingSteps ? `${activeCase.missingSteps} 个步骤含缺口` : '没有缺口'}</span></div>
    </main>

    <aside className="uisv-pane uisv-inspector flex min-h-0 flex-col overflow-hidden rounded-[10px] border border-[var(--uisv-e3eaf3)] bg-[var(--uisv-fff)] max-[1200.01px]:hidden">
      {activeStep ? <MissingInspector step={activeStep} /> : <div className="uisv-inline-empty flex min-h-0 flex-1 items-center justify-center"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择步骤查看缺口" /></div>}
    </aside>
  </div>
}
