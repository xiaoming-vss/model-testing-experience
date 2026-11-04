import { describe, expect, it } from 'vitest'
import { computeFlowLayout, flowColumns, oppositeFlowSide } from './flowLayout'

describe('flow layout', () => {
  it('wraps long flows into a serpentine grid instead of one row', () => {
    expect(flowColumns(32)).toBe(7)
    const { nodes } = computeFlowLayout(32)
    expect(nodes).toHaveLength(32)
    expect(nodes[0].position).toEqual({ x: 0, y: 0 })
    expect(nodes[6].position).toEqual({ x: 6 * 240, y: 0 })
    expect(nodes[7].position).toEqual({ x: 6 * 240, y: 148 })
    expect(nodes[8].position).toEqual({ x: 5 * 240, y: 148 })
    expect(nodes[31].position).toEqual({ x: 3 * 240, y: 4 * 148 })
    expect(nodes[6]).toMatchObject({ sourceSide: 'bottom', targetSide: 'left' })
    expect(nodes[7]).toMatchObject({ targetSide: 'top', sourceSide: 'left' })
    expect(nodes[8]).toMatchObject({ targetSide: 'right', sourceSide: 'left' })
  })

  it('keeps the last card horizontal when the add slot continues the row', () => {
    const { nodes } = computeFlowLayout(32, { withAddSlot: true })
    expect(nodes[31]).toMatchObject({ sourceSide: 'right', targetSide: 'left' })
  })

  it('turns the last card down when the add slot starts a new row', () => {
    expect(flowColumns(24)).toBe(6)
    const { nodes } = computeFlowLayout(24, { withAddSlot: true })
    expect(nodes[23].sourceSide).toBe('bottom')
  })

  it('handles empty and single-node flows', () => {
    expect(flowColumns(0)).toBe(1)
    expect(computeFlowLayout(0).nodes).toEqual([])
    expect(computeFlowLayout(1).nodes[0]).toMatchObject({ position: { x: 0, y: 0 }, sourceSide: 'right', targetSide: 'left' })
  })

  it('maps handle sides for the trailing add card', () => {
    expect(oppositeFlowSide('left')).toBe('right')
    expect(oppositeFlowSide('right')).toBe('left')
    expect(oppositeFlowSide('top')).toBe('bottom')
    expect(oppositeFlowSide('bottom')).toBe('top')
  })
})
