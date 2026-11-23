import type { ScopeCategoryTone, ScopeStatusTone } from '../../utils/testScopeAnalysis'

export const RAIL_PANEL = 'flex h-full min-h-0 w-[328px] flex-none flex-col border-r border-app-surface-border bg-app-surface-hover max-narrow:h-auto max-narrow:w-full max-narrow:border-b max-narrow:border-r-0'
export const RAIL_BODY = 'flex min-h-0 flex-1 flex-col px-3.5 pb-0 pt-[18px] max-narrow:px-[18px] max-narrow-sm:px-[13px]'
export const RAIL_FOOTER = 'flex flex-none flex-wrap items-center gap-x-2 gap-y-1 border-t border-app-surface-border px-4 py-2 text-[11px] text-app-surface-text-muted max-narrow:px-[18px]'

export const SCOPE_MATRIX = 'mt-3.5 grid flex-none grid-cols-2 gap-px overflow-hidden rounded-[12px] border border-app-surface-border bg-app-surface-border max-narrow:grid-cols-4 max-narrow-sm:grid-cols-2'
export const SCOPE_CELL = 'flex min-h-[66px] min-w-0 cursor-pointer flex-col gap-2 border-0 bg-app-surface px-2.5 py-2.5 text-left transition-colors hover:bg-app-surface-hover'
export const SCOPE_CELL_SELECTED = 'bg-app-accent-selection ring-1 ring-inset ring-app-accent-border'
export const SCOPE_CELL_ATTENTION = 'bg-app-status-warning-bg ring-1 ring-inset ring-app-status-warning-border'
export const SCOPE_CELL_LABEL = 'min-w-0 truncate text-[11.5px] font-semibold text-app-surface-text'
export const SCOPE_CELL_COUNT = 'ml-auto font-mono text-[15px] leading-none tracking-[-0.02em] text-app-surface-text-muted'
export const SCOPE_BAR = 'flex h-[3px] overflow-hidden rounded-[2px] bg-app-surface-border'
export const SCOPE_BAR_SEGMENT = 'block min-w-[2px]'

export const SEARCH_WRAP = 'relative mt-3 flex-none'
export const SEARCH_INPUT = 'h-[34px] w-full rounded-[8px] border border-app-surface-border bg-app-surface pl-8 pr-9 text-[12px] text-app-surface-text outline-none transition-colors placeholder:text-app-surface-text-muted hover:border-app-accent-border focus:border-app-accent-border focus:ring-2 focus:ring-app-accent-selection'
export const SEARCH_KBD = 'pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded-[4px] border border-app-surface-border bg-app-surface-hover px-1.5 py-0.5 font-mono text-[10px] leading-[1.3] text-app-surface-text-muted'

export const FILTER_GRID = 'mt-2 grid flex-none grid-cols-4 gap-px overflow-hidden rounded-[8px] border border-app-surface-border bg-app-surface-border'
export const FILTER_BUTTON = 'flex min-w-0 cursor-pointer items-center justify-center gap-1 border-0 bg-app-surface px-1 py-1.5 text-[11px] whitespace-nowrap text-app-surface-text-muted transition-colors hover:bg-app-surface-hover hover:text-app-surface-text disabled:cursor-not-allowed disabled:opacity-45'
export const FILTER_BUTTON_SELECTED = 'bg-app-surface-hover text-app-surface-text ring-1 ring-inset ring-app-surface-border'
export const FILTER_SUMMARY = 'mt-2 flex flex-none flex-wrap items-center gap-1.5 rounded-[8px] border border-app-status-warning-border bg-app-status-warning-bg px-2.5 py-2 text-[11px] leading-[1.5] text-app-surface-text'

export const LIST = 'mt-2.5 min-h-0 flex-1 overflow-y-auto pb-3 pr-1 max-narrow:max-h-[360px] max-narrow:flex-none'
export const CLEAR_BUTTON = 'inline-flex h-7 cursor-pointer items-center justify-center rounded-[6px] border border-app-surface-border bg-app-surface px-2.5 text-[11px] text-app-surface-text transition-colors hover:border-app-accent-border hover:bg-app-surface-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-app-accent'
export const LIST_GROUP_TITLE = 'm-0 flex items-center gap-1.5 px-2 pb-1 pt-2.5 text-[11px] font-semibold tracking-[0.03em] text-app-surface-text-muted'
export const LIST_ITEM = 'grid min-h-[36px] w-full cursor-pointer grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-2 rounded-[7px] border-0 bg-transparent px-2 py-1.5 text-left text-app-surface-text transition-colors hover:bg-app-surface focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-app-accent'
export const LIST_ITEM_SELECTED = 'bg-app-accent-selection ring-1 ring-inset ring-app-accent-border'
export const LIST_ID = 'font-mono text-[11px] leading-[1.3] text-app-surface-text-muted'
export const LIST_NAME = 'line-clamp-2 min-w-0 text-[12px] leading-[1.35] text-app-surface-text [overflow-wrap:anywhere]'
export const STATUS_PLAIN = 'inline-flex items-center gap-1 text-[11px] whitespace-nowrap text-app-surface-text-muted'
export const STATUS_DOT = 'size-[5px] shrink-0 rounded-full'

export const DETAIL_SCROLL = 'min-w-0 flex-1 overflow-y-auto bg-app-surface max-narrow:min-h-[420px] max-narrow:flex-none max-narrow:overflow-visible'
export const DETAIL_INNER = 'mx-auto w-full max-w-[1080px] px-10 pb-[72px] pt-8 max-narrow:px-6 max-narrow:pb-14 max-narrow:pt-[26px] max-narrow-sm:px-4 max-narrow-sm:pt-[21px]'
export const DETAIL_TITLE = 'm-0 max-w-[900px] text-[22px] font-semibold leading-[1.3] tracking-[-0.015em] text-app-surface-text [overflow-wrap:anywhere] max-narrow:text-[21px] max-narrow-sm:text-[19px]'
export const META_ROW = 'mt-2.5 flex flex-wrap items-center gap-1.5'
export const CATEGORY_PILL = 'inline-flex h-[22px] items-center rounded-[5px] border px-1.5 text-[11px] font-semibold whitespace-nowrap'
export const ID_CHIP = 'rounded-[4px] border border-app-surface-border bg-app-surface-hover px-1.5 py-0.5 font-mono text-[11px] leading-[1.3] text-app-surface-text-muted'
export const STATUS_PILL = 'inline-flex h-[22px] items-center gap-1 rounded-[5px] border px-1.5 text-[11px] whitespace-nowrap'
export const TYPE_CHIP = 'inline-flex h-[22px] items-center rounded-[5px] border border-app-surface-border px-1.5 text-[11px] whitespace-nowrap text-app-surface-text-muted'
export const ICON_BUTTON = 'inline-flex size-6 cursor-pointer items-center justify-center rounded-[5px] border border-transparent bg-transparent text-app-surface-text-muted transition-colors hover:border-app-surface-border hover:bg-app-surface-hover hover:text-app-surface-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-app-accent'

export const QUESTION_NOTE = 'mt-4 flex items-start gap-2 rounded-[12px] border border-app-status-warning-border bg-app-status-warning-bg px-3 py-2.5 text-[11px] leading-[1.55] text-app-surface-text'
export const JUDGEMENT = 'mt-5 grid grid-cols-[56px_minmax(0,1fr)] gap-3.5 border-t border-app-surface-border pt-4 max-narrow-sm:grid-cols-1 max-narrow-sm:gap-1'
export const JUDGEMENT_LABEL = 'pt-0.5 text-[11px] tracking-[0.03em] text-app-surface-text-muted'
export const JUDGEMENT_TEXT = 'm-0 max-w-[68ch] text-[13px] leading-[1.75] text-app-surface-text'

export const STAT_STRIP = 'mt-4 grid grid-cols-4 border-y border-app-surface-border max-narrow-sm:grid-cols-2'
export const STAT_CELL = 'border-l border-app-surface-border px-3.5 py-3 first:border-l-0 max-narrow-sm:odd:border-l-0 max-narrow-sm:[&:nth-child(n+3)]:border-t'
export const STAT_LABEL = 'block text-[11px] leading-[1.3] text-app-surface-text-muted'
export const STAT_VALUE = 'mt-0.5 block text-[16px] leading-[1.25] font-semibold tracking-[-0.01em] text-app-surface-text'

export const RELATIONS = 'flex flex-col gap-2 pt-3'
export const RELATION_GRID = 'grid grid-cols-[56px_minmax(0,1fr)] items-start gap-3.5 max-narrow-sm:grid-cols-1 max-narrow-sm:gap-1'
export const RELATION_LABEL = 'pt-1 text-[11px] tracking-[0.03em] text-app-surface-text-muted'
export const RELATION_CHIPS = 'flex min-w-0 flex-wrap gap-1.5'
export const REL_CHIP = 'inline-flex h-[26px] max-w-full min-w-0 cursor-pointer items-center gap-1.5 rounded-[6px] border border-app-surface-border bg-app-surface px-2 text-[11px] text-app-surface-text transition-colors hover:border-app-accent-border hover:bg-app-surface-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-app-accent'
export const REL_CHIP_CODE = 'shrink-0 font-mono text-[11px] leading-none text-app-surface-text-muted'
export const REL_CHIP_TITLE = 'min-w-0 truncate'
export const REL_CHIP_ARROW = 'shrink-0 text-app-surface-text-muted'

export const SECTION = 'mt-6 border-t border-app-surface-border pt-5'
export const SECTION_HEAD = 'mb-3 flex flex-wrap items-center gap-2'
export const SECTION_TITLE = 'm-0 text-[14px] font-semibold text-app-surface-text'
export const SECTION_COUNT = 'inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-[4px] border border-app-surface-border bg-app-surface-hover px-1 font-mono text-[11px] leading-none text-app-surface-text-muted'
export const SECTION_NOTE = 'ml-auto inline-flex items-center gap-1 text-[11px] text-app-surface-text-muted'
export const DETAIL_FOOT = 'mt-6 flex items-center gap-1.5 text-[11px] leading-[1.5] text-app-surface-text-muted'

export const EVIDENCE_CARD = 'overflow-hidden rounded-[12px] border border-app-surface-border bg-app-surface [&+&]:mt-2.5'
export const EVIDENCE_DOC = 'flex items-start gap-2 border-b border-app-surface-border bg-app-surface-hover px-3 py-2.5'
export const EVIDENCE_DOC_TITLE = 'min-w-0 flex-1 text-[11px] font-semibold leading-[1.45] text-app-surface-text [overflow-wrap:anywhere]'
export const EVIDENCE_DOC_META = 'mt-0.5 block text-[11px] leading-[1.4] text-app-surface-text-muted'
export const EVIDENCE_INDEX = 'w-7 shrink-0 font-mono text-[11px] leading-[1.2] text-app-surface-text-muted'
export const EVIDENCE_HEAD = 'flex w-full items-center gap-2 px-3 py-2 text-left text-app-surface-text'
export const EVIDENCE_HEAD_BUTTON = `${EVIDENCE_HEAD} cursor-pointer border-0 bg-transparent transition-colors hover:bg-app-surface-hover focus-visible:outline-2 focus-visible:outline-offset-[-3px] focus-visible:outline-app-accent`
export const EVIDENCE_LOCATOR = 'min-w-0 flex-1 text-[11px] leading-[1.45] text-app-surface-text [overflow-wrap:anywhere]'
export const EVIDENCE_KIND = 'inline-flex h-5 shrink-0 items-center rounded-[4px] border border-app-surface-border px-1 text-[11px] leading-none text-app-surface-text-muted'
export const EVIDENCE_SUMMARY = 'shrink-0 text-[11px] leading-none text-app-surface-text-muted'
export const EVIDENCE_BODY = 'px-3 pb-3 pl-[60px] max-narrow-sm:pl-[54px]'
export const EVIDENCE_EMPTY = 'm-0 text-[11px] leading-[1.6] text-app-surface-text-muted'
export const EVIDENCE_ITEM = 'border-t border-app-surface-border first:border-t-0'
export const EVIDENCE_MISSING = 'flex items-center gap-1.5 px-3 pb-3 pl-[60px] text-[11px] text-app-status-warning-text max-narrow-sm:pl-[54px]'

export const CATEGORY_PILL_TONE: Record<ScopeCategoryTone, string> = {
  blue: 'border-app-accent-border bg-app-accent-surface text-app-accent',
  purple: 'border-[var(--app-status-review-border)] bg-[var(--app-status-review-bg)] text-[var(--app-status-review-text)]',
  red: 'border-[var(--app-danger-border)] bg-app-danger-surface-soft text-[var(--app-request-error-text)]',
  amber: 'border-app-status-warning-border bg-app-status-warning-bg text-app-status-warning-text',
}

export const CATEGORY_DOT_TONE: Record<ScopeCategoryTone, string> = {
  blue: 'bg-app-accent',
  purple: 'bg-[var(--app-status-review-text)]',
  red: 'bg-[var(--app-request-error-text)]',
  amber: 'bg-app-status-warning-text',
}

export const STATUS_PILL_TONE: Record<ScopeStatusTone, string> = {
  ok: 'border-[var(--app-status-approved-border)] bg-[var(--app-status-approved-bg)] text-app-status-approved-text',
  info: 'border-app-accent-border bg-app-accent-surface text-app-accent',
  warn: 'border-app-status-warning-border bg-app-status-warning-bg text-app-status-warning-text',
}

export const STATUS_DOT_TONE: Record<ScopeStatusTone, string> = {
  ok: 'bg-app-status-approved-text',
  info: 'bg-app-accent',
  warn: 'bg-app-status-warning-text',
}

export const STATUS_BAR_TONE: Record<ScopeStatusTone, string> = {
  ok: 'bg-app-status-approved-text',
  info: 'bg-app-accent',
  warn: 'bg-app-status-warning-text',
}
