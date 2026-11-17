import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import type { CaseNameTreeNode } from '../utils/caseNameTree'

vi.mock('./CaseNamesResultView', () => ({
  CaseNameTreeView: ({ renderRelations, defaultCollapsed, toolbarHint }: {
    renderRelations?: (node: CaseNameTreeNode) => ReactNode
    defaultCollapsed?: Iterable<string>
    toolbarHint?: string
  }) => {
    const point: CaseNameTreeNode = { id: 'P1', title: '【配置】验证保存', kind: 'point', children: [] }
    return <div data-testid="case-tree-view" data-collapsed={[...(defaultCollapsed ?? [])].length} data-hint={toolbarHint}>{renderRelations?.(point)}</div>
  },
}))

import { TraceablePointsView } from './TraceablePointsView'

const content = JSON.stringify({
  artifactType: 'traceable_test_points', schemaVersion: '1.0', reviewStatus: 'independent_review_failed',
  testPoints: [{ id: 'P1', module: '配置', dimension: '功能场景', name: '【配置】验证保存', materialBlockIds: ['B1'] }],
  coverageGaps: [{ id: 'G1', description: '状态待确认', blockedCoverage: '保存后状态' }],
  reviewIssues: [{ targetId: 'P1', issue: '缺少边界说明', suggestion: '补充保存失败的边界' }],
})

const materialContent = JSON.stringify({
  sources: [{ id: 'S1', name: '需求文档' }],
  materialBlocks: [{ id: 'B1', sourceId: 'S1', kind: 'paragraph', locator: '第一段', content: { text: '已确认的业务要求' } }],
})

describe('TraceablePointsView', () => {
  it('默认只读测试点页，审查与缺口分页展示且不提供处理动作', () => {
    render(<TraceablePointsView content={content} materialContent={materialContent} />)

    expect(screen.getByRole('tab', { name: /测试点/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('case-tree-view')).toHaveAttribute('data-collapsed', '1')
    expect(screen.getByTestId('case-tree-view')).toHaveAttribute('data-hint', '点击场景展开测试点；悬停节点显示关联按钮')
    expect(screen.getByText('P1 【配置】验证保存')).toBeInTheDocument()
    expect(screen.getByText('已确认的业务要求')).toBeInTheDocument()

    const issuesTab = screen.getByRole('tab', { name: /审查/ })
    const gapsTab = screen.getByRole('tab', { name: /缺口/ })
    expect(issuesTab).toHaveAttribute('aria-selected', 'false')
    expect(gapsTab).toHaveAttribute('aria-selected', 'false')

    fireEvent.click(issuesTab)
    expect(issuesTab).toHaveAttribute('aria-selected', 'true')
    const issueList = screen.getByRole('complementary', { name: '未解决的审查问题列表' })
    expect(within(issueList).getByText('缺少边界说明')).toBeInTheDocument()
    const issueDetail = screen.getByRole('region', { name: '审查问题详情' })
    expect(within(issueDetail).getByText('缺少边界说明')).toBeInTheDocument()
    expect(within(issueDetail).getByText('补充保存失败的边界')).toBeInTheDocument()
    expect(screen.getByText('独立审查未通过')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '覆盖缺口列表' })).not.toBeInTheDocument()

    fireEvent.click(gapsTab)
    expect(gapsTab).toHaveAttribute('aria-selected', 'true')
    const detail = screen.getByRole('region', { name: '覆盖缺口详情' })
    expect(within(detail).getByText('状态待确认')).toBeInTheDocument()
    expect(within(detail).getByText('保存后状态')).toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: '未解决的审查问题列表' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '标记已处理' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /下一条/ })).not.toBeInTheDocument()
  })

  it('关联气泡内修改名称后保留引用并重置审查状态', () => {
    const change = vi.fn()
    render(<TraceablePointsView content={content} materialContent={materialContent} onChange={change} />)
    const input = screen.getByRole('textbox', { name: '测试点 P1' })
    fireEvent.change(input, { target: { value: '【配置】验证更新' } })
    fireEvent.blur(input)
    const output = JSON.parse(change.mock.calls[0][0])
    expect(output.reviewStatus).toBe('self_review_only')
    expect(output.testPoints[0].materialBlockIds).toEqual(['B1'])
  })
})
