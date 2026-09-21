import { describe, expect, it } from 'vitest'
import { formatStructuredContent, prettyPrintValue } from './value'

describe('structured task output formatting', () => {
  it.each([
    [undefined, ''],
    [null, ''],
    ['', ''],
    ['  ', '  '],
    ['not json', 'not json'],
    ['"text"', '"text"'],
    ['null', 'null'],
    ['false', 'false'],
    ['{"count":1}', '{\n  "count": 1\n}'],
  ])('preserves the output representation of %j', (input, expected) => {
    expect(formatStructuredContent(input)).toBe(expected)
  })

  it('keeps task JSON strings distinct from general display text', () => {
    expect(prettyPrintValue('"text"')).toBe('text')
    expect(formatStructuredContent('"text"')).toBe('"text"')
  })

  it('falls back to text for an object that cannot be serialized', () => {
    const circular: { self?: unknown } = {}
    circular.self = circular
    expect(formatStructuredContent(circular)).toBe('[object Object]')
  })
})
