import { describe, expect, it } from 'vitest'
import { formatCompactTime, formatTime } from './format'

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

describe('formatCompactTime', () => {
  it.each([
    ['2026-11-26T03:15:00Z', '11/26 11:15'],
    ['2026-11-26T02:56:00', '11/26 10:56'],
    ['2026-11-25T16:50:00Z', '11/26 00:50'],
    ['2026-11-26T00:50:00+08:00', '11/26 00:50'],
  ])('formats %s as %s in Shanghai time', (value, expected) => {
    expect(formatCompactTime(value)).toBe(expected)
  })

  it('returns an empty string for missing or invalid values', () => {
    expect(formatCompactTime()).toBe('')
    expect(formatCompactTime(null)).toBe('')
    expect(formatCompactTime('invalid date')).toBe('')
  })
})
