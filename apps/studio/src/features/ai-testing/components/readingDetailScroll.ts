import { useEffect, useRef } from 'react'

/**
 * 左导航右阅读区共用的滚动行为。宽屏切换条目时阅读区回到顶部，或定位到指向的子条目；
 * 窄屏导航在上、阅读区在下，只在用户主动选中后把阅读区滚入视野。
 * key 变化即视为切换条目；anchor 用 data 属性定位阅读区内的子条目。
 */
export function useReadingDetailScroll(key: string | undefined, anchor?: { attribute: string; value: string } | null) {
  const detailRef = useRef<HTMLDivElement>(null)
  /** 调用方在用户选中列表项时置为 true，供窄屏滚动一次。 */
  const scrollOnSelectionRef = useRef(false)
  const { attribute, value } = anchor ?? {}
  useEffect(() => {
    const detail = detailRef.current
    if (!detail) return
    const target = attribute && value
      ? [...detail.querySelectorAll<HTMLElement>(`[${attribute}]`)].find(node => node.getAttribute(attribute) === value)
      : undefined
    const narrow = typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 900px)').matches
    if (narrow) {
      if (scrollOnSelectionRef.current) detail.scrollIntoView?.({ block: 'start' })
    } else if (target) {
      detail.scrollTop += target.getBoundingClientRect().top - detail.getBoundingClientRect().top - 16
    } else {
      detail.scrollTop = 0
    }
    scrollOnSelectionRef.current = false
  }, [key, attribute, value])
  return { detailRef, scrollOnSelectionRef }
}
