/**
 * 元素库页面的 utility 串。
 *
 * 这个页面按用例库的版面语法拆分（工具栏条 + 分组卡片 + 列表卡片），
 * 卡片外壳、快速过滤条和导航行在这一处声明，组件里只引用常量，
 * 避免同一串 utility 在多个组件重复（ADR 0004）。
 * 颜色只消费 --srf-* 与 --app-* 角色 token。
 */

export const elementPageClass =
  'workbench-page tp-surface tp-list-surface flex min-h-0 flex-1 flex-col px-[var(--app-page-gutter)] pt-3 pb-4'

export const elementBoardClass = 'tp-board flex min-h-0 flex-1 flex-col'

export const elementLayoutClass =
  'grid min-h-0 flex-1 grid-cols-[var(--app-sidebar-width)_minmax(0,1fr)] gap-3 overflow-hidden max-[1180.01px]:grid-cols-1'

export const elementToolbarGroupClass = 'flex min-w-0 flex-wrap items-center gap-2'

export const elementToolbarActionsClass = 'flex flex-none flex-wrap items-center gap-2'

export const elementCardShellClass =
  'flex min-h-0 flex-col overflow-hidden rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] shadow-[0_1px_2px_var(--srf-shadow-color)]'

export const elementSidebarShellClass = `${elementCardShellClass} max-[1180.01px]:max-h-[420px]`

export const elementSidebarHeadClass = 'flex flex-none items-center gap-1.5 border-b border-[var(--srf-divider)] p-3'

export const elementSidebarTitleClass = 'text-[12px] font-bold leading-[18px] text-[var(--srf-text)]'

export const elementSidebarBodyClass = 'min-h-0 flex-1 overflow-auto px-3 pt-2.5 pb-3'

export const elementNavListClass = 'flex flex-col gap-0.5'

export const elementNavSectionLabelClass =
  'mx-0 mt-2 mb-1 px-2.5 text-[12px] font-semibold text-[var(--srf-text-secondary)]'

export const elementSidebarFootClass =
  'flex flex-none items-center gap-2 border-t border-[var(--srf-divider)] bg-[var(--srf-hover)] px-3 py-2'

export const elementQuickBarClass =
  'tp-quickbar flex flex-none flex-wrap items-center justify-between gap-2 border-b border-[var(--srf-divider)] px-4 py-2.5'

export const elementQuickBarMainClass = 'flex min-w-0 flex-wrap items-center gap-2'

export const elementStatusChipsClass = 'flex flex-wrap items-center gap-1'

export const elementScopeTitleClass =
  'min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-semibold text-[var(--srf-text)]'

export const elementRouteChipClass =
  'flex-none rounded-[4px] border border-[var(--srf-card-border)] bg-[var(--srf-chip)] px-1.5 py-0.5 font-mono text-[12px] leading-[16px] text-[var(--srf-text-secondary)]'

export const elementMetaTextClass = 'text-[12px] text-[var(--srf-text-secondary)]'

export const elementCountStrongClass = 'font-semibold text-[var(--srf-text)]'

export const elementTableScrollClass = 'flex flex-auto min-h-0 flex-col p-4'

export const elementLocatorChipClass =
  'inline-block min-w-[92px] rounded-[4px] border border-[var(--srf-card-border)] bg-[var(--srf-chip)] px-1.5 text-center font-mono text-[12px] font-semibold leading-[18px] text-[var(--srf-text-secondary)]'

export const elementNameButtonClass =
  'min-w-0 cursor-pointer truncate border-0 bg-transparent p-0 text-left text-[13px] leading-[24px] text-[var(--app-list-name)] hover:text-[var(--app-list-name-hover)] hover:underline'

export const elementNameIconClass =
  'flex h-[22px] w-[22px] flex-none items-center justify-center rounded-[6px] bg-[var(--srf-chip)] text-[var(--srf-text-secondary)]'

export const elementNameIconParameterizedClass = 'bg-[var(--srf-accent-soft)] text-[var(--srf-accent)]'
