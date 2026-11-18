import { ArrowLeftOutlined, ArrowRightOutlined } from '@ant-design/icons'
import { Button, Empty } from 'antd'
import { useEffect, useRef } from 'react'
import { cx } from '@/shared/utils/cx'
import type { TestOrderEntry } from '../../types'
import type { Visualization } from '../../visualizationTypes'
import {
  vizFlowClass,
  vizFlowCountClass,
  vizFlowFooterActionsClass,
  vizFlowFooterClass,
  vizFlowHeaderClass,
  vizFlowSubtitleClass,
  vizFlowTitleClass,
  vizStepArrowClass,
  vizStepButtonActiveClass,
  vizStepButtonClass,
  vizStepItemClass,
  vizStepLabelClass,
  vizStepMetaActiveClass,
  vizStepMetaClass,
  vizStepNumberActiveClass,
  vizStepNumberClass,
  vizStepTopClass,
  vizStepsClass,
} from './visualizationClasses'

type Props = { snapshot: TestOrderEntry['snapshot']; artifact: Visualization; step: number; onStep: (step: number) => void }
export function VisualizationSteps({ snapshot, artifact, step, onStep }: Props) {
  const steps = snapshot?.steps ?? []
  const flow = useRef<HTMLOListElement>(null)
  useEffect(() => {
    const list = flow.current
    const selected = list?.querySelector('[aria-pressed="true"]')
    if (!list || !selected) return
    const bounds = list.getBoundingClientRect()
    const target = selected.getBoundingClientRect()
    if (target.left < bounds.left) list.scrollLeft += target.left - bounds.left - 18
    else if (target.right > bounds.right) list.scrollLeft += target.right - bounds.right + 18
  }, [step])
  function label(index: number) {
    const ids = new Set(artifact.sources.filter(s => s.field === 'action' && s.index === index).map(s => s.id))
    const actions = artifact.entities.filter(e => e.kind === 'action' && e.sourceIds.some(id => ids.has(id)))
    // A single sourced action is a useful short label; otherwise preserve the original action.
    return actions.length === 1 ? actions[0].label : steps[index]?.action || '操作缺失'
  }
  return <section className={vizFlowClass} aria-label="场景流程">
    <header className={vizFlowHeaderClass}><div><h3 className={vizFlowTitleClass}>场景流程</h3><p className={vizFlowSubtitleClass}>选择步骤，联动查看图解、操作与预期</p></div><span className={vizFlowCountClass}>{steps.length} 个步骤</span></header>
    {steps.length ? <ol ref={flow} className={vizStepsClass}>{steps.map((item, index) => <li key={index} className={vizStepItemClass}>
      <button type="button" aria-pressed={step === index} aria-label={`步骤 ${index + 1}：${label(index)}`} title={item.action} onClick={() => onStep(index)} className={cx(vizStepButtonClass, step === index && vizStepButtonActiveClass)}>
        <span className={vizStepTopClass}>步骤 {String(index + 1).padStart(2, '0')}<span className={cx(vizStepNumberClass, step === index && vizStepNumberActiveClass)}>{index + 1}</span></span>
        <strong className={vizStepLabelClass}>{label(index)}</strong><small className={cx(vizStepMetaClass, step === index && vizStepMetaActiveClass)}>{step === index ? '当前步骤' : '查看此步骤'}</small>
      </button>{index < steps.length - 1 && <ArrowRightOutlined className={vizStepArrowClass} aria-hidden="true" />}
    </li>)}</ol> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无步骤，图解仅依据前置条件" />}
    {steps.length > 0 && <footer className={vizFlowFooterClass}><span>阅读位置 {step + 1} / {steps.length}</span><div className={vizFlowFooterActionsClass}><Button size="small" icon={<ArrowLeftOutlined />} disabled={step === 0} onClick={() => onStep(step - 1)}>上一步</Button><Button size="small" disabled={step >= steps.length - 1} onClick={() => onStep(step + 1)}>下一步 <ArrowRightOutlined /></Button></div></footer>}
  </section>
}
