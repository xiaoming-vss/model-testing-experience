import { afterEach, describe, expect, it, vi } from 'vitest'
import { goBackOrFallback } from './backNavigation'
import type { NavigateFunction } from 'react-router-dom'

describe('goBackOrFallback', () => {
  const fallbackUrl = '/ai-testing?tab=tasks'

  function setup(historyIdx: number | undefined) {
    const navigate = vi.fn() as unknown as NavigateFunction
    Object.defineProperty(window, 'history', {
      value: { state: historyIdx === undefined ? null : { idx: historyIdx } },
      writable: true,
      configurable: true,
    })
    return navigate
  }

  afterEach(() => {
    Object.defineProperty(window, 'history', {
      value: { state: null },
      writable: true,
      configurable: true,
    })
  })

  it('有应用内历史时回退上一页', () => {
    const navigate = setup(2)
    goBackOrFallback(navigate, fallbackUrl)
    expect(navigate).toHaveBeenCalledWith(-1)
  })

  it('首个入口（idx=0）时回退到默认列表页', () => {
    const navigate = setup(0)
    goBackOrFallback(navigate, fallbackUrl)
    expect(navigate).toHaveBeenCalledWith(fallbackUrl)
  })

  it('没有路由历史状态（如外部打开）时回退到默认列表页', () => {
    const navigate = setup(undefined)
    goBackOrFallback(navigate, fallbackUrl)
    expect(navigate).toHaveBeenCalledWith(fallbackUrl)
  })
})
