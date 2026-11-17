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

  it('按分类展示列表、详情、关联与冻结材料', () => {
    render(<RequirementAnalysisDiagramView content={content} materialContent={material} />)

    expect(screen.getByRole('tab', { name: /测试对象/ })).toHaveAttribute('aria-selected', 'true')
    const objectList = screen.getByRole('complementary', { name: '测试对象列表' })
    expect(within(objectList).getByText('存量记录')).toBeInTheDocument()
    const objectDetail = screen.getByRole('region', { name: '测试对象详情' })
    expect(within(objectDetail).getByText('数据')).toBeInTheDocument()
    expect(within(objectDetail).getByText('关注旧记录')).toBeInTheDocument()
    expect(within(objectDetail).getByText('指定记录回退')).toBeInTheDocument()
    expect(within(objectDetail).getByText('需求 2.1')).toBeInTheDocument()
    expect(screen.queryByText(/类型：/)).not.toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: '材料依据' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /影响范围/ }))
    const impactDetail = screen.getByRole('region', { name: '影响范围详情' })
    expect(within(impactDetail).getByText('更新后回退')).toBeInTheDocument()
    expect(within(impactDetail).getByText('TO1 存量记录')).toBeInTheDocument()
    expect(within(impactDetail).getByText('指定记录回退')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /风险/ }))
    const riskDetail = screen.getByRole('region', { name: '风险详情' })
    expect(within(riskDetail).getByText('历史产物可能混用')).toBeInTheDocument()
    expect(within(riskDetail).getByText('推测')).toBeInTheDocument()
    expect(within(riskDetail).getByText('I1 旧记录处理')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '影响范围详情' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /待确认/ }))
    const questionDetail = screen.getByRole('region', { name: '待确认详情' })
    expect(within(questionDetail).getByText('其他记录如何处理？')).toBeInTheDocument()
    expect(within(questionDetail).getByText('R1 历史产物可能混用')).toBeInTheDocument()
    expect(within(questionDetail).getByText('指定记录回退')).toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: '材料依据' })).not.toBeInTheDocument()
  })
})
