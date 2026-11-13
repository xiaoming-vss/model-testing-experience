import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TraceablePointsView } from './TraceablePointsView'

const content = JSON.stringify({
  artifactType: 'traceable_test_points', schemaVersion: '1.0', reviewStatus: 'independent_reviewed',
  testPoints: [{ id: 'P1', module: '配置', dimension: '功能场景', name: '【配置】验证保存', materialBlockIds: ['B1'] }],
  coverageGaps: [{ id: 'G1', description: '状态待确认', blockedCoverage: '保存后状态' }],
})

describe('TraceablePointsView', () => {
  it('按功能场景显示测试点、审查状态与覆盖缺口', () => {
    const materialContent = JSON.stringify({ sources: [{ id: 'S1', name: '需求文档' }], materialBlocks: [{ id: 'B1', sourceId: 'S1', kind: 'paragraph', locator: '第一段', content: { text: '已确认的业务要求' } }] })
    render(<TraceablePointsView content={content} materialContent={materialContent} />)
    expect(screen.getByText('配置')).toBeTruthy()
    expect(screen.getByText('功能场景')).toBeTruthy()
    expect(screen.getByText('独立审查通过')).toBeTruthy()
    expect(screen.getByText('状态待确认')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '查看关联' }))
    expect(screen.getByText('B1')).toBeTruthy()
    expect(screen.getByText('已确认的业务要求')).toBeTruthy()
  })
  it('切换树图时为画布启用完整高度布局，切回详情恢复滚动', () => {
    const { container } = render(<TraceablePointsView content={content} tree={<div>树图内容</div>} />)
    const view = container.querySelector('.ai-traceable-points')!
    expect(view.classList.contains('is-tree-active')).toBe(false)
    fireEvent.click(screen.getByRole('tab', { name: '树图' }))
    expect(view.classList.contains('is-tree-active')).toBe(true)
    fireEvent.click(screen.getByRole('tab', { name: '测试点详情' }))
    expect(view.classList.contains('is-tree-active')).toBe(false)
  })
  it('编辑后保留引用并重置审查状态', () => {
    const change = vi.fn()
    render(<TraceablePointsView content={content} onChange={change} />)
    fireEvent.change(screen.getByRole('textbox', { name: '测试点 P1' }), { target: { value: '【配置】验证更新' } })
    const output = JSON.parse(change.mock.calls[0][0])
    expect(output.reviewStatus).toBe('self_review_only')
    expect(output.testPoints[0].materialBlockIds).toEqual(['B1'])
  })
})
