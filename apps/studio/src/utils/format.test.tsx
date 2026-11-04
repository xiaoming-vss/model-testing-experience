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

  it('preserves the browser locale output for varied dates and invalid values', () => {
    for (const value of ['1970-01-01T00:00:00Z', '2026-12-31T16:00:00Z', '2026-01-02T03:04:05.123-05:00']) {
      expect(formatTime(value)).toBe(new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }))
    }
    expect(formatTime('invalid date')).toBe('invalid date')
    expect(formatTime()).toBe('-')
  })
})
