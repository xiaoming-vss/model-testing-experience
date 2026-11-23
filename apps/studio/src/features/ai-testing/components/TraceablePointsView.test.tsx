import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { TraceableGap, TraceableIssue } from '../utils/traceablePointsModel'
import type { TraceableSelection } from '../utils/traceablePointsGraph'

type MockActionProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  action?: string
  size?: string
  icon?: ReactNode
  loading?: boolean
}

vi.mock('@/domain/projects/components/ProjectActionButton', async () => {
  const React = await import('react')
  return {
    ProjectActionButton: ({ children, action: _action, size: _size, icon: _icon, loading: _loading, ...props }: MockActionProps) => React.createElement('button', props, children),
  }
})

type MockGraphProps = {
  mode: string
  query: string
  selection: TraceableSelection
  expandedSceneIds: ReadonlySet<string>
  activeGap?: TraceableGap
  activeIssue?: TraceableIssue
  onSelect: (selection: TraceableSelection) => void
  onSceneSelect: (sceneId: string) => void
  onRenamePoint: (pointId: string, name: string) => void
  onOpenEvidence: (request: { title: string; blockIds: string[] }) => void
}

vi.mock('./TraceablePointsGraph', async () => {
  const React = await import('react')
  const { forwardRef, useImperativeHandle } = React
  return {
    TraceablePointsGraph: forwardRef(function MockTraceablePointsGraph(props: MockGraphProps, ref) {
      useImperativeHandle(ref, () => ({ saveImage: async () => undefined, fitView: () => undefined }))
      return React.createElement('div', {
        'data-testid': 'traceable-graph',
        'data-mode': props.mode,
        'data-query': props.query,
        'data-selection': JSON.stringify(props.selection),
        'data-expanded': [...props.expandedSceneIds].join(','),
        'data-issue': props.activeIssue?.issue ?? '',
        'data-gap': props.activeGap?.id ?? '',
      },
      React.createElement('button', { type: 'button', onClick: () => props.onSelect({ kind: 'point', id: 'P1' }) }, '选择测试点'),
      React.createElement('button', { type: 'button', onClick: () => props.onSceneSelect('module-0-scene-0') }, '切换场景'),
      React.createElement('button', { type: 'button', onClick: () => props.onRenamePoint('P1', '【配置】验证更新') }, '重命名测试点'),
      React.createElement('button', { type: 'button', onClick: () => props.onOpenEvidence({ title: '【配置】验证保存', blockIds: ['B1'] }) }, '打开证据'))
    }),
  }
})

import { TraceablePointsView } from './TraceablePointsView'

const content = JSON.stringify({
  artifactType: 'traceable_test_points',
  schemaVersion: '1.0',
  reviewStatus: 'independent_review_failed',
  testPoints: [
    {
      id: 'P1', module: '配置', dimension: '功能场景', name: '【配置】验证保存', basis: 'direct',
      materialBlockIds: ['B1'], testObjectIds: ['TO1'], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [],
    },
    {
      id: 'P2', module: '配置', dimension: '异常场景', name: '【配置】验证取消', basis: 'derived',
      materialBlockIds: ['B1'], testObjectIds: [], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [],
    },
  ],
  coverageGaps: [{ id: 'G1', description: '状态待确认', blockedCoverage: '保存后状态', materialBlockIds: [], testObjectIds: ['TO1'], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [] }],
  reviewIssues: [{ kind: 'missing', targetType: 'testPoint', targetId: 'P2', issue: '缺少边界说明', suggestion: '补充保存失败的边界', materialBlockIds: [], testObjectIds: [], impactAreaIds: [], riskIds: [], materialQuestionIds: [], scopeQuestionIds: [] }],
})

const materialContent = JSON.stringify({
  sources: [{ id: 'S1', name: '需求文档' }],
  materialBlocks: [{ id: 'B1', sourceId: 'S1', kind: 'paragraph', locator: '第一段', content: { text: '已确认的业务要求' } }],
})

afterEach(cleanup)

describe('TraceablePointsView', () => {
  it('三页签共用图谱，左侧索引不展示测试点编号', () => {
    render(<TraceablePointsView content={content} materialContent={materialContent} />)

    expect(screen.getByRole('tab', { name: /测试点/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('traceable-graph')).toHaveAttribute('data-mode', 'points')
    expect(screen.getByText('覆盖索引')).toBeInTheDocument()
    expect(screen.getByText('配置')).toBeInTheDocument()
    expect(screen.getByText('功能场景')).toBeInTheDocument()
    expect(screen.getByText('异常场景')).toBeInTheDocument()
    expect(screen.queryByText('P1')).not.toBeInTheDocument()
    expect(screen.queryByText('P2')).not.toBeInTheDocument()
    expect(screen.getAllByText('独立审查未通过').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('tab', { name: /审查/ }))
    expect(screen.getByTestId('traceable-graph')).toHaveAttribute('data-mode', 'issues')
    expect(screen.getByTestId('traceable-graph')).toHaveAttribute('data-issue', '缺少边界说明')
    expect(screen.getByText('缺少边界说明')).toBeInTheDocument()
    expect(screen.getAllByText('【配置】验证取消').length).toBeGreaterThan(0)
    expect(screen.queryByText('P2')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: /缺口/ }))
    expect(screen.getByTestId('traceable-graph')).toHaveAttribute('data-mode', 'gaps')
    expect(screen.getByTestId('traceable-graph')).toHaveAttribute('data-gap', 'G1')
    expect(screen.getAllByText('状态待确认').length).toBeGreaterThan(0)
    expect(screen.getByText('G1')).toBeInTheDocument()
  })

  it('场景可独立展开，全部展开与收起同步图内分支', () => {
    render(<TraceablePointsView content={content} materialContent={materialContent} />)
    const graph = screen.getByTestId('traceable-graph')
    const sceneButton = screen.getByRole('button', { name: /功能场景/ })
    fireEvent.click(sceneButton)
    expect(graph).toHaveAttribute('data-expanded', 'module-0-scene-0')
    fireEvent.click(sceneButton)
    expect(graph).toHaveAttribute('data-expanded', '')

    const expand = screen.getByRole('button', { name: '全部展开' })
    expect(expand).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(expand)
    expect(graph).toHaveAttribute('data-expanded', 'module-0-scene-0,module-0-scene-1')
    expect(screen.getByRole('button', { name: '收起全部' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: '收起全部' }))
    expect(graph).toHaveAttribute('data-expanded', '')
    expect(screen.getByRole('button', { name: '适应画布' })).toBeInTheDocument()
  })

  it('选择测试点打开图内详情，材料依据使用弹窗且标题不展示编号', async () => {
    render(<TraceablePointsView content={content} materialContent={materialContent} />)
    fireEvent.click(screen.getByRole('button', { name: '选择测试点' }))
    expect(JSON.parse(screen.getByTestId('traceable-graph').getAttribute('data-selection')!)).toMatchObject({ kind: 'point', id: 'P1' })
    expect(screen.getAllByText('【配置】验证保存').length).toBeGreaterThan(0)
    expect(screen.queryByText('P1')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '打开证据' }))
    expect(await screen.findByText('已确认的业务要求')).toBeInTheDocument()
    expect(screen.getAllByText('【配置】验证保存').length).toBeGreaterThan(0)
    expect(screen.queryByText('P1')).not.toBeInTheDocument()
  })

  it('搜索测试点后定位并清除搜索，不显示测试点编号', () => {
    render(<TraceablePointsView content={content} materialContent={materialContent} />)
    const graph = screen.getByTestId('traceable-graph')
    const search = screen.getByRole('textbox', { name: '搜索测试点、模块或场景' })
    fireEvent.change(search, { target: { value: '验证保存' } })
    expect(graph).toHaveAttribute('data-query', '验证保存')
    expect(screen.getByText('搜索结果')).toBeInTheDocument()
    expect(screen.getByText('1 个匹配测试点')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /【配置】验证保存/ }))
    expect(search).toHaveValue('')
    expect(JSON.parse(graph.getAttribute('data-selection')!)).toMatchObject({ kind: 'point', id: 'P1' })
    expect(screen.queryByText('P1')).not.toBeInTheDocument()
  })

  it('重命名保留引用并把审查状态重置为自审', async () => {
    const change = vi.fn()
    render(<TraceablePointsView content={content} materialContent={materialContent} onChange={change} />)
    fireEvent.click(screen.getByRole('button', { name: '重命名测试点' }))
    await waitFor(() => expect(change).toHaveBeenCalled())
    const output = JSON.parse(change.mock.calls[0][0])
    expect(output.reviewStatus).toBe('self_review_only')
    expect(output.testPoints[0]).toMatchObject({ name: '【配置】验证更新', materialBlockIds: ['B1'] })
  })

  it('无效产物显示空状态', () => {
    render(<TraceablePointsView content="{}" />)
    expect(screen.getByText('测试点格式无效，请重新生成')).toBeInTheDocument()
  })
})
