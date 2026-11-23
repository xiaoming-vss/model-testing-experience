import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { notify } from '@/shared/utils/toast'
import { RequirementAnalysisDiagramView } from './RequirementAnalysisView'

vi.mock('@/shared/utils/toast', () => ({ notify: { success: vi.fn(), error: vi.fn() } }))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const content = JSON.stringify({
  schemaVersion: '1.0',
  artifactType: 'test_scope_impact_risk',
  testObjects: [
    {
      id: 'TO1', name: '存量记录迁移', type: '历史数据',
      description: '旧记录升级后仍需可读', basisStatus: 'confirmed', sourceBlockIds: ['b1', 'b2'],
    },
    {
      id: 'TO2', name: '结果页导出', type: '页面交互',
      description: '结果页提供导出入口', basisStatus: 'inferred', sourceBlockIds: ['b1'],
    },
  ],
  impactAreas: [{
    id: 'I1', area: '旧记录处理', impact: '升级后回退可能混用历史产物',
    testObjectIds: ['TO1'], sourceBlockIds: ['b1'], basisStatus: 'confirmed',
  }],
  risks: [{
    id: 'R1', description: '历史产物可能混用',
    testObjectIds: ['TO1'], impactAreaIds: ['I1'], sourceBlockIds: ['b1'], basisStatus: 'inferred',
  }],
  openQuestions: [{
    id: 'Q1', question: '其他记录如何处理？',
    testObjectIds: ['TO1'], impactAreaIds: ['I1'], riskIds: ['R1'],
    sourceBlockIds: ['b1'], sourceQuestionIds: ['MQ1'],
  }],
})

const material = JSON.stringify({
  sources: [{ id: 's1', name: '需求说明书', type: 'document' }],
  materialBlocks: [
    { id: 'b1', sourceId: 's1', locator: '需求 2.1', kind: 'paragraph', content: { text: '指定记录回退' } },
    { id: 'b2', sourceId: 's1', locator: '需求 2.2', kind: 'table', content: { rows: [['字段', '规则'], ['状态', '回退']] } },
  ],
  questions: [{ id: 'MQ1', question: '旧数据是否保留？' }],
})

function renderView() {
  render(<RequirementAnalysisDiagramView content={content} materialContent={material} />)
}

describe('测试范围分析', () => {
  it('旧格式不进入可视化展示', () => {
    render(<RequirementAnalysisDiagramView content={JSON.stringify({ functionalOverview: { purpose: '旧内容' } })} />)
    expect(screen.getByText('测试范围风险分析格式无效，请重新生成')).toBeInTheDocument()
    expect(screen.queryByText('旧内容')).not.toBeInTheDocument()
  })

  it('用分类矩阵切换列表与详情，并展示反向关联和冻结材料', () => {
    renderView()

    const objectCategory = screen.getByRole('button', { name: /测试对象，2 条/ })
    expect(objectCategory).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('heading', { name: '测试范围' })).toBeInTheDocument()

    const objectList = screen.getByRole('navigation', { name: '测试对象列表' })
    expect(within(objectList).getByRole('heading', { name: /存量与配置/ })).toBeInTheDocument()
    expect(within(objectList).getByRole('heading', { name: /页面与操作/ })).toBeInTheDocument()

    const objectDetail = screen.getByRole('region', { name: '测试对象详情' })
    expect(within(objectDetail).getByRole('heading', { level: 2, name: '存量记录迁移' })).toBeInTheDocument()
    expect(within(objectDetail).getByText('旧记录升级后仍需可读')).toBeInTheDocument()
    expect(within(objectDetail).getByText('历史数据')).toBeInTheDocument()
    expect(within(objectDetail).getByText('明确')).toBeInTheDocument()
    expect(within(objectDetail).getByRole('button', { name: '查看影响范围 I1：旧记录处理' })).toBeInTheDocument()
    expect(within(objectDetail).getByRole('button', { name: '查看风险 R1：历史产物可能混用' })).toBeInTheDocument()
    expect(within(objectDetail).getByRole('button', { name: '查看待确认 Q1：其他记录如何处理？' })).toBeInTheDocument()

    expect(within(objectDetail).getByText('需求说明书')).toBeInTheDocument()
    expect(within(objectDetail).getByText('需求文档 · 2 个材料块')).toBeInTheDocument()
    expect(within(objectDetail).getByText('指定记录回退')).toBeInTheDocument()
    const tableToggle = within(objectDetail).getByRole('button', { name: /需求 2\.2/ })
    expect(tableToggle).toHaveAttribute('aria-expanded', 'false')
    const tableBody = document.getElementById(tableToggle.getAttribute('aria-controls')!)
    expect(tableBody).toHaveAttribute('hidden')
    fireEvent.click(tableToggle)
    expect(tableToggle).toHaveAttribute('aria-expanded', 'true')
    expect(tableBody).not.toHaveAttribute('hidden')
    expect(within(tableBody!).getByText('字段')).toBeInTheDocument()

    fireEvent.click(within(objectDetail).getByRole('button', { name: '查看影响范围 I1：旧记录处理' }))
    const impactDetail = screen.getByRole('region', { name: '影响范围详情' })
    expect(within(impactDetail).getByText('升级后回退可能混用历史产物')).toBeInTheDocument()
    expect(within(impactDetail).getByRole('button', { name: '查看测试对象 TO1：存量记录迁移' })).toBeInTheDocument()

    fireEvent.click(within(impactDetail).getByRole('button', { name: '查看测试对象 TO1：存量记录迁移' }))
    expect(screen.getByRole('region', { name: '测试对象详情' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /测试对象，2 条/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('支持搜索、状态筛选、清除与待确认来源问题', () => {
    renderView()
    const objectList = screen.getByRole('navigation', { name: '测试对象列表' })
    const search = screen.getByRole('textbox', { name: '搜索当前分类条目' })

    fireEvent.change(search, { target: { value: '导出' } })
    expect(within(objectList).queryByText('存量记录迁移')).not.toBeInTheDocument()
    expect(within(objectList).getByText('结果页导出')).toBeInTheDocument()
    expect(screen.getByText('结果页提供导出入口')).toBeInTheDocument()

    fireEvent.keyDown(search, { key: 'Escape' })
    expect(search).toHaveValue('')

    fireEvent.change(search, { target: { value: '不存在' } })
    expect(within(objectList).getByText('没有匹配的条目')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '测试对象详情' })).toBeInTheDocument()
    expect(screen.queryByText('暂无测试对象')).not.toBeInTheDocument()
    fireEvent.click(within(objectList).getByRole('button', { name: '清除筛选' }))
    expect(search).toHaveValue('')

    const filterGroup = screen.getByRole('group', { name: '按依据状态筛选' })
    fireEvent.click(within(filterGroup).getByRole('button', { name: /推测/ }))
    expect(within(filterGroup).getByRole('button', { name: /推测/ })).toHaveAttribute('aria-pressed', 'true')
    expect(within(objectList).queryByText('存量记录迁移')).not.toBeInTheDocument()
    expect(within(objectList).getByText('结果页导出')).toBeInTheDocument()
    expect(within(filterGroup).getByRole('button', { name: /待确认/ })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: /待确认，1 条/ }))
    const questionDetail = screen.getByRole('region', { name: '待确认详情' })
    expect(within(questionDetail).getByText(/材料未明确/)).toBeInTheDocument()
    expect(within(questionDetail).getByText('旧数据是否保留？')).toBeInTheDocument()
    expect(within(questionDetail).getByRole('button', { name: '查看风险 R1：历史产物可能混用' })).toBeInTheDocument()
    expect(screen.getByLabelText('待确认项的关联范围')).toHaveTextContent('涉及 1 个测试对象 · 1 个影响范围 · 1 个风险')

    fireEvent.keyDown(document, { key: '/' })
    expect(search).toHaveFocus()
  })

  it('复制条目 ID 后给出提示', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    renderView()

    fireEvent.click(screen.getByRole('button', { name: '复制 ID TO1' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('TO1'))
    expect(notify.success).toHaveBeenCalledWith('ID 已复制')
  })
})
