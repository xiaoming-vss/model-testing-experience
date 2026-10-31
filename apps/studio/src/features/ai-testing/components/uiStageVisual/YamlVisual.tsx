import { useMemo, useState } from 'react'
import '../../styles/ui-yaml-issues.css'
import { Alert, Empty, Progress, Tag } from 'antd'
import {
  CheckCircleFilled,
  ExclamationCircleFilled,
} from '@ant-design/icons'
import { parseYaml, type YamlMissing, type YamlStep } from './uiStageVisualUtils'
import { VisualEmpty, VisualParseError } from './VisualStates'

function keywordClass(keyword: string): string {
  if (['click', 'assert_visible', 'assert_hidden', 'assert_text', 'open', 'wait_text', 'input'].includes(keyword)) return keyword
  return 'other'
}

function MissingInspector({ step }: { step: YamlStep }) {
  return <div className="uisv-inspector-scroll">
    <div className="uisv-inspector-head compact">
      <span className="uisv-step-badge amber">S{step.orderNo}</span>
      <div><h3>{step.name}</h3><code>orderNo {step.orderNo} · {step.keyword}</code></div>
      {step.missing.length ? <Tag variant="filled" color="warning">{step.missing.length} 项待补</Tag> : <Tag variant="filled" color="green">就绪</Tag>}
    </div>
    <section><h4>当前步骤</h4><p>{step.locatorValue || step.operationValue || '没有额外定位或值。'}</p><div className="uisv-value-grid">{step.locatorType ? <span><em>定位类型</em><code>{step.locatorType}</code></span> : null}{step.operationValue ? <span><em>操作值</em><code>{step.operationValue}</code></span> : null}</div></section>
    <section><h4>需要补齐的字段 <span>{step.missing.length}</span></h4>
      {step.missing.length ? step.missing.map((missing: YamlMissing, index) => <div className="uisv-missing-box" key={`${missing.target}-${index}`}>
        <div className="uisv-missing-head">{missing.fields.map(field => <code key={field}>{field}</code>)}<strong>{missing.target || missing.operation || '未命名缺口'}</strong></div>
        <p>{missing.reason}</p>
        {missing.value ? <div className="uisv-missing-value"><span>当前值</span><code>{missing.value}</code></div> : null}
      </div>) : <div className="uisv-note-box green"><CheckCircleFilled /><span>这个步骤没有声明字段缺口；仍需核对测试数据、设计冲突与定位正确性。</span></div>}
    </section>
    <section><h4>如何补齐</h4><ol className="uisv-fix-list"><li>优先补行级定位：按业务主键定位行，再定位行内单元格或控件。</li><li>页面地址和期望文本属于测试数据，可以按环境批量填写。</li><li>补齐后切换回 YAML 修改原文，或继续使用当前原文编辑。</li></ol></section>
    <div className="uisv-inspector-note"><ExclamationCircleFilled /> 当前步骤来自真实 YAML 产物；可视化视图只读，修改请切换到 YAML。</div>
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

  return <div className="uisv uisv-yaml">
    <aside className="uisv-pane uisv-nav">
      <div className="uisv-pane-head"><span>UI 用例</span><em>{parsed.cases.length}</em></div>
      <div className="uisv-case-list">
        {parsed.cases.map((candidate, index) => {
          const candidateReady = candidate.steps.length - candidate.missingSteps
          return <button type="button" key={`${candidate.name}-${index}`} className={`uisv-case-item${index === caseIndex ? ' active' : ''}`} onClick={() => { setCaseIndex(index); setStepNo(0) }}>
            <span className={`uisv-case-dot ${candidate.missingSteps || candidate.completionIssues.length ? 'amber' : 'green'}`} />
            <span className="uisv-case-copy"><strong title={candidate.name}>{candidate.name}</strong><small>{candidateReady}/{candidate.steps.length} 步字段完整</small></span>
            <span className={`uisv-missing-count${candidate.missingSteps ? '' : ' ready'}`}>{candidate.missingSteps || candidate.completionIssues.length || '✓'}</span>
          </button>
        })}
      </div>
      <div className="uisv-nav-foot"><div className="uisv-nav-foot-title">缺口总览</div><div className="uisv-nav-stats"><strong>{totalSteps}</strong><span>步骤</span><strong>{totalMissing}</strong><span>待补</span></div><div className="uisv-cover-note">{parsed.cases.length} 条用例 · {totalMissing || parsed.cases.some(candidate => candidate.completionIssues.length) ? '仍有待处理内容' : '未声明缺口，需人工审核'}</div></div>
    </aside>

    <main className="uisv-pane uisv-main">
      <div className="uisv-main-head">
        <div><h3>{activeCase.name}</h3><p>{activeCase.steps.length} 个步骤 · {ready} 个字段完整 · {activeCase.missingSteps} 个含缺口</p></div>
        <div className="uisv-head-tags"><Tag variant="filled" color={activeCase.enabled ? 'green' : 'default'}>{activeCase.enabled ? '启用' : '停用'}</Tag><Tag variant="filled" color={activeCase.missingSteps ? 'warning' : 'green'}>{activeCase.missingSteps ? `${activeCase.missingSteps} 步待补` : activeCase.completionIssues.length ? '有待处理内容' : '字段完整'}</Tag></div>
      </div>
      {activeCase.completionIssues.length ? <Alert className="ui-yaml-issues" type="warning" showIcon title="此用例仍有待处理内容"
        description={<details><summary>查看 {activeCase.completionIssues.length} 项待补数据与设计冲突</summary><ul>{activeCase.completionIssues.map((issue, index) => <li key={index}>{issue}</li>)}</ul></details>} /> : null}
      <div className="uisv-readiness-strip">
        <div className="uisv-readiness-copy"><strong>字段完整度 {percent}%</strong><span>{ready} / {activeCase.steps.length} 步</span></div>
        <Progress percent={percent} showInfo={false} strokeColor={activeCase.missingSteps ? 'var(--ant-color-warning)' : 'var(--ant-color-success)'} railColor="var(--ant-color-fill-secondary)" />
        <div className="uisv-readiness-legend"><span><i className="ready" />字段完整 {ready}</span><span><i className="gap" />待补 {activeCase.missingSteps}</span></div>
      </div>
      {activeCase.steps.length === 0 ? <div className="uisv-inline-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="这条用例还没有步骤" /></div> : (
        <div className="uisv-table-wrap">
          <div className="uisv-table uisv-yaml-table">
            <div className="uisv-thead uisv-yaml-grid"><span>#</span><span>关键字</span><span>步骤</span><span>定位 / 值</span><span>缺口</span></div>
            {activeCase.steps.map(step => <button type="button" key={step.orderNo} className={`uisv-row uisv-yaml-grid${step.missing.length ? ' gap' : ''}${step.orderNo === activeStep?.orderNo ? ' selected' : ''}`} onClick={() => setStepNo(step.orderNo)}>
              <span className="uisv-step-no">{String(step.orderNo).padStart(2, '0')}</span>
              <span><span className={`uisv-keyword uisv-kw-${keywordClass(step.keyword)}`}>{step.keyword}</span></span>
              <span className="uisv-step-source">{step.name}</span>
              <span className="uisv-yaml-locator">{step.locatorType ? <><Tag variant="filled">{step.locatorType}</Tag><code title={step.locatorValue}>{step.locatorValue || '—'}</code></> : <em>{step.operationValue || '—'}</em>}</span>
              <span>{step.missing.length ? <span className="uisv-pill amber">{step.missing.length} 项待补</span> : <span className="uisv-pill green">就绪</span>}</span>
            </button>)}
          </div>
        </div>
      )}
      <div className="uisv-table-foot"><span>步骤 {activeCase.steps.length} 个</span><span>{activeCase.missingSteps ? `${activeCase.missingSteps} 个步骤含缺口` : '没有缺口'}</span></div>
    </main>

    <aside className="uisv-pane uisv-inspector">
      {activeStep ? <MissingInspector step={activeStep} /> : <div className="uisv-inline-empty"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择步骤查看缺口" /></div>}
    </aside>
  </div>
}
