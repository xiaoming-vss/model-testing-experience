import { create } from 'zustand'

export const SIDEBAR_COLLAPSED_KEY = 'mtx-sidebar-collapsed'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1'
  } catch {
    return false
  }
}

type SidebarState = {
  collapsed: boolean
  toggleCollapsed: () => void
}

export const useSidebarStore = create<SidebarState>((set, get) => ({
  collapsed: readCollapsed(),
  toggleCollapsed: () => {
    const collapsed = !get().collapsed
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0')
    } catch {
      // Storage may be disabled; the current tab can still toggle.
    }
    set({ collapsed })
  },
}))
