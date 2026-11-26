import type { HistoricalTone } from '../../utils/historicalRelationView'
import {
  CATEGORY_DOT_TONE,
  CATEGORY_PILL_TONE,
  EVIDENCE_HEAD_BUTTON,
  STATUS_BAR_TONE,
  STATUS_PILL_TONE,
} from '../TestScopeAnalysisView/testScopeClasses'

/** 与测试范围分析共用语义色：沿用／充分＝绿，补充＝蓝，变更／待确认＝琥珀，替代＝紫，取消／冲突＝红。 */
export const TONE_PILL: Record<HistoricalTone, string> = {
  ok: STATUS_PILL_TONE.ok,
  info: STATUS_PILL_TONE.info,
  warn: STATUS_PILL_TONE.warn,
  review: CATEGORY_PILL_TONE.purple,
  danger: CATEGORY_PILL_TONE.red,
}
export const TONE_COLOR: Record<HistoricalTone, string> = {
  ok: STATUS_BAR_TONE.ok,
  info: STATUS_BAR_TONE.info,
  warn: STATUS_BAR_TONE.warn,
  review: CATEGORY_DOT_TONE.purple,
  danger: CATEGORY_DOT_TONE.red,
}

/* 导航栏：与测试范围导航同一套皮肤。 */
export const SPLIT_ROOT = 'flex h-full min-h-0 overflow-hidden bg-app-surface text-app-surface-text max-narrow:flex-col max-narrow:overflow-y-auto'
export const CATEGORY_ICON = 'shrink-0 text-[14px]'
export const CATEGORY_ROW_IDLE = 'border-y-transparent border-r-transparent border-l-transparent bg-transparent hover:border-y-app-surface-border hover:border-r-app-surface-border hover:bg-app-surface'
export const CATEGORY_TEXT_SELECTED = 'text-app-accent'
export const CATEGORY_TEXT_ATTENTION = 'text-app-status-warning-text'
export const FILTER_CHIP_IDLE = 'bg-transparent text-app-surface-text hover:border-app-surface-border hover:bg-app-surface-hover'
export const FILTER_COUNT = 'font-mono text-[10px] font-medium'
export const FOOTER_READONLY = 'ml-auto inline-flex items-center gap-1'
export const LIST_EMPTY = 'm-0 px-2 py-6 text-center text-[11px] leading-[1.5] text-app-surface-text-muted'

/* 档案详情：历史规则与本次规则并排对照。 */
const COMPARE_PANE = 'min-w-0 px-3.5 py-3 max-narrow-sm:[&+&]:border-t max-narrow-sm:[&+&]:border-app-surface-border'
export const COMPARE = 'mt-2.5 grid grid-cols-2 overflow-hidden rounded-[10px] border border-app-surface-border max-narrow-sm:grid-cols-1'
export const COMPARE_PREVIOUS = `${COMPARE_PANE} bg-app-surface-hover`
export const COMPARE_CURRENT = `${COMPARE_PANE} border-l border-app-surface-border bg-app-accent-surface max-narrow-sm:border-l-0`
export const COMPARE_HEAD = 'm-0 mb-1.5 text-[11px] font-semibold text-app-surface-text-muted'
export const COMPARE_HEAD_CURRENT = 'm-0 mb-1.5 text-[11px] font-semibold text-app-accent'
export const COMPARE_TEXT = 'm-0 text-[13px] leading-[1.75] [overflow-wrap:anywhere]'

export const SCOPE_STRIP = 'mt-3 grid grid-cols-3 border-y border-[var(--app-surface-divider)] max-narrow-sm:grid-cols-1 max-narrow-sm:divide-y max-narrow-sm:divide-[var(--app-surface-divider)]'
export const SCOPE_CELL = 'min-w-0 py-2.5 pr-3 [&+&]:border-l [&+&]:border-[var(--app-surface-divider)] [&+&]:pl-3 max-narrow-sm:[&+&]:border-l-0 max-narrow-sm:[&+&]:pl-0'
export const SCOPE_LABEL = 'mb-1 text-[11px] text-app-surface-text-muted'
export const SCOPE_VALUE = 'm-0 text-[12.5px] leading-[1.65] [overflow-wrap:anywhere]'

export const IMPACT = 'border-t border-[var(--app-surface-divider)] py-4 first:border-t-0 first:pt-0'
export const IMPACT_TAGS = 'flex flex-wrap items-center gap-1.5'
export const IMPACT_SUMMARY = 'mt-2 max-w-[72ch] text-[13px] font-medium leading-[1.65] text-app-surface-text'
export const ID_CHIP_CLIP = 'max-w-[260px] truncate'

export const EVIDENCE_TOGGLE = `${EVIDENCE_HEAD_BUTTON} list-none text-app-accent [&::-webkit-details-marker]:hidden`
export const EVIDENCE_CHEVRON = 'ml-auto shrink-0 text-[10px] text-app-surface-text-muted transition-transform group-open:rotate-90'
export const EVIDENCE_ROWS = 'border-t border-app-surface-border'
export const EVIDENCE_ROW = 'grid grid-cols-[56px_minmax(0,1fr)] gap-3 border-b border-app-surface-border px-3 py-2.5 last:border-b-0'
export const EVIDENCE_SIDE = 'pt-0.5 text-[11px] font-semibold text-app-surface-text-muted'
export const EVIDENCE_LOC = 'flex flex-wrap items-center gap-1.5 text-[11px] text-app-surface-text-muted'
export const EVIDENCE_TEXT = 'mt-1 text-[13px] leading-[1.7] [overflow-wrap:anywhere]'

export const NOTE_ICON = 'mt-0.5 shrink-0 text-app-status-warning-text'
export const JUMP_LINK = 'ml-auto shrink-0 border-0 bg-transparent p-0 text-[12px] font-medium text-app-accent hover:underline'
export const KNOWN_LIST = 'flex flex-col gap-2'
export const KNOWN_ITEM = 'flex flex-wrap items-center gap-2'
