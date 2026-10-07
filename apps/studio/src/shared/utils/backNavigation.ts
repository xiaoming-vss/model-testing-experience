import type { NavigateFunction } from 'react-router-dom'

type RouterHistoryState = { idx?: number } | null

/**
 * 平台统一的返回逻辑：有应用内历史时回退到上一页，上级列表的状态（Tab、类型、搜索词）
 * 都保存在 URL 里，回退即完整恢复；没有应用内历史（直接打开链接或刷新进入）时，
 * 回退到指定的默认列表页。
 */
export function goBackOrFallback(navigate: NavigateFunction, fallbackUrl: string) {
  const entryIndex = (window.history.state as RouterHistoryState)?.idx
  if (typeof entryIndex === 'number' && entryIndex > 0) {
    navigate(-1)
  } else {
    navigate(fallbackUrl)
  }
}
