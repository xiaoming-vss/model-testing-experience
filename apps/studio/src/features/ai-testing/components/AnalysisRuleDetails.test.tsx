import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { AnalysisRuleDetails } from './AnalysisRuleDetails'

afterEach(cleanup)

describe('AnalysisRuleDetails', () => {
  it('shows compact rules without empty historical fields', () => {
    render(<AnalysisRuleDetails item={{ expectedBehavior: ['生成报告', '不覆盖历史报告'] }} />)
    expect(screen.getByText('生成报告')).toBeTruthy()
    expect(screen.getByText('不覆盖历史报告')).toBeTruthy()
    expect(screen.queryByText('禁止或跳过的行为')).toBeNull()
    expect(screen.queryByText('可观察结果')).toBeNull()
  })

  it('still shows historical rule fields', () => {
    render(<AnalysisRuleDetails item={{ prohibitedOrSkippedBehavior: ['不覆盖历史报告'], observableOutcome: '报告存在' }} />)
    expect(screen.getByText('禁止或跳过的行为')).toBeTruthy()
    expect(screen.getByText('不覆盖历史报告')).toBeTruthy()
    expect(screen.getByText('可观察结果')).toBeTruthy()
    expect(screen.getByText('报告存在')).toBeTruthy()
  })
})
