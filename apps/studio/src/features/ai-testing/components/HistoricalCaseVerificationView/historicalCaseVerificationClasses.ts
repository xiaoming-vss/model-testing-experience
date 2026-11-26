import { cx } from '@/shared/utils/cx'
import type { DecisionTone } from '../../utils/historicalCaseVerificationView'
import { IMPACT, TONE_COLOR, TONE_PILL } from '../HistoricalRelationView/historicalRelationClasses'
import { CATEGORY_PILL } from '../TestScopeAnalysisView/testScopeClasses'

/** 判定标签沿用历史需求关联的语义色；「不受影响」没有语义色，只保留中性底。 */
export const DECISION_PILL: Record<DecisionTone, string> = { ...TONE_PILL, plain: '' }
export const DOT: Record<DecisionTone, string> = { ...TONE_COLOR, plain: 'bg-app-surface-text-muted' }
export const PILL_INFO = cx(CATEGORY_PILL, TONE_PILL.info)

/* 行内批注：被引用的前置条件或步骤铺对应状态的浅底，左侧压 3px 强调条。 */
export const FLAG_BG: Record<DecisionTone, string> = {
  ok: 'bg-[var(--app-status-approved-bg)]',
  info: 'bg-app-accent-surface',
  warn: 'bg-app-status-warning-bg',
  review: 'bg-[var(--app-status-review-bg)]',
  danger: 'bg-app-danger-surface-soft',
  plain: 'bg-app-surface-hover',
}
export const FLAG_BAR: Record<DecisionTone, string> = {
  ok: 'shadow-[inset_3px_0_0_var(--app-status-approved-text)]',
  info: 'shadow-[inset_3px_0_0_var(--app-accent)]',
  warn: 'shadow-[inset_3px_0_0_var(--app-status-warning-text)]',
  review: 'shadow-[inset_3px_0_0_var(--app-status-review-text)]',
  danger: 'shadow-[inset_3px_0_0_var(--app-request-error-text)]',
  plain: 'shadow-[inset_3px_0_0_var(--app-surface-text-muted)]',
}
/** 批注卡与结论卡左侧的强调边。 */
export const EDGE: Record<DecisionTone, string> = {
  ok: 'border-l-[var(--app-status-approved-text)]',
  info: 'border-l-[var(--app-accent)]',
  warn: 'border-l-[var(--app-status-warning-text)]',
  review: 'border-l-[var(--app-status-review-text)]',
  danger: 'border-l-[var(--app-request-error-text)]',
  plain: 'border-l-[var(--app-surface-border)]',
}

/* 导航：「待确认」在本阶段用评审紫，区别于琥珀色的「需修改」。 */
export const CAT_ROW_ATTENTION_REVIEW = 'border-y-[var(--app-status-review-border)] border-r-[var(--app-status-review-border)] border-l-[var(--app-status-review-text)] bg-[var(--app-status-review-bg)]'
export const CATEGORY_TEXT_ATTENTION = 'text-[var(--app-status-review-text)]'
export const CATEGORY_TEXT_SELECTED = 'text-app-accent'
export const CATEGORY_ICON = 'shrink-0 text-[14px]'
export const CATEGORY_ROW_IDLE = 'border-y-transparent border-r-transparent border-l-transparent bg-transparent hover:border-y-app-surface-border hover:border-r-app-surface-border hover:bg-app-surface'
export const FILTER_CHIP_IDLE = 'bg-transparent text-app-surface-text hover:border-app-surface-border hover:bg-app-surface-hover'
export const FILTER_COUNT = 'font-mono text-[10px] font-medium'
export const LIST_EMPTY = 'm-0 px-2 py-6 text-center text-[11px] leading-[1.5] text-app-surface-text-muted'

/* 用例结论卡 */
export const CASE_ID = 'max-w-[240px] truncate rounded-[4px] border border-app-surface-border bg-app-surface-hover px-1.5 py-0.5 font-mono text-[11px] font-semibold leading-[1.3] text-app-list-name'
export const FINDING = IMPACT
export const FINDING_OPEN = 'mt-3 rounded-[12px] border border-app-accent-border bg-app-surface px-4 py-3.5 first:mt-0'
export const FINDING_HEAD = 'flex flex-wrap items-center gap-x-2.5 gap-y-1.5'
export const FINDING_TITLE = 'm-0 mt-1.5 mb-2.5 text-[14px] font-semibold leading-[1.5] text-app-surface-text'
export const FINDING_META = 'text-[11.5px] text-app-surface-text-muted'
export const FINDING_TOGGLE = 'ml-auto inline-flex shrink-0 cursor-pointer items-center gap-1 whitespace-nowrap border-0 bg-transparent p-0 text-[12px] font-medium text-app-accent hover:underline disabled:cursor-not-allowed disabled:text-app-surface-text-muted disabled:no-underline'
export const KV = 'm-0 grid grid-cols-[56px_minmax(0,1fr)] gap-x-3 gap-y-2'
export const KV_LABEL = 'pt-[3px] text-[11px] text-app-surface-text-muted'
export const KV_VALUE = 'min-w-0 text-[13px] leading-[1.7] [overflow-wrap:anywhere]'
export const EVIDENCE_LINES = 'flex flex-col gap-1.5'
export const EVIDENCE_LINE = 'flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-[8px] border border-app-surface-border bg-app-surface-hover px-2.5 py-[7px]'
export const EVIDENCE_KIND = 'flex-none rounded-[4px] border border-app-surface-border bg-app-surface px-1.5 font-mono text-[11px] font-semibold leading-[1.5] text-app-surface-text-muted'
export const EVIDENCE_TEXT = 'text-[12.5px] leading-[1.65] [overflow-wrap:anywhere]'
export const EVIDENCE_ARROW = 'mx-1.5 font-semibold not-italic text-app-accent'
export const HINT = 'flex items-baseline gap-2 rounded-[8px] border border-app-accent-border bg-app-accent-surface px-2.5 py-2 text-[12.5px] leading-[1.65]'
export const HINT_LABEL = 'flex-none text-[11px] font-semibold text-app-accent'
export const SUPPLEMENTAL_POINT = IMPACT
export const JUMP_LINK = 'ml-auto inline-flex shrink-0 cursor-pointer items-center gap-1 whitespace-nowrap border-0 bg-transparent p-0 text-[12px] font-medium text-app-accent hover:underline'

/* 行内批注 */
export const OTHER_RULES = 'mt-3 flex flex-wrap items-center gap-x-2.5 gap-y-1.5 rounded-[8px] border border-app-surface-border bg-app-surface-hover px-2.5 py-2 text-[11.5px] text-app-surface-text-muted'
export const OTHER_RULE = 'inline-flex flex-wrap items-center gap-1.5 text-app-surface-text'
export const DOC_HEAD = 'mb-2 mt-3.5 flex flex-wrap items-center gap-2 first:mt-0'
export const DOC_HEAD_TITLE = 'm-0 text-[12px] font-semibold text-app-surface-text'
export const DOC_HEAD_NOTE = 'text-[11px] text-app-surface-text-muted'
export const DOC_LIST = 'm-0 list-none overflow-hidden rounded-[10px] border border-app-surface-border'
export const DOC_ITEM = 'grid grid-cols-[44px_minmax(0,1fr)] border-t border-[var(--app-surface-divider)] first:border-t-0'
export const DOC_NO = 'pt-2.5 pl-3.5 font-mono text-[11px] font-semibold leading-[1.7] text-app-surface-text-muted'
export const DOC_TEXT = 'py-2.5 pr-3.5 text-[13px] leading-[1.7] [overflow-wrap:anywhere]'
export const DOC_EMPTY = 'px-3.5 py-2.5 text-[12.5px] text-app-surface-text-muted'
export const DOC_NOTES = 'col-span-full flex flex-col gap-2 px-3.5 pb-3'
export const DOC_TABLE = 'w-full table-fixed border-separate border-spacing-0 overflow-hidden rounded-[10px] border border-app-surface-border text-left'
export const DOC_TABLE_HEAD = 'h-[38px] bg-[var(--srf-list-header-bg)] px-3.5 text-[11px] font-semibold text-app-surface-text-muted'
export const DOC_CELL = 'border-t border-[var(--app-surface-divider)] px-3.5 py-2.5 align-top text-[13px] leading-[1.7] [overflow-wrap:anywhere]'
export const DOC_NO_CELL = 'border-t border-[var(--app-surface-divider)] px-3.5 py-2.5 align-top font-mono text-[11px] font-semibold leading-[1.7] text-app-surface-text-muted'
export const DOC_EMPTY_CELL = 'border-t border-[var(--app-surface-divider)]'
export const DOC_NOTE_CELL = 'border-t border-[var(--app-surface-divider)] px-3.5 pb-3 align-top'
export const ANNOTATION = 'flex flex-col gap-1.5 rounded-[8px] border border-l-[3px] border-app-surface-border bg-app-surface px-3 py-2.5'
export const ANNOTATION_HEAD = 'flex flex-wrap items-center gap-1.5'
export const ANNOTATION_NOTE = 'text-[11px] text-app-surface-text-muted'
export const ANNOTATION_TEXT = 'm-0 text-[12.5px] leading-[1.65] [overflow-wrap:anywhere]'

/* 用例档案顶部的结论卡 */
export const VERDICTS = 'mt-4 flex flex-col gap-2'
export const VERDICT = 'rounded-[10px] border border-app-surface-border border-l-[3px] bg-app-surface px-3 py-2.5'
export const VERDICT_TAGS = 'flex flex-wrap items-center gap-1.5'
export const VERDICT_RULE = 'text-[11.5px] text-app-surface-text-muted'
/* 提示条：整条边框色各写一份完整类名，避免两个同优先级的边框色互相覆盖。 */
export const NOTE_REVIEW = 'flex items-start gap-2 rounded-[10px] border border-l-[3px] border-[var(--app-status-review-border)] bg-[var(--app-status-review-bg)] px-3 py-2.5 text-[12px] leading-[1.6]'
export const NOTE_INFO = 'flex items-start gap-2 rounded-[10px] border border-app-accent-border bg-app-accent-surface px-3 py-2.5 text-[12px] leading-[1.6]'
