import { describe, expect, it } from 'vitest'
import { clampPage, pageSlice } from './pagination'

describe('pagination helpers', () => {
  it('clamps pages into the available range', () => {
    expect(clampPage(0, 45, 20)).toBe(1)
    expect(clampPage(3, 45, 20)).toBe(3)
    expect(clampPage(9, 45, 20)).toBe(3)
    expect(clampPage(1, 0, 20)).toBe(1)
  })

  it('slices the clamped page window', () => {
    const items = Array.from({ length: 45 }, (_, index) => index)
    expect(pageSlice(items, 1, 20)).toEqual(items.slice(0, 20))
    expect(pageSlice(items, 9, 20)).toEqual(items.slice(40, 60))
  })
})
