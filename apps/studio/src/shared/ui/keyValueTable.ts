/**
 * 接口参数 / API 用例参数共用的键值表样式。
 * 两个功能页签的结构和皮肤完全一致，集中在这里避免在组件里复制整串 utility。
 */
export const KV_TABLE_WRAP_CLASS =
  'overflow-x-auto rounded-[var(--srf-radius-control)] border border-[var(--srf-card-border)] bg-[var(--srf-card)]'

export const KV_TABLE_CLASS =
  'w-full table-fixed border-separate border-spacing-0 [&_tbody_tr:last-child_td]:border-b-0'

export const KV_HEAD_CELL_CLASS =
  'h-[34px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-left text-[11px] font-semibold text-[var(--srf-list-header-text)]'

export const KV_HEAD_CELL_CENTER_CLASS =
  'h-[34px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5 text-center text-[11px] font-semibold text-[var(--srf-list-header-text)]'

export const KV_HEAD_CELL_ACTION_CLASS =
  'h-[34px] border-b border-[var(--srf-card-border)] bg-[var(--srf-list-header-bg)] px-2 py-1.5'

export const KV_BODY_CELL_CLASS =
  'border-b border-[var(--srf-divider)] px-1.5 py-[5px] align-middle'

export const KV_BODY_CELL_CENTER_CLASS =
  'border-b border-[var(--srf-divider)] px-1.5 py-[5px] text-center align-middle'

export const KV_SECTION_HEAD_CLASS =
  'mb-2 flex min-w-0 flex-wrap items-start justify-between gap-2'

export const KV_SECTION_HINT_CLASS =
  'm-0 mt-0.5 text-[11px] leading-[18px] text-[var(--srf-text-muted)]'

export const KV_SECTION_COUNT_CLASS =
  'flex-none text-[11px] leading-[18px] text-[var(--srf-text-muted)] tabular-nums'

export const KV_EMPTY_CLASS =
  'flex items-center gap-2.5 rounded-[var(--srf-radius-control)] border border-dashed border-[var(--srf-card-border)] bg-[color-mix(in_srgb,var(--srf-hover)_45%,var(--srf-card))] px-3.5 py-4'

export const KV_EMPTY_ICON_CLASS = 'text-[18px] text-[var(--srf-text-muted)]'

export const KV_EMPTY_TEXT_CLASS = 'flex min-w-0 flex-col gap-px'

export const KV_EMPTY_TITLE_CLASS = 'text-[12px] font-semibold text-[var(--srf-text)]'

export const KV_EMPTY_HINT_CLASS = 'text-[11px] leading-[18px] text-[var(--srf-text-muted)]'
