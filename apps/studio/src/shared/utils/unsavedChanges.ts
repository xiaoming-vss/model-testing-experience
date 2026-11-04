/** Ask active editors whether a programmatic page navigation may proceed. */
export const UNSAVED_NAVIGATION_EVENT = 'mtx:before-navigation'

export function canNavigateAway(): boolean {
  return window.dispatchEvent(new Event(UNSAVED_NAVIGATION_EVENT, { cancelable: true }))
}
