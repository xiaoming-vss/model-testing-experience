/**
 * UI 阶段可视化的 Tailwind 类串。
 *
 * 原 ui-stage-visual.module.css 的浅色规则按元素拆到这里；深色覆盖仍留在 CSS Module，
 * 因为 `:root[data-theme="dark"]` 需要成组维护。语义类名保留给深色规则与测试钩子。
 */

export const uisvPillClass = 'uisv-pill inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded-[5px] px-[7px] text-[11.5px] font-semibold'
export const uisvPillGreenClass = 'green bg-[var(--uisv-f0fdf4)] text-[var(--uisv-15803d)]'
export const uisvPillAmberClass = 'amber bg-[var(--uisv-fff8eb)] text-[var(--uisv-b45309)]'
export const uisvPillSlateClass = 'slate bg-[var(--uisv-f1f5f9)] text-[var(--uisv-475569)]'
export const uisvPillCompactClass = 'h-[19px] text-[10.5px]'

export const uisvInspectorScrollClass = 'uisv-inspector-scroll min-h-0 flex-1 overflow-auto p-3'
export const uisvInspectorHeadClass = 'uisv-inspector-head flex items-center gap-[7px] border-b border-[var(--uisv-eef2f7)] pb-2 [&_.ant-tag]:m-0 [&_.ant-tag]:text-[11px]'
export const uisvInspectorHeadCompactClass = 'compact items-start'
export const uisvInspectorHeadBodyClass = 'min-w-0 flex-1'
export const uisvInspectorHeadTitleClass = 'm-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13.5px] font-bold text-[var(--uisv-0f172a)]'
export const uisvInspectorHeadCodeClass = 'mt-0.5 block overflow-hidden text-ellipsis whitespace-nowrap text-[11px] text-[var(--uisv-94a3b8)]'

export const uisvInspectorSectionClass = 'uisv-inspector-section mt-2.5'
export const uisvInspectorSectionTitleClass = 'm-0 mb-[5px] flex items-center gap-[5px] text-[12px] font-bold text-[var(--uisv-475569)]'
export const uisvInspectorSectionCountClass = 'inline-flex h-[15px] min-w-[15px] items-center justify-center rounded-[4px] bg-[var(--uisv-eff6ff)] px-[3px] text-[10px] text-[var(--uisv-1d4ed8)]'
export const uisvInspectorParagraphClass = 'my-[3px] text-[12px] leading-[1.6] text-[var(--uisv-64748b)]'
export const uisvInspectorCodeClass = 'text-[11px] text-[var(--uisv-334155)]'
export const uisvBlockquoteClass = 'm-0 rounded-r-[6px] border-l-2 border-[var(--uisv-bfdbfe)] bg-[var(--uisv-f8fafc)] px-2 py-[7px] text-[12px] leading-[1.6] text-[var(--uisv-475569)]'

export const uisvNoteBoxClass = 'uisv-note-box mb-[5px] flex gap-1.5 rounded-[6px] px-2 py-[7px] text-[11.5px] leading-[1.6]'
export const uisvNoteBoxAmberClass = 'amber border border-[var(--uisv-fde8c3)] bg-[var(--uisv-fffaf0)] text-[var(--uisv-92400e)]'
export const uisvNoteBoxGreenClass = 'green border border-[var(--uisv-dcfce7)] bg-[var(--uisv-f7fdf9)] text-[var(--uisv-166534)]'
export const uisvNoteBoxIconClass = '[&_.anticon]:mt-px [&_.anticon]:flex-none'

export const uisvLocatorBoxClass = 'uisv-locator-box mb-1.5 rounded-[6px] border border-[var(--uisv-e5ecf5)] bg-[var(--uisv-f8fafc)] p-[7px]'
export const uisvLocatorCodeClass = 'block overflow-hidden text-ellipsis whitespace-nowrap text-[11.5px] text-[var(--uisv-334155)]'
export const uisvLocatorRowClass = 'mt-[5px] flex items-center gap-1'
export const uisvLocatorMetaClass = 'm-0 text-[11.5px] leading-[1.55] text-[var(--uisv-94a3b8)]'

export const uisvInteractionBoxClass = 'uisv-interaction-box mb-[5px] flex flex-col gap-px rounded-[6px] border border-[var(--uisv-e0e7ff)] bg-[var(--uisv-f8faff)] px-[7px] py-1.5'
export const uisvInteractionStrongClass = 'text-[11.5px] text-[var(--uisv-3730a3)]'
export const uisvInteractionSpanClass = 'text-[11.5px] leading-[1.45] text-[var(--uisv-64748b)]'
export const uisvInspectorNoteClass = 'uisv-inspector-note mt-2.5 rounded-[6px] bg-[var(--uisv-f0f7ff)] p-2 text-[11.5px] leading-[1.6] text-[var(--uisv-3b6ea5)]'

export const uisvStepBadgeClass = 'uisv-step-badge inline-flex h-[30px] w-[30px] flex-[0_0_30px] items-center justify-center rounded-[8px] bg-[var(--uisv-eff6ff)] text-[10.5px] font-bold text-[var(--uisv-1d4ed8)]'
export const uisvStepBadgeAmberClass = 'amber bg-[var(--uisv-fff8eb)] text-[var(--uisv-b45309)]'

export const uisvTraceItemClass = 'uisv-trace-item mb-[5px] flex items-start gap-[5px] rounded-[6px] border border-[var(--uisv-eef2f7)] bg-[var(--uisv-fcfdff)] p-1.5'
export const uisvTraceItemExcludedClass = 'excluded border-[var(--uisv-fde8c3)] bg-[var(--uisv-fffaf0)]'
export const uisvTraceIndexClass = 'uisv-trace-index inline-flex h-[18px] w-[18px] flex-[0_0_18px] items-center justify-center rounded-[4px] bg-[var(--uisv-eff6ff)] text-[9px] font-bold text-[var(--uisv-1d4ed8)]'
export const uisvTraceIndexAssertClass = 'assert bg-[var(--uisv-ecfeff)] text-[var(--uisv-0e7490)]'

export const uisvValueGridClass = 'uisv-value-grid mt-1.5 flex flex-wrap gap-[5px]'
export const uisvValueGridItemClass = 'flex flex-col gap-px rounded-[5px] bg-[var(--uisv-f8fafc)] px-1.5 py-[5px]'
export const uisvValueGridLabelClass = 'text-[10.5px] not-italic text-[var(--uisv-94a3b8)]'
export const uisvValueGridCodeClass = 'text-[11.5px] text-[var(--uisv-334155)]'

export const uisvMissingBoxClass = 'uisv-missing-box mb-1.5 rounded-[6px] border border-[var(--uisv-fde8c3)] bg-[var(--uisv-fffaf0)] p-[7px]'
export const uisvMissingHeadClass = 'uisv-missing-head flex flex-wrap items-center gap-[3px]'
export const uisvMissingHeadCodeClass = 'inline-flex h-5 items-center rounded-[4px] bg-[var(--uisv-fef3c7)] px-1 text-[11.5px] text-[var(--uisv-92400e)]'
export const uisvMissingHeadStrongClass = 'text-[11.5px] text-[var(--uisv-78350f)]'
export const uisvMissingParagraphClass = 'my-[5px] text-[11.5px] leading-[1.6] text-[var(--uisv-a16207)]'
export const uisvMissingValueClass = 'uisv-missing-value flex items-center gap-[5px] rounded-[4px] bg-[var(--uisv-fff)] px-[5px] py-1'
export const uisvMissingValueTextClass = 'text-[11.5px] text-[var(--uisv-94a3b8)]'
export const uisvMissingValueCodeClass = 'overflow-hidden text-ellipsis whitespace-nowrap text-[11.5px] text-[var(--uisv-475569)]'
export const uisvFixListClass = 'uisv-fix-list m-0 ml-3.5 list-decimal p-0 text-[11.5px] leading-[1.65] text-[var(--uisv-64748b)]'
