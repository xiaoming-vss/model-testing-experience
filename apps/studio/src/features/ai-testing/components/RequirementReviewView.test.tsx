import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { RequirementReviewView } from './RequirementReviewView'

const REVIEW = {
  schemaVersion: '1.0',
  artifactType: 'requirement_review',
  reviewStatus: 'blocked',
  summary: {
    scope: 'PRD v1.2 下单流程',
    materialsReviewed: ['PRD.docx'],
    confirmedFacts: ['用户可以在商品详情页点击立即购买'],
    workingAssumptions: ['库存不足指可用库存为 0'],
    hypothesesToVerify: ['支付前是否会重新校验库存'],
    inputGaps: ['缺少库存不足时的接口错误码'],
  },
  issues: [
    {
      id: 'RR-01',
      topic: '库存不足时的下单行为',
      type: 'conflict',
      severity: 'blocker',
      evidence: [
        {
          sourceName: 'PRD.docx',
          locator: '3.2 下单流程 / 第 12 段',
          quote: '库存不足时仍可提交订单',
        },
      ],
      impact: '实现和测试无法确定库存不足时是创建订单还是拒绝请求。',
      question: '库存不足时到底能不能提交订单？',
      suggestedOwner: 'product',
      nextAction: '产品确认库存不足场景的业务规则。',
      verifyMethod: 'analysis',
      failureMode: 'conflict_escape',
    },
  ],
  coverage: {
    structure: [{ name: 'background', status: 'present' }],
    qualityCharacteristics: [{ name: 'unambiguous', status: 'fail', issueIds: ['RR-01'] }],
    smells: [{ type: 'vague', quote: '库存不足时仍可提交订单', issueId: 'RR-01' }],
    behavioralStates: [{ area: 'state', status: 'gap', note: '未说明订单状态' }],
    traceability: [
      {
        kind: 'rule_without_ac',
        status: 'fail',
        note: '库存不足规则没有可判定的验收标准',
        issueId: 'RR-01',
      },
    ],
    inputAudit: {
      materials: ['PRD.docx'],
      missing: ['库存不足时的接口错误码'],
      recency: 'PRD 为本次上传版本',
      comparability: '只评审文档内部一致性',
    },
  },
}

function renderReview(content: string) {
  return render(
    <TestThemeProvider>
      <RequirementReviewView content={content} />
    </TestThemeProvider>,
  )
}

afterEach(cleanup)

describe('RequirementReviewView', () => {
  it('renders the conclusion tab with summary and severity breakdown', () => {
    renderReview(JSON.stringify(REVIEW))
    expect(screen.getByRole('tab', { name: /结论/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByText('阻断').length).toBeGreaterThan(0)
    expect(screen.getByText('评审报告仅供人工判断，不阻断材料整理')).toBeInTheDocument()
    expect(screen.getByText('PRD v1.2 下单流程')).toBeInTheDocument()
    expect(screen.getByText('用户可以在商品详情页点击立即购买')).toBeInTheDocument()
    expect(screen.getByText('缺少库存不足时的接口错误码')).toBeInTheDocument()
  })

  it('shows issues with evidence and fields on the issues tab', async () => {
    const user = userEvent.setup()
    renderReview(JSON.stringify(REVIEW))
    const issuesTab = screen.getByRole('tab', { name: /问题/ })
    expect(issuesTab).toHaveTextContent('1')
    await user.click(issuesTab)
    expect(issuesTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByText('RR-01').length).toBeGreaterThan(0)
    expect(screen.getAllByText('库存不足时的下单行为').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/库存不足时仍可提交订单/).length).toBeGreaterThan(0)
    expect(screen.getByText('库存不足时到底能不能提交订单？')).toBeInTheDocument()
    expect(screen.getByText('产品确认库存不足场景的业务规则。')).toBeInTheDocument()
    expect(screen.getByText('冲突会漏到下游')).toBeInTheDocument()
  })

  it('lists coverage dimensions and switches between details', async () => {
    const user = userEvent.setup()
    renderReview(JSON.stringify(REVIEW))
    await user.click(screen.getByRole('tab', { name: /覆盖度/ }))
    expect(screen.getByRole('heading', { name: /结构盘点/ })).toBeInTheDocument()
    expect(screen.getByText('背景')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /质量特性/ }))
    expect(screen.getByText('无歧义')).toBeInTheDocument()
    expect(screen.getByText('不通过')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /输入审计/ }))
    expect(screen.getByText('缺失材料')).toBeInTheDocument()
    expect(screen.getByText('时效性')).toBeInTheDocument()
    expect(screen.getByText('只评审文档内部一致性')).toBeInTheDocument()
  })

  it('shows a stable empty state for invalid JSON', () => {
    renderReview('not json')
    expect(screen.getByText('评审报告格式无效，请重新生成')).toBeInTheDocument()
  })

  it('renders a passed report with minor issues', async () => {
    const user = userEvent.setup()
    renderReview(JSON.stringify({
      ...REVIEW,
      reviewStatus: 'passed',
      issues: [{ ...REVIEW.issues[0], id: 'RR-02', severity: 'minor', type: 'weak_ac' }],
    }))
    expect(screen.getByText('通过')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: /问题/ }))
    expect(screen.getAllByText('次要').length).toBeGreaterThan(0)
  })
})
