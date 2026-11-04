import { describe, expect, it } from 'vitest'
import { getFlowOrder } from './flowOrder'

describe('getFlowOrder', () => {
  const ids = ['a', 'b', 'c']
  it('uses connections rather than node positions or input order', () => {
    expect(getFlowOrder(ids, [{ source: 'c', target: 'a' }, { source: 'a', target: 'b' }])).toEqual(['c', 'a', 'b'])
  })
  it('rejects disconnected, branching, converging, cyclic and foreign connections', () => {
    expect(getFlowOrder(ids, [{ source: 'a', target: 'b' }])).toBeNull()
    expect(getFlowOrder(ids, [{ source: 'a', target: 'b' }, { source: 'a', target: 'c' }])).toBeNull()
    expect(getFlowOrder(ids, [{ source: 'a', target: 'c' }, { source: 'b', target: 'c' }])).toBeNull()
    expect(getFlowOrder(ids, [{ source: 'a', target: 'b' }, { source: 'b', target: 'c' }, { source: 'c', target: 'a' }])).toBeNull()
    expect(getFlowOrder(ids, [{ source: 'a', target: 'unknown' }])).toBeNull()
  })
  it('handles empty and single-node flows', () => {
    expect(getFlowOrder([], [])).toEqual([])
    expect(getFlowOrder(['a'], [])).toEqual(['a'])
  })
})
