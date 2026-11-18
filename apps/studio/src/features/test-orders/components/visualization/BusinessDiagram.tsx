import { ArrowRightOutlined, CheckOutlined, ScissorOutlined, StopOutlined } from '@ant-design/icons'
import { cx } from '@/shared/utils/cx'
import type { Visual, Visualization } from '../../visualizationTypes'
import { DiagramEntity } from './DiagramEntity'
import { formatConstraint } from '../../utils/visualizationFormat'
import { DiagramRelations } from './DiagramRelations'
import {
  vizBlockClass,
  vizBlockCurrentClass,
  vizBlockDividerClass,
  vizBlockLastClass,
  vizCaptionClass,
  vizDiagramsClass,
  vizFocusClass,
  vizFocusParagraphClass,
  vizFocusTitleClass,
  vizFocusTitleCurrentClass,
  vizIntervalClass,
  vizIntervalEntityClass,
  vizIntervalItemClass,
  vizIntervalRemoveClass,
  vizMappedArrowClass,
  vizMappedClass,
  vizMappedEntityClass,
  vizMappedItemClass,
  vizOptionClass,
  vizOptionEntityClass,
  vizOptionOwnerClass,
  vizOptionOwnerEntityClass,
  vizOptionsClass,
  vizOutputClass,
  vizQuantityClass,
  vizQuantityEntityClass,
  vizSegmentRoleClass,
  vizStateClass,
  vizStateColumnClass,
  vizStateLabelClass,
  vizTotalClass,
  vizTotalMetaClass,
  vizTrackScrollClass,
  vizTransitionClass,
  vizTransitionIconClass,
} from './visualizationClasses'

type Props = { artifact: Visualization; step: number }

export function BusinessDiagram({ artifact, step }: Props) {
  const entities = new Map(artifact.entities.map(entity => [entity.id, entity]))
  const activeSources = new Set(artifact.sources.filter(source => source.field !== 'precondition' && source.index === step).map(source => source.id))
  const relates = (ids: string[]) => ids.some(id => activeSources.has(id))
  const score = (visual: Visual) => artifact.assertions.some(a => visual.assertionIds.includes(a.id) && relates(a.sourceIds)) ? 2 : relates(visual.sourceIds) ? 1 : 0
  const firstStep = (visual: Visual) => Math.min(...artifact.sources.filter(source => source.field !== 'precondition' && visual.sourceIds.includes(source.id)).map(source => source.index), Infinity)
  const orderedVisuals = [...artifact.visuals].sort((a, b) => firstStep(a) - firstStep(b))
  function entityView(id: string | null, className?: string) {
    const entity = id ? entities.get(id) : undefined
    return <DiagramEntity key={id} entity={entity} active={Boolean(entity && relates(entity.sourceIds))} className={className} />
  }
  function relations(visual: Visual) {
    return artifact.relations.filter(r => visual.relationIds.includes(r.id))
  }
  function intervalMapping(visual: Visual) {
    if (visual.kind !== 'interval') return []
    const output = visual.data.distinctOutputEntityIds
    const edges = relations(visual).filter(r => r.kind === 'produces' && r.polarity === 'positive' && !r.condition && visual.data.orderedSegments.some(s => s.role === 'keep' && s.entityId === r.from) && output.includes(r.to))
    return output.length && edges.length === output.length && new Set(edges.map(r => r.from)).size === edges.length && new Set(edges.map(r => r.to)).size === edges.length ? edges : []
  }
  function body(visual: Visual) {
    switch (visual.kind) {
      case 'options': return <>
        <div className={vizOptionOwnerClass}>{entityView(visual.data.ownerEntityId, vizOptionOwnerEntityClass)}<span>{visual.data.availability === 'allowed' ? '允许选择' : visual.data.availability === 'forbidden' ? '禁止选择' : '可选规则未明确'}</span></div>
        <div className={cx(vizOptionsClass, `tone-${visual.data.availability === 'forbidden' ? 'red' : 'blue'}`)}>{visual.data.optionEntityIds.map(id => <div className={vizOptionClass} key={id}>{visual.data.availability === 'allowed' ? <CheckOutlined aria-hidden="true" /> : visual.data.availability === 'forbidden' ? <StopOutlined aria-hidden="true" /> : null}{entityView(id, vizOptionEntityClass)}</div>)}</div>
        <p className={vizCaptionClass}>{visual.data.completeness === 'exhaustive' ? '仅限以上选项' : visual.data.completeness === 'examples' ? '以上仅为原文示例，不代表全部选项' : '是否穷尽未明确'}</p>
      </>
      case 'interval': return <>
        <div className={vizTrackScrollClass}><ol className={vizIntervalClass} aria-label="保留与剔除区间">{visual.data.orderedSegments.map(segment => <li key={segment.entityId} className={cx(vizIntervalItemClass, segment.role === 'remove' && vizIntervalRemoveClass, `tone-${segment.role === 'keep' ? 'blue' : segment.role === 'remove' ? 'red' : 'slate'}`)}>
          <span className={vizSegmentRoleClass}>{segment.role === 'remove' && <ScissorOutlined aria-hidden="true" />}{segment.role === 'keep' ? '保留' : segment.role === 'remove' ? '剔除' : '角色未明确'}</span>{entityView(segment.entityId, vizIntervalEntityClass)}
        </li>)}</ol></div>
        <p className={vizCaptionClass}>按原文顺序排列 · 区间宽度不表示实际时长</p>
        {intervalMapping(visual).length > 0 ? <div className={vizTrackScrollClass}><div className={vizMappedClass} style={{ gridTemplateColumns: `repeat(${visual.data.orderedSegments.length}, minmax(105px, 1fr))` }}>
          {visual.data.orderedSegments.map(segment => { const edge = intervalMapping(visual).find(r => r.from === segment.entityId); return <div key={segment.entityId} className={vizMappedItemClass}>{edge && <><ArrowRightOutlined className={vizMappedArrowClass} aria-label="产生" />{entityView(edge.to, vizMappedEntityClass)}</>}</div> })}
        </div></div> : visual.data.distinctOutputEntityIds.length > 0 && <div className={vizOutputClass}><h4>分别形成独立产物</h4><div className={vizOptionsClass}>{visual.data.distinctOutputEntityIds.map(id => entityView(id))}</div></div>}
      </>
      case 'state': return <>
        <div className={vizOptionOwnerClass}><span>执行操作</span>{entityView(visual.data.actionEntityId)}</div>
        <div className={vizStateClass}><div className={vizStateColumnClass}><span className={vizStateLabelClass}>操作前</span>{entityView(visual.data.beforeEntityId)}</div>
          <div className={vizTransitionClass}><ArrowRightOutlined className={vizTransitionIconClass} aria-hidden="true" /><span>{visual.data.change === 'unchanged' ? '状态保持' : visual.data.change === 'changed' ? '预期变化' : '变化未明确'}</span></div>
          <div className={vizStateColumnClass}><span className={vizStateLabelClass}>操作后（预期）</span>{entityView(visual.data.afterEntityId)}</div></div>
      </>
      case 'quantity': {
        const mapped = new Set(relations(visual).flatMap(r => [r.from, r.to]))
        const sources = visual.data.sourceEntityIds.filter(id => !mapped.has(id))
        const outputs = visual.data.outputEntityIds.filter(id => !mapped.has(id))
        return <>
          <div className={vizTotalClass}><strong>{visual.data.totalConstraint ? `预期总量 ${formatConstraint(visual.data.totalConstraint)}` : '总量未明确'}</strong><span className={vizTotalMetaClass}>{visual.data.ownership === 'distinct' ? '各自独立，不合并' : visual.data.ownership === 'shared' ? '共同归属同一产物' : '归属关系未明确'}</span></div>
          {(sources.length > 0 || outputs.length > 0) && <div className={vizQuantityClass}><div className="min-w-0"><h4>来源</h4>{sources.map(id => entityView(id, vizQuantityEntityClass))}</div><div className="min-w-0"><h4>预期产物</h4>{outputs.map(id => entityView(id, vizQuantityEntityClass))}</div></div>}
        </>
      }
    }
  }
  function renderVisual(visual: Visual, index: number, total: number) {
    // Positive, unconditional adjacent sequence edges are already drawn by the strip.
    const edges = relations(visual).filter(r => !intervalMapping(visual).includes(r) && !(visual.kind === 'interval' && r.kind === 'sequence' && r.polarity === 'positive' && !r.condition && visual.data.orderedSegments.some((s, i, list) => s.entityId === r.from && list[i + 1]?.entityId === r.to)))
    const current = score(visual) > 0
    return <section className={cx(vizBlockClass, current && vizBlockCurrentClass, index > 0 && vizBlockDividerClass, index === total - 1 && vizBlockLastClass)} key={visual.id} aria-label={visual.title}>
      <h4 className={cx(vizFocusTitleClass, current && vizFocusTitleCurrentClass)}>{visual.title}</h4>
      {visual.assertionIds.length > 0 && <div className={vizFocusClass}>{visual.assertionIds.map(id => {
        const assertion = artifact.assertions.find(item => item.id === id)
        return assertion ? <p className={vizFocusParagraphClass} key={id}>{assertion.text}</p> : null
      })}</div>}
      {body(visual)}
      {edges.length > 0 && <DiagramRelations relations={edges} entityView={entityView} />}
      {visual.notes.map((note, index) => <p key={index}>操作中的检查要求：{note.text}</p>)}
    </section>
  }
  return <section className={vizDiagramsClass} aria-label="验证焦点">
    <h3>验证焦点</h3>
    {artifact.visuals.length ? orderedVisuals.map((visual, index) => renderVisual(visual, index, orderedVisuals.length)) : <p className={vizCaptionClass}>暂无可靠图解，请按操作与预期执行。</p>}
  </section>
}
