import { cx } from '@/shared/utils/cx'
import type { HistoricalTone } from '../../utils/historicalRelationView'
import { CATEGORY_PILL } from '../TestScopeAnalysisView/testScopeClasses'
import { TONE_PILL } from './historicalRelationClasses'

/** 历史需求产物的枚举标签；tone 为 plain 时只有中性底。 */
export function HistoricalTag({ value }: { value: { label: string; tone: HistoricalTone | 'plain' } }) {
  return <span className={cx(CATEGORY_PILL, value.tone === 'plain' ? null : TONE_PILL[value.tone])}>{value.label}</span>
}
