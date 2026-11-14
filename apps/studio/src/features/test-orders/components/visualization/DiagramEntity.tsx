import type { Entity } from '../../visualizationTypes'

import { formatConstraint } from '../../utils/visualizationFormat'

type Props = { entity?: Entity; active: boolean }
export function DiagramEntity({ entity, active }: Props) {
  if (!entity) return <span className="test-order-viz-unknown">原文未明确</span>
  return <div className={`test-order-viz-entity${active ? ' is-related' : ''}`} title={entity.label}>
    <strong>{entity.label}</strong>
    {entity.range && <span>{entity.range.startInclusive === true ? '[' : entity.range.startInclusive === false ? '(' : '?'}{entity.range.start ?? '未知'}, {entity.range.end ?? '未知'}{entity.range.endInclusive === true ? ']' : entity.range.endInclusive === false ? ')' : '?'} {entity.range.unit}{entity.range.timeBase ? ` · ${entity.range.timeBase}` : ''}</span>}
    {entity.durationConstraint && <span className="test-order-viz-measure">时长 {formatConstraint(entity.durationConstraint)}</span>}
    {entity.countConstraint && <span className="test-order-viz-measure">数量 {formatConstraint(entity.countConstraint)}</span>}
  </div>
}
