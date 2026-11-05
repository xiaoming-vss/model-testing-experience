import { createContext, useContext } from 'react'

/**
 * 面板可见性：标签页把隐藏的面板留在树上以保留筛选和滚动位置，
 * 但隐藏期间不应该继续轮询。默认 true，未包在 Provider 里的页面行为不变。
 */
export const PaneActiveContext = createContext(true)

export function usePaneActive() {
  return useContext(PaneActiveContext)
}
