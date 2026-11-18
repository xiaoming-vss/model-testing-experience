import type { Entity } from '../../visualizationTypes'
import { cx } from '@/shared/utils/cx'

import { formatConstraint } from '../../utils/visualizationFormat'
import {
  vizEntityClass,
  vizEntityRelatedClass,
  vizEntityTitleClass,
  vizMeasureClass,
  vizUnknownClass,
} from './visualizationClasses'

type Props = { entity?: Entity; active: boolean; className?: string }
export function DiagramEntity({ entity, active, className }: Props) {
  if (!entity) return <span className={vizUnknownClass}>原文未明确</span>
  return (
    <div className={cx(vizEntityClass, active && vizEntityRelatedClass, className)} title={entity.label}>
      <strong className={vizEntityTitleClass}>{entity.label}</strong>
      {entity.range && <span>{entity.range.startInclusive === true ? '[' : entity.range.startInclusive === false ? '(' : '?'}{entity.range.start ?? '未知'}, {entity.range.end ?? '未知'}{entity.range.endInclusive === true ? ']' : entity.range.endInclusive === false ? ')' : '?'} {entity.range.unit}{entity.range.timeBase ? ` · ${entity.range.timeBase}` : ''}</span>}
      {entity.durationConstraint && <span className={vizMeasureClass}>时长 {formatConstraint(entity.durationConstraint)}</span>}
      {entity.countConstraint && <span className={vizMeasureClass}>数量 {formatConstraint(entity.countConstraint)}</span>}
    </div>
  )
}
