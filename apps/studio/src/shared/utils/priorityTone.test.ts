import { describe, expect, it } from 'vitest'
import { priorityTone } from './priorityTone'

describe('优先级色调', () => {
  it('四档落在共享色盘上，大小写都认', () => {
    expect(priorityTone('P0')).toBe('red')
    expect(priorityTone('p1')).toBe('amber')
    expect(priorityTone(' P2 ')).toBe('blue')
    expect(priorityTone('P3')).toBe('slate')
  })

  it('缺优先级或没见过时按最弱的一档走', () => {
    expect(priorityTone(undefined)).toBe('slate')
    expect(priorityTone('')).toBe('slate')
    expect(priorityTone('P9')).toBe('slate')
  })
})
