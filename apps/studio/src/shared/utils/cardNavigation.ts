const INTERACTIVE_CARD_SELECTOR = 'a, button, input, textarea, select, [role="button"], [role="menuitem"], [role="combobox"]'

/** 卡片整块可点时，内部交互元素（链接、按钮、输入）不应触发卡片的进入动作。 */
export function isInteractiveCardTarget(target: EventTarget | null) {
  return target instanceof Element && Boolean(target.closest(INTERACTIVE_CARD_SELECTOR))
}
