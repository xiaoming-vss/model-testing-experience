import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RequirementAnalysisDiagramView } from './RequirementAnalysisView'

const content = JSON.stringify({
  schemaVersion: '1.0', artifactType: 'test_scope_impact_risk',
  testObjects: [{ id: 'TO1', name: '存量记录', type: '数据', description: '关注旧记录', basisStatus: 'confirmed', sourceBlockIds: ['b1'] }],
  impactAreas: [{ id: 'I1', area: '旧记录处理', impact: '更新后回退', testObjectIds: ['TO1'], sourceBlockIds: ['b1'], basisStatus: 'confirmed' }],
  risks: [{ id: 'R1', description: '历史产物可能混用', testObjectIds: ['TO1'], impactAreaIds: ['I1'], sourceBlockIds: ['b1'], basisStatus: 'inferred' }],
  openQuestions: [{ id: 'Q1', question: '其他记录如何处理？', testObjectIds: ['TO1'], impactAreaIds: ['I1'], riskIds: ['R1'], sourceBlockIds: ['b1'], sourceQuestionIds: [] }],
})
const material = JSON.stringify({ materialBlocks: [{ id: 'b1', locator: '需求 2.1', content: { text: '指定记录回退' } }] })

describe('测试范围分析', () => {
  it('旧格式不进入可视化展示', () => {
    render(<RequirementAnalysisDiagramView content={JSON.stringify({ functionalOverview: { purpose: '旧内容' } })} />)
    expect(screen.getByText('测试范围风险分析格式无效，请重新生成')).toBeInTheDocument()
    expect(screen.queryByText('旧内容')).not.toBeInTheDocument()
  })

  it('按分类展示关联、依据状态及冻结材料', () => {
    render(<RequirementAnalysisDiagramView content={content} materialContent={material} />)
    expect(screen.getByText('存量记录')).toBeInTheDocument()
    expect(screen.queryByText(/类型：/)).not.toBeInTheDocument()
    expect(screen.queryByText(/材料依据：/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /业务影响范围/ }))
    expect(screen.getByText('更新后回退')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /旧记录处理/ }))
    const evidence = screen.getByRole('complementary', { name: '材料依据' })
    expect(within(evidence).getByText('指定记录回退')).toBeInTheDocument()
    expect(within(evidence).getByText('需求 2.1')).toBeInTheDocument()
    fireEvent.click(within(evidence).getByRole('button', { name: '关闭材料依据' }))
    expect(screen.queryByRole('complementary', { name: '材料依据' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /旧记录处理/ }))
    fireEvent.click(screen.getByRole('button', { name: /风险/ }))
    expect(screen.queryByRole('complementary', { name: '材料依据' })).not.toBeInTheDocument()
    expect(screen.getByText('历史产物可能混用')).toBeInTheDocument()
    expect(screen.getByText('推测')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /待确认问题/ }))
    expect(screen.getByText('其他记录如何处理？')).toBeInTheDocument()
    expect(screen.queryByText(/关联风险：/)).not.toBeInTheDocument()
  })
})
