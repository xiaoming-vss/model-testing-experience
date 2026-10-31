const INTERACTIVE_CARD_SELECTOR = 'a, button, input, textarea, select, [role="button"], [role="menuitem"], [role="combobox"]'

export function isInteractiveCardTarget(target: EventTarget | null) {
  return target instanceof Element && Boolean(target.closest(INTERACTIVE_CARD_SELECTOR))
}
