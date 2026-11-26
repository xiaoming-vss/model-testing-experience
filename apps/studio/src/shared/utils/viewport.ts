/** 工作台侧栏在窄视口切换为浮层；与样式中的 1180px 断点保持一致。 */
const RAIL_OVERLAY_QUERY = '(max-width: 1180px)'

export function isRailOverlayViewport() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(RAIL_OVERLAY_QUERY).matches
}
