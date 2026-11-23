/** 接口配置提取的语义色与布局类；颜色只消费已登记的 AI/应用 token。 */

import { METHOD_BASE, methodTone, SMALL_SECONDARY_TEXT, STRONG_TEXT } from '../ApiDesignDiagramView/apiDesignClasses'

export { METHOD_BASE, methodTone, SMALL_SECONDARY_TEXT, STRONG_TEXT }

export const VIEW_GRID = 'grid grid-cols-[264px_minmax(0,1fr)] items-start gap-5 max-[1200px]:grid-cols-1 max-[1200px]:gap-3'

export const RAIL_ASIDE = 'sticky top-0 z-[2] min-w-0 self-start border-r border-[var(--app-frame-divider-soft)] pr-4 max-h-[calc(100dvh-180px)] overflow-y-auto max-[1200px]:static max-[1200px]:max-h-none max-[1200px]:overflow-visible max-[1200px]:border-r-0 max-[1200px]:border-b max-[1200px]:border-[var(--app-frame-divider-soft)] max-[1200px]:pb-4'
export const OVERVIEW_CARD = 'mt-3 rounded-[9px] border border-[var(--app-surface-border)] bg-[var(--app-surface-hover)] p-3'
export const STAT_GRID = 'mt-2 grid grid-cols-2 overflow-hidden rounded-[7px] border border-[var(--app-surface-border)] bg-[var(--app-surface-border)]'
export const STAT_CELL = 'flex flex-col gap-0.5 bg-[var(--app-surface-hover)] px-2.5 py-2'
export const RAIL_ITEM_BASE = 'grid w-full grid-cols-[46px_minmax(0,1fr)_auto] items-center gap-2 rounded-[7px] border px-2 py-2 text-left transition-colors max-[1200px]:w-[240px] max-[1200px]:flex-none'
export const RAIL_ITEM_SELECTED = 'border-[var(--app-accent-border)] bg-[var(--app-accent-selection)]'
export const RAIL_ITEM_IDLE = 'border-transparent hover:bg-[var(--app-surface-hover)]'
export const RAIL_BADGE = 'inline-flex h-3.5 w-3.5 items-center justify-center rounded-[3px] text-[10px]'
export const RAIL_BADGE_AUTH = 'bg-[var(--app-accent-surface)] text-[var(--app-accent)]'
export const RAIL_BADGE_KEY = 'bg-[var(--app-testing-success-tag-bg)] text-[var(--app-testing-success-tag-text)]'

export const DETAIL_PANEL = 'min-w-0'
export const DETAIL_HEAD = 'border-b border-[var(--app-frame-divider-soft)] pb-4'
export const TITLE_ROW = 'flex flex-wrap items-center gap-2.5'
export const DETAIL_TITLE = 'm-0 min-w-0 text-[18px] font-semibold leading-tight text-[var(--ai-text)] [overflow-wrap:anywhere]'
export const ORDER_TEXT = 'font-mono text-[10px] text-[var(--ai-text-muted)]'
export const META_ROW = 'mt-2.5 flex flex-wrap items-center gap-2.5 text-[11.5px] text-[var(--ai-text-secondary)]'
export const META_SEP = 'h-3 w-px bg-[var(--app-surface-border)]'
export const DETAIL_FOOT = 'flex items-center gap-1.5 pt-4 text-[10.5px] text-[var(--ai-text-muted)]'
export const COPY_BUTTON = 'inline-flex h-7 w-7 flex-none items-center justify-center rounded-[6px] border-0 bg-transparent text-[var(--ai-text-muted)] hover:bg-[var(--app-surface-hover)] hover:text-[var(--ai-text)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--app-review-focus-ring)]'
export const PATH_CODE = 'inline-block max-w-full rounded-[6px] border border-[var(--app-surface-border)] bg-[var(--app-glass-surface-68)] px-2 py-1 font-mono text-[11.5px] text-[var(--ai-text-secondary)] [overflow-wrap:anywhere]'
export const PATH_VARIABLE = 'text-[var(--app-status-review-text)]'

export const SIGNAL_GRID = 'grid grid-cols-[minmax(0,0.9fr)_minmax(0,1.3fr)_minmax(0,0.8fr)] border-y border-[var(--app-frame-divider-soft)] py-2.5 max-narrow:grid-cols-1 max-narrow:py-0'
export const SIGNAL_ITEM = 'flex min-w-0 flex-col gap-1.5 px-4 first:pl-0 last:pr-0 border-[var(--app-frame-divider-soft)] [&+&]:border-l max-narrow:py-2.5 max-narrow:first:pt-3 max-narrow:last:pb-3 max-narrow:[&+&]:border-l-0 max-narrow:[&+&]:border-t'
export const SIGNAL_LABEL = 'text-[9.5px] font-semibold tracking-[0.05em] text-[var(--ai-text-muted)]'
export const SIGNAL_VALUE = 'flex min-h-[17px] min-w-0 flex-wrap items-center gap-1.5 text-[11.5px] text-[var(--ai-text-secondary)]'

export const CHIP_BASE = 'inline-flex items-center gap-1 rounded-full border px-1.5 text-[10px] leading-[17px]'
const KEY_TONE = 'border-[var(--app-status-approved-border)] bg-[var(--app-testing-success-tag-bg)] font-mono text-[var(--app-testing-success-tag-text)]'
export const VAR_CHIP = `${CHIP_BASE} whitespace-nowrap border-[var(--app-status-review-border)] bg-[var(--app-status-review-bg)] font-mono text-[var(--app-status-review-text)]`
export const AUTH_CHIP = `${CHIP_BASE} whitespace-nowrap border-[var(--app-accent-border)] bg-[var(--app-accent-surface)] text-[var(--app-accent)]`
export const KEY_CHIP = `${CHIP_BASE} whitespace-nowrap ${KEY_TONE}`
export const KEY_CHIP_BUTTON = `${CHIP_BASE} max-w-full cursor-pointer whitespace-normal text-left ${KEY_TONE} hover:border-[var(--app-status-approved-text)] hover:bg-[var(--app-status-approved-bg)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--app-review-focus-ring)]`
export const KEY_NOTE = 'text-[10.5px] text-[var(--ai-text-muted)]'
export const SIGNAL_EMPTY = 'text-[11px] text-[var(--ai-text-secondary)]'

export const SECTION = 'border-b border-[var(--app-frame-divider-soft)] pb-4 pt-5 last:border-b-0'
export const SECTION_HEAD = 'flex flex-wrap items-baseline gap-2 pb-2.5'
export const SECTION_TITLE = 'm-0 text-[14px] font-semibold text-[var(--ai-text)]'
export const SECTION_COUNT = 'inline-flex items-center rounded-full border border-[var(--app-surface-border)] bg-[var(--app-surface)] px-1.5 font-mono text-[9.5px] leading-4 text-[var(--ai-text-secondary)]'
export const SECTION_DESC = 'text-[11px] text-[var(--ai-text-muted)] max-[640px]:hidden'
export const SECTION_KEY = 'ml-auto inline-flex items-center gap-1 text-[10.5px] text-[var(--app-testing-success-tag-text)]'
export const GROUP_HEAD = 'flex items-center gap-1.5 pb-1.5'
export const GROUP_TITLE = 'm-0 text-[12px] font-semibold text-[var(--ai-text-secondary)]'
export const GROUP_COUNT = 'inline-flex min-w-4 items-center justify-center rounded-full border border-[var(--app-surface-border)] bg-[var(--app-surface)] px-1 font-mono text-[9.5px] leading-4 text-[var(--ai-text-secondary)]'
export const RAW_BODY = 'mt-1 max-h-[220px] overflow-auto whitespace-pre-wrap rounded-[6px] border border-[var(--app-surface-border)] bg-[var(--app-glass-surface-68)] p-2 font-mono text-[11px] leading-[1.6] text-[var(--ai-text-secondary)] [overflow-wrap:anywhere]'

export const REQUEST_GRID: Record<number, string> = {
  1: 'grid grid-cols-1',
  2: 'grid grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] gap-y-4 max-[1060px]:grid-cols-1',
  3: 'grid grid-cols-3 gap-y-4 max-[1180px]:grid-cols-1',
  4: 'grid grid-cols-2 gap-y-4 max-[1060px]:grid-cols-1',
}
const DIVIDER_LEFT = 'border-l border-[var(--app-frame-divider-soft)] pl-5'
const DIVIDER_TOP = 'border-t border-[var(--app-frame-divider-soft)]'
const RESET_LEFT_AT_1060 = 'max-[1060px]:border-l-0 max-[1060px]:pl-0'
const RESET_LEFT_AT_1180 = 'max-[1180px]:border-l-0 max-[1180px]:pl-0'

export function requestGroupLayout(index: number, count: number) {
  if (count <= 1) return ''
  if (count === 2) return index === 1 ? `${DIVIDER_LEFT} ${RESET_LEFT_AT_1060} max-[1060px]:border-t` : ''
  if (count === 3) return index > 0 ? `${DIVIDER_LEFT} ${RESET_LEFT_AT_1180} max-[1180px]:border-t` : ''
  if (index === 1) return `${DIVIDER_LEFT} ${RESET_LEFT_AT_1060} max-[1060px]:border-t`
  if (index === 2) return DIVIDER_TOP
  if (index === 3) return `${DIVIDER_LEFT} ${DIVIDER_TOP} ${RESET_LEFT_AT_1060}`
  return ''
}

export const FIELD_HEAD_BASE = 'grid items-start gap-x-3 border-b border-[var(--app-frame-divider-soft)] px-1 pb-1.5 text-[9.5px] font-semibold tracking-[0.05em] text-[var(--ai-text-muted)] max-[640px]:hidden'
export const FIELD_COLUMNS = 'grid-cols-[minmax(150px,1.1fr)_86px_minmax(0,1.9fr)]'
export const HEADER_COLUMNS = 'grid-cols-[minmax(130px,0.9fr)_minmax(0,1.25fr)_minmax(0,0.85fr)]'
export const FIELD_ROW_BASE = 'grid items-start gap-x-3 border-t border-[var(--app-frame-divider-soft)] px-1 py-2 transition-colors hover:bg-[var(--app-surface-hover)] first:border-t-0 max-[640px]:grid-cols-[minmax(0,max-content)_minmax(0,1fr)] max-[640px]:gap-x-2 max-[640px]:gap-y-1 max-[640px]:py-2.5'
export const FIELD_ROW_KEY = 'bg-[var(--app-status-approved-bg)]'
export const FIELD_NAME = 'flex min-w-0 items-center gap-1.5 max-[640px]:col-span-2'
export const OBJECT_TOGGLE = 'inline-flex min-h-5 min-w-0 items-center gap-1 rounded-[4px] border border-transparent bg-transparent px-0.5 text-left text-[var(--ai-text-muted)] hover:border-[var(--app-surface-border)] hover:bg-[var(--app-surface-hover)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--app-review-focus-ring)]'
export const FIELD_CODE = 'font-mono text-[11.5px] text-[var(--ai-text)] [overflow-wrap:anywhere]'
export const KEY_ICON = 'text-[11px] text-[var(--app-testing-success-tag-text)]'

export const TYPE_CHIP = 'inline-flex max-w-full items-center overflow-hidden whitespace-nowrap rounded-[4px] border border-[var(--app-surface-border)] bg-[var(--app-surface)] px-1.5 font-mono text-[9.5px] leading-[17px] text-[var(--ai-text-secondary)]'
export const VALUE_CHIP = 'inline-flex max-w-full items-center overflow-hidden rounded-[4px] border border-[var(--app-surface-border)] bg-[var(--app-surface)] px-1.5 font-mono text-[9.5px] leading-[17px] text-[var(--ai-text)] [overflow-wrap:anywhere] max-[640px]:whitespace-normal'
export const CONTAINER_CHIP = `${TYPE_CHIP} border-[var(--app-accent-border)] bg-[var(--app-accent-surface)] text-[var(--app-accent)]`
export const FIELD_META = 'flex min-w-0 flex-wrap items-center gap-1.5'
export const FLAG = 'inline-flex items-center gap-1 rounded-[4px] border px-1.5 text-[9.5px] leading-[17px] whitespace-nowrap'
export const REQUIRED_FLAG = `${FLAG} border-[var(--app-status-warning-border)] bg-[var(--app-status-warning-bg)] text-[var(--app-status-warning-text)]`
export const OPTIONAL_FLAG = `${FLAG} border-[var(--app-surface-border)] bg-[var(--app-surface)] text-[var(--ai-text-secondary)]`
export const KEY_FLAG = `${FLAG} border-[var(--app-status-approved-border)] bg-[var(--app-testing-success-tag-bg)] text-[var(--app-testing-success-tag-text)]`
export const CODE_CHIP = 'inline-flex max-w-full flex-wrap items-baseline gap-1 rounded-[4px] border border-[var(--app-surface-border)] bg-[var(--app-surface)] px-1.5 text-[9px] leading-[17px] text-[var(--ai-text-muted)]'
export const CODE_CHIP_CODE = 'min-w-0 text-[9.5px] text-[var(--ai-text-secondary)] [overflow-wrap:anywhere]'
export const FIELD_DESCRIPTION = 'text-[10.5px] leading-[1.55] text-[var(--ai-text-secondary)] [overflow-wrap:anywhere]'
export const FIELD_EMPTY = 'text-[11.5px] text-[var(--ai-text-secondary)]'

export const RULE_GRID = 'mt-6 grid grid-cols-2 gap-x-6 gap-y-5 border-t border-[var(--app-frame-divider-soft)] pt-5 max-narrow:grid-cols-1'
export const RULE_HEAD = 'flex items-center justify-between gap-2 border-b border-[var(--app-frame-divider-soft)] pb-1.5'
export const RULE_ROW = 'flex min-w-0 flex-col gap-0.5 border-t border-[var(--app-frame-divider-soft)] py-2 first:border-t-0'

export function apiConfigFieldId(prefix: string, caseKey: string, section: string, path: string) {
  const safePrefix = prefix.replace(/[^a-zA-Z0-9_-]/g, '')
  return `api-config-field-${safePrefix}-${encodeURIComponent(caseKey)}-${encodeURIComponent(section)}-${encodeURIComponent(path)}`
}
