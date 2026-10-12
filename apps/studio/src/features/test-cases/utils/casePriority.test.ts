import { expect, it } from 'vitest'
import { formatCasePriority } from './casePriority'

it.each([
  ['0', 'P0'], [1, 'P1'], ['2', 'P2'], ['3', 'P3'],
  ['P2', 'P2'], ['p1', 'P1'], ['', '-'], [null, '-'], ['4', '4'],
])('兼容优先级显示 %s → %s', (value, expected) => {
  expect(formatCasePriority(value)).toBe(expected)
})
