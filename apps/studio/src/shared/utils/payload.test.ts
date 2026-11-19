import { describe, expect, it } from 'vitest'
import { normalizeText } from './payload'

describe('normalizeText', () => {
  it('uses an empty string for missing values and preserves existing text', () => {
    expect(normalizeText()).toBe('')
    expect(normalizeText(null)).toBe('')
    expect(normalizeText('保留原文')).toBe('保留原文')
  })
})
