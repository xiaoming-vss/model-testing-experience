/**
 * 共享列表表面的 Tailwind 类串。
 *
 * 这些表面原先由 legacy-surface.css / base-services-connection.module.css 提供；
 * 迁入 utility 后集中在这里，避免基础服务、性能监控与 AI Skill 库各写一份。
 * 颜色只消费 --app-glass-* 与 --srf-* 角色 token。
 */

export const serviceCardShellClass = 'flex min-h-0 flex-1 flex-col gap-0'

export const serviceCardScrollClass = 'flex min-h-0 flex-1 flex-col px-[18px] py-4'

export const serviceCardLoadingClass = 'grid min-h-[220px] place-items-center'

export const serviceCardEmptyClass =
  'flex min-h-[260px] flex-1 items-center justify-center rounded-[16px] border border-[var(--app-glass-request-shadow-selected)] bg-[var(--app-glass-surface-72)] p-6 shadow-[inset_0_1px_0_var(--app-glass-highlight-86),0_10px_24px_var(--app-glass-shadow-card)] backdrop-blur-[24px] backdrop-saturate-[1.8]'

export const serviceCardGridClass =
  'grid w-full flex-none content-start items-stretch grid-cols-[repeat(auto-fill,minmax(310px,1fr))] [grid-auto-rows:auto] gap-[18px] max-[1880.01px]:grid-cols-5 max-[1560.01px]:grid-cols-4 max-[1220.01px]:grid-cols-3 max-[980.01px]:grid-cols-2 max-[680.01px]:grid-cols-1'

export const serviceCardClass =
  'h-full min-h-[172px] min-w-0 rounded-[14px] border border-[var(--app-glass-border-68)] bg-[var(--app-glass-surface-72)] shadow-[inset_0_1px_0_var(--app-glass-highlight-86),0_10px_24px_var(--app-glass-shadow-card)] backdrop-blur-[24px] backdrop-saturate-[1.8] transition hover:-translate-y-0.5 hover:border-[var(--app-glass-action-border)] hover:bg-[var(--app-glass-surface-82)] hover:shadow-[inset_0_1px_0_var(--app-glass-highlight-90),0_14px_30px_var(--app-glass-shadow-floating)]'

export const serviceCardBodyClass = 'flex h-auto min-h-[172px] flex-col gap-2.5 p-4'

export const serviceCardHeadClass = 'flex min-h-[22px] flex-nowrap items-start justify-between gap-2.5'

export const serviceCardTitleWrapClass = 'min-w-0 max-w-full flex-1 [&_.ant-space-item]:min-w-0'

export const serviceCardTitleClass =
  'block min-w-0 max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-[14px] font-bold leading-[22px] text-[var(--app-glass-text)]'

export const serviceCardUrlClass =
  'mb-0 line-clamp-2 min-h-8 overflow-hidden break-all text-[12px] leading-4 text-[var(--app-glass-text-description)]'

export const serviceCardMetaClass =
  'flex min-w-0 items-center justify-between gap-4 border-b border-[var(--app-glass-request-shadow)] pb-2.5 max-[900.01px]:flex-col max-[900.01px]:items-start max-[900.01px]:gap-1'

export const serviceCardLabelClass = 'text-[12px] leading-5 text-[var(--app-glass-text-caption)]'

export const serviceCardValueClass = 'text-right text-[12px] font-[650] break-words text-[var(--app-glass-text)]'

export const serviceCardValueInlineClass =
  'min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-right text-[12px] font-[650] text-[var(--app-glass-text)]'

export const serviceCardActionsClass =
  'mt-auto flex min-h-7 items-center justify-end gap-1.5 pt-1 [&_.ant-btn]:h-7 [&_.ant-btn]:w-7 [&_.ant-btn]:min-w-7'

export const entityCardGridClass =
  'grid grid-cols-[repeat(auto-fill,minmax(min(100%,328px),1fr))] content-start gap-4'

/** 列表/抽屉/选择弹窗共用的页脚表面；分页与文案排布由 pagination.css 维护。 */
export const tableFooterClass =
  'box-border flex flex-none flex-wrap items-center justify-between gap-x-4 gap-y-2 min-h-[58px] border-t border-[var(--app-surface-border)] bg-[var(--app-surface)] px-4 py-3'

/** 选择器/小弹窗里的紧凑页脚，保留同一套 flex 与描边，只收尺寸。 */
export const tableFooterCompactClass =
  'box-border flex flex-none flex-wrap items-center justify-between gap-x-4 gap-y-2 min-h-[42px] border-t border-[var(--app-surface-border)] bg-[var(--app-surface)] px-3 py-1.5'

/** 工作台页签容器：撑满剩余高度、纵向排列并承载页面内距。 */
const workbenchTabsBaseClass = 'flex flex-auto min-h-0 flex-col gap-3 overflow-hidden'
export const workbenchTabsClass = `${workbenchTabsBaseClass} px-[var(--app-page-gutter)] pt-3.5 pb-5`
/** Sprint 看板沿用 12px 全向内距。 */
export const workbenchTabsCompactClass = `${workbenchTabsBaseClass} p-3`
/** AI Skill 库沿用 12px 上、16px 下的内距。 */
export const workbenchTabsAiClass = `${workbenchTabsBaseClass} px-[var(--app-page-gutter)] pt-3 pb-4`

/** 操作列列头：宽度与按钮组一致并居中，页面对齐方式不另写一串。 */
export const actionsColumnTitleClass = 'tp-actions-col-title inline-block text-center'

/** 列表滚动承载层：滚动与表面色；flex/min-height 由各页面按结构声明。 */
export const tableScrollClass = 'overflow-auto bg-[var(--app-surface)]'

export const entityCardDescClass =
  'line-clamp-2 mb-3 min-h-9 overflow-hidden text-[11.5px] leading-[18px] text-[var(--srf-text-secondary)]'

export const entityCardDescEmptyClass = 'text-[var(--srf-text-muted)] italic'

export const entityCardBadgesClass = 'mb-3 flex flex-wrap items-center gap-1.5'

export const runResultPreClass =
  'block min-h-[180px] w-full max-w-full overflow-hidden whitespace-pre-wrap break-words rounded-[10px] border border-[var(--app-request-field-border)] bg-[var(--app-surface-hover)] px-3.5 py-3 text-[12px] leading-5 text-[var(--app-shell-text)] [overflow-wrap:anywhere]'

export const runResultPreCompactClass = 'min-h-[120px]'

export const runResultSubsectionClass = 'mt-3 min-w-0 flex-none'

export const runResultListClass = 'flex min-w-0 flex-none flex-col gap-2'

export const runResultRowClass =
  'min-w-0 flex-none rounded-[10px] border border-[var(--app-request-field-border)] bg-[var(--app-request-field-bg)] px-3 py-2.5'

export const runResultRowFailedClass = 'border-[var(--app-request-error-border)]'

export const runResultRowTitleClass = 'mb-1.5 flex min-w-0 flex-wrap items-center gap-2'

export const runResultRowMetaClass =
  'flex min-w-0 flex-wrap gap-x-3 gap-y-2 text-[12px] leading-[18px] text-[var(--app-control-text)]'

export const runResultMetaItemClass =
  'inline-flex max-w-full min-w-0 items-start gap-1.5 [&>strong]:flex-none [&>strong]:text-[12px] [&>strong]:font-semibold [&>strong]:leading-[18px] [&>strong]:text-[var(--app-surface-chip-text)] [&>span:last-child]:min-w-0 [&>span:last-child]:max-w-full [&>span:last-child]:[overflow-wrap:anywhere]'

export const runHistoryLayoutClass = 'flex flex-col gap-2.5'

export const runHistoryListClass = 'flex max-h-[min(60vh,720px)] flex-col gap-2.5 overflow-auto'

export const runHistoryMoreClass = 'flex justify-center px-0 pb-2 pt-1'

export const runHistoryItemClass =
  'flex w-full cursor-pointer items-start justify-between gap-3.5 rounded-[14px] border border-[var(--app-request-card-border)] bg-[var(--app-surface)] px-4 py-3.5 text-left transition-[border-color,box-shadow,background] duration-200 enabled:hover:border-[var(--app-request-card-border-hover)] enabled:hover:shadow-[0_8px_20px_var(--app-request-card-shadow-hover)] disabled:cursor-wait disabled:opacity-80 max-[900.01px]:flex-col max-[900.01px]:items-start'

export const runHistoryItemMainClass = 'flex min-w-0 flex-col gap-2'

export const runHistoryItemSideClass = 'flex flex-none flex-col items-end gap-2 max-[900.01px]:items-start'

export const runHistoryItemTitleClass = 'flex min-w-0 flex-wrap items-center gap-2'

export const runHistoryItemMetaClass = 'flex flex-wrap gap-x-3.5 gap-y-2 text-[12px] leading-[18px] text-[var(--app-control-text)]'

export const runHistoryItemErrorClass = 'text-[12px] leading-[18px] text-[var(--app-request-error-text)]'

export const runHistoryItemIdClass = 'text-[12px] leading-[18px] text-[var(--app-request-text-muted)]'

export const runHistoryItemLinkClass = 'text-[12px] leading-[18px] text-[var(--app-accent)]'

/** 运行详情/记录页顶栏容器：标题、状态与操作分布两端。 */
export const runDetailToolbarClass =
  'tp-list-toolbar flex flex-wrap items-center justify-between gap-3 px-4 py-3'

/** 运行 ID、脚本摘要等需要断行的等宽标识。 */
export const runIdMonoClass = 'break-all font-mono text-[11px]'

/** 列表中的单行运行 ID/标识，超出省略。 */
export const runIdLineClass = 'truncate font-mono text-[11px] text-app-surface-text-muted'

/** 指标卡标签与脚注。 */
export const statCardLabelClass = 'text-xs text-app-surface-text-muted'
export const statCardNoteClass = 'mt-0.5 text-[11px] text-app-surface-text-muted'

export const runResultBlockClass =
  'mt-2.5 flex min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-y-auto overflow-x-hidden pr-1'

export const runResultAlertClass = 'mb-3.5'

export const runReportLayoutClass = 'flex h-full max-h-full min-h-0 flex-1 flex-col overflow-hidden'

export const runReportStaticClass =
  'flex flex-none flex-col gap-3.5 rounded-[12px] bg-[var(--app-surface)] px-3 pb-3.5 pt-2 shadow-[0_10px_20px_-20px_var(--app-request-sticky-shadow)]'

export const runReportScrollClass =
  'block max-h-[clamp(240px,calc(100vh-430px),620px)] min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain pr-0.5'

export const runReportHeadClass = 'flex items-start justify-between gap-3 max-[900.01px]:flex-col max-[900.01px]:items-start'

export const runReportHeadMainClass = 'flex min-w-0 flex-col gap-2'

export const runReportHeadActionsClass = 'flex flex-none items-center gap-2'

export const runReportTitleClass = 'flex items-center gap-2.5'

export const runReportMetaClass = 'flex flex-wrap gap-x-4 gap-y-2 text-[12px] leading-[18px] text-[var(--app-control-text)]'

export const runReportSummaryGridClass =
  'grid grid-cols-[repeat(5,minmax(84px,0.9fr))_minmax(220px,1.8fr)] gap-2.5 max-[900.01px]:grid-cols-2'

export const runReportSummaryItemClass =
  'flex min-w-0 flex-col gap-0.5 rounded-[10px] border border-[var(--app-request-card-border)] bg-[var(--app-surface)] px-2.5 py-2 last:min-w-[220px] [&>span]:text-[10px] [&>span]:leading-[14px] [&>span]:text-[var(--app-shell-text-muted)] [&>strong]:min-w-0 [&>strong]:text-[14px] [&>strong]:leading-[18px] [&>strong]:break-words [&:last-child>strong]:overflow-hidden [&:last-child>strong]:text-ellipsis [&:last-child>strong]:whitespace-nowrap [&:last-child>strong]:break-normal'

export const runReportSummarySuccessClass = 'border-[var(--app-request-result-success-border)]'
export const runReportSummaryFailedClass = 'border-[var(--app-request-result-failed-border)]'
export const runReportSummaryErrorClass = 'border-[var(--app-request-result-warning-border)]'
export const runReportSummarySkippedClass = 'border-[var(--app-frame-border-strong)]'

export const runReportContentClass = 'flex min-h-0 flex-col gap-2.5'
export const runReportContentInnerClass = 'h-auto min-h-0 flex-none pr-0'
export const runReportListClass = 'flex min-h-0 flex-col gap-2.5'

export const runReportItemClass =
  'overflow-hidden rounded-[14px] border border-[var(--app-request-card-border)] bg-[var(--app-surface)] [&.expanded]:border-[var(--app-request-result-border-hover)]'

export const runReportItemHeadClass =
  'flex w-full cursor-pointer items-center justify-between gap-3 border-0 bg-transparent px-4 py-3.5 text-left max-[900.01px]:flex-col max-[900.01px]:items-start'

export const runReportItemTitleClass =
  'flex min-w-0 flex-wrap items-center gap-2 [&>strong]:min-w-0 [&>strong]:overflow-hidden [&>strong]:text-ellipsis [&>strong]:whitespace-nowrap'

export const runReportItemOrderClass =
  'flex-none rounded-full bg-[var(--app-accent-soft)] px-2 py-0.5 text-[12px] leading-[18px] text-[var(--app-accent)]'

export const runReportItemMetaClass =
  'flex flex-none flex-wrap items-center justify-end gap-x-3.5 gap-y-2 text-[12px] leading-[18px] text-[var(--app-shell-text-muted)] max-[900.01px]:flex-col max-[900.01px]:items-start'

export const runReportItemArrowClass = 'transition-transform duration-200 [&.expanded]:rotate-180'

export const runReportItemBodyClass =
  'flex flex-col gap-3 border-t border-[var(--app-request-result-divider)] px-4 pb-4'

export const runReportInlineMetaClass = 'flex flex-wrap gap-x-4 gap-y-2 pt-3.5 text-[12px] leading-[18px] text-[var(--app-control-text)]'

export const runReportListMoreClass = 'flex justify-center px-0 pb-2 pt-1'
