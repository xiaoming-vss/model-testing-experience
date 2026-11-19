import { describe, expect, it } from 'vitest'
import { compareByOrderNo, orderNoOrMax } from './order'

describe('orderNo sorting', () => {
  it('sorts explicit values before missing order numbers', () => {
    const items = [{ orderNo: 2 }, {}, { orderNo: 1 }, { orderNo: null }]

    expect(items.sort(compareByOrderNo)).toEqual([
      { orderNo: 1 },
      { orderNo: 2 },
      {},
      { orderNo: null },
    ])
  })

  it('keeps missing values at the end', () => {
    expect(orderNoOrMax(undefined)).toBe(Number.MAX_SAFE_INTEGER)
    expect(orderNoOrMax(null)).toBe(Number.MAX_SAFE_INTEGER)
    expect(orderNoOrMax(0)).toBe(0)
  })
})
