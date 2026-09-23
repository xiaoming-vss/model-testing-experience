import { describe, expect, it } from 'vitest'
import { caseTypeTone } from './caseTone'

describe('用例类型色调', () => {
  it('按关键词认类型，兼容 / 易用 / 功能 / 安全 / 异常各归各色', () => {
    expect(caseTypeTone('兼容测试')).toBe('blue')
    expect(caseTypeTone('兼容性测试')).toBe('blue')
    expect(caseTypeTone('易用性/体验')).toBe('amber')
    expect(caseTypeTone('功能测试')).toBe('purple')
    expect(caseTypeTone('安全测试')).toBe('red')
    expect(caseTypeTone('异常测试')).toBe('orange')
  })

  it('自由文本里带关键词也能认出来', () => {
    expect(caseTypeTone('登录流程测试')).toBe('indigo')
    expect(caseTypeTone('安装部署')).toBe('indigo')
    expect(caseTypeTone('边界值校验')).toBe('teal')
  })

  it('认不出来和空值都走兜底色，不抛错', () => {
    expect(caseTypeTone('回归')).toBe('slate')
    expect(caseTypeTone('')).toBe('slate')
    expect(caseTypeTone(undefined)).toBe('slate')
  })
})
