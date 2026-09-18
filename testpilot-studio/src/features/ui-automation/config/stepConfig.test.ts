import { describe, expect, it } from 'vitest'
import {
  isValidUiStepComparator,
  isValidUiStepKeyword,
  isValidUiStepLocatorType,
  requiresUiStepLocator,
  uiTestKeywordOptions,
  uiTestLocatorTypeOptions,
  usesUiStepComparator,
  usesUiStepOperation,
} from './stepConfig'

describe('UI 步骤规范', () => {
  it('只提供平台支持的关键字和定位方式', () => {
    expect(uiTestKeywordOptions.map((item) => item.value)).toEqual([
      'open',
      'reload',
      'click',
      'dblclick',
      'input',
      'clear',
      'press',
      'wait_text',
      'assert_text',
      'assert_visible',
      'assert_url',
      'screenshot',
      'sleep',
    ])
    expect(uiTestLocatorTypeOptions.map((item) => item.value)).toEqual([
      'css',
      'xpath',
      'text',
      'placeholder',
      'label',
      'test_id',
      'testid',
      'role',
    ])
  })

  it('按关键字决定条件字段', () => {
    expect(requiresUiStepLocator('assert_text')).toBe(true)
    expect(requiresUiStepLocator('assert_url')).toBe(false)
    expect(usesUiStepOperation('assert_text')).toBe(true)
    expect(usesUiStepOperation('assert_visible')).toBe(true)
    expect(usesUiStepOperation('screenshot')).toBe(false)
    expect(usesUiStepComparator('assert_text')).toBe(true)
    expect(usesUiStepComparator('assert_url')).toBe(true)
    expect(usesUiStepComparator('wait_text')).toBe(false)
  })

  it('拒绝规范之外的关键字、定位方式和比较器', () => {
    expect(isValidUiStepKeyword('wait_visible')).toBe(false)
    expect(isValidUiStepKeyword('assert_visible')).toBe(true)
    expect(isValidUiStepLocatorType('id')).toBe(false)
    expect(isValidUiStepLocatorType('test_id')).toBe(true)
    expect(isValidUiStepComparator('equals')).toBe(false)
    expect(isValidUiStepComparator('eq')).toBe(true)
  })
})
