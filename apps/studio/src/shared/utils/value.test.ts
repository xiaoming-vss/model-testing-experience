import { describe, expect, it } from 'vitest'
import { formatBytes, formatStructuredContent, isJsonText, parseJsonRecord, prettyPrintValue, toRecord } from './value'

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

describe('toRecord', () => {
  it('accepts plain objects and rejects arrays and primitives', () => {
    expect(toRecord({ value: 1 })).toEqual({ value: 1 })
    expect(toRecord([{ value: 1 }])).toBeNull()
    expect(toRecord('value')).toBeNull()
    expect(toRecord(null)).toBeNull()
  })
})

describe('JSON text helpers', () => {
  it('parses object JSON and rejects other JSON values', () => {
    expect(parseJsonRecord('{"value":1}')).toEqual({ value: 1 })
    expect(parseJsonRecord({ value: 1 })).toEqual({ value: 1 })
    expect(parseJsonRecord('[1]')).toBeNull()
    expect(parseJsonRecord('not json')).toBeNull()
  })

  it('treats empty text as valid only when explicitly allowed', () => {
    expect(isJsonText('')).toBe(true)
    expect(isJsonText('', { allowEmpty: false })).toBe(false)
    expect(isJsonText('{"value":1}')).toBe(true)
    expect(isJsonText('{')).toBe(false)
  })

  it('formats bytes with one implementation', () => {
    expect(formatBytes(12)).toBe('12 B')
    expect(formatBytes(1536)).toBe('1.50 KB')
    expect(formatBytes(1536, 1)).toBe('1.5 KB')
    expect(formatBytes(2 * 1024 * 1024)).toBe('2.00 MB')
    expect(formatBytes(-1)).toBe('-')
  })
})
