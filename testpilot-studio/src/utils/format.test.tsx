import { describe, expect, it } from 'vitest'
import { formatTime } from './format'

describe('formatTime', () => {
  it('treats a timezone-less API timestamp as UTC and displays Shanghai time', () => {
    expect(formatTime('2026-08-06T01:46:53')).toBe('2026/8/6 09:46:53')
  })

  it('displays timezone-aware API timestamps in Shanghai time', () => {
    expect(formatTime('2026-08-06T01:46:53Z')).toBe('2026/8/6 09:46:53')
    expect(formatTime('2026-08-06T09:46:53+08:00')).toBe('2026/8/6 09:46:53')
  })
})
