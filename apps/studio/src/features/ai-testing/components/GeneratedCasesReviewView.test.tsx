import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import type { GeneratedCasesSelection } from '../utils/generatedCasesGraph'
import type { GeneratedCaseEntry, GeneratedCasesModel } from '../utils/generatedCasesModel'

vi.mock('@/domain/projects/components/ProjectActionButton', async () => {
  const React = await import('react')
  return {
    ProjectActionButton: ({ children, action: _action, size: _size, icon: _icon, loading: _loading, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { action?: string; size?: string; icon?: ReactNode; loading?: boolean }) => React.createElement('button', props, children),
  }
})

type MockGraphProps = {
  model: GeneratedCasesModel
  selection: GeneratedCasesSelection
  expandedSceneIds: ReadonlySet<string>
  canDelete: boolean
  onChangeCase?: (entry: GeneratedCaseEntry, patch: Record<string, unknown>) => void
  onDeleteCase?: (entry: GeneratedCaseEntry) => void
  onSelect: (selection: GeneratedCasesSelection) => void
  onSceneSelect: (sceneId: string) => void
}

vi.mock('./GeneratedCasesGraph', async () => {
  const React = await import('react')
  const { forwardRef, useImperativeHandle } = React
  const button = (label: string, onClick: () => void, key?: string) => React.createElement('button', { type: 'button', onClick, key }, label)
  return {
    GeneratedCasesGraph: forwardRef(function MockGeneratedCasesGraph(props: MockGraphProps, ref) {
      useImperativeHandle(ref, () => ({ saveImage: async () => undefined, fitView: () => undefined }))
      const entries = props.model.entries
      return React.createElement('div', {
        'data-testid': 'generated-cases-graph',
        'data-selection': JSON.stringify(props.selection),
        'data-expanded': [...props.expandedSceneIds].join(','),
      },
      button('选择第一', () => props.onSelect({ kind: 'case', key: entries[0].key }), 'first'),
      button('选择第三', () => props.onSelect({ kind: 'case', key: entries[2].key }), 'third'),
      button('切换首个类型', () => props.onSceneSelect(props.model.modules[0].scenes[0].id), 'scene'),
      button('编辑第一', () => props.onChangeCase?.(entries[0], { case_title: '新名称' }), 'edit'),
      props.canDelete ? button('删除第一', () => props.onDeleteCase?.(entries[0]), 'delete') : null,
      )
    }),
  }
})

import { GeneratedCasesReviewView } from './GeneratedCasesReviewView'

const content = JSON.stringify({
  cases: [
    { case_id: 'case-a', case_module: '模块A', case_type: '功能测试', case_title: '用例甲', priority: 'P1' },
    { case_id: 'case-b', case_module: '模块A', case_type: '功能测试', case_title: '用例乙', priority: 'P2' },
    { case_id: 'case-c', case_module: '模块B', case_type: '异常测试', case_title: '用例丙', priority: 'P3' },
  ],
})

function Draft({ allowDelete = false }: { allowDelete?: boolean }) {
  const [value, setValue] = useState(content)
  return <>
    <output data-testid="draft">{value}</output>
    <GeneratedCasesReviewView allowDelete={allowDelete} content={value} onChange={setValue} />
  </>
}

function selectionOf() {
  return JSON.parse(screen.getByTestId('generated-cases-graph').getAttribute('data-selection')!) as GeneratedCasesSelection
}

afterEach(cleanup)

describe('GeneratedCasesReviewView', () => {
  it('零条新用例时仍展示历史用例及其三类结论', () => {
    render(<GeneratedCasesReviewView content={JSON.stringify({
      cases: [],
      historicalCaseFindings: [
        { caseId: 'case-a', decision: 'reuse', title: '旧用例甲', pointRefs: [{ pointId: 'P1' }] },
        { caseId: 'case-b', decision: 'modify', title: '旧用例乙', modificationHint: '调整数量上限' },
        { caseId: 'case-c', decision: 'invalidate', title: '旧用例丙', reason: '旧规则已取消' },
      ],
    })} />)
    expect(screen.getByText('本轮没有新生成的用例')).toBeInTheDocument()
    const history = screen.getByRole('region', { name: '历史用例结论' })
    expect(within(history).getByText('可复用')).toBeInTheDocument()
    expect(within(history).getByText('需修改')).toBeInTheDocument()
    expect(within(history).getByText('建议失效')).toBeInTheDocument()
    expect(within(history).getByText('关联测试点 P1')).toBeInTheDocument()
    expect(within(history).getByText('调整数量上限')).toBeInTheDocument()
  })

  it('渲染用例索引与总览，画布内提供展开、适应画布和保存图谱', async () => {
    render(<GeneratedCasesReviewView content={content} />)
    expect(screen.getByRole('heading', { name: '完整用例图谱' })).toHaveClass('sr-only')
    expect(screen.getByText('用例索引')).toBeInTheDocument()
    expect(screen.getByText('模块A')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /功能测试/ })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '搜索用例、模块或类型' })).not.toBeInTheDocument()
    const canvas = screen.getByRole('main', { name: '完整用例图谱' })
    expect(within(canvas).getByRole('button', { name: '全部展开' })).toBeInTheDocument()
    expect(within(canvas).getByRole('button', { name: '适应画布' })).toBeInTheDocument()
    expect(within(canvas).getByRole('button', { name: '保存图谱' })).toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: '选中用例详情' })).not.toBeInTheDocument()
    await waitFor(() => expect(selectionOf()).toEqual({ kind: 'overview' }))
    expect(screen.getByTestId('generated-cases-graph').getAttribute('data-expanded')).toBe('')

    fireEvent.click(screen.getByRole('button', { name: '选择第一' }))
    await waitFor(() => expect(selectionOf()).toMatchObject({ kind: 'case', key: '模块A:0' }))
    expect(screen.getByTestId('generated-cases-graph').getAttribute('data-expanded')).toContain('module-0-scene-0')
  })

  it('用例类型可独立展开，全部展开与收起同步图内分支', async () => {
    render(<GeneratedCasesReviewView content={content} />)
    const graph = screen.getByTestId('generated-cases-graph')
    expect(graph.getAttribute('data-expanded')).toBe('')
    fireEvent.click(screen.getByRole('button', { name: '切换首个类型' }))
    expect(graph.getAttribute('data-expanded')).toContain('module-0-scene-0')
    fireEvent.click(screen.getByRole('button', { name: '切换首个类型' }))
    expect(graph.getAttribute('data-expanded')).not.toContain('module-0-scene-0')

    fireEvent.click(screen.getByRole('button', { name: '全部展开' }))
    expect(graph.getAttribute('data-expanded')).toContain('module-0-scene-0,module-1-scene-0')
    expect(screen.getByRole('button', { name: '收起全部' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: '收起全部' }))
    expect(graph.getAttribute('data-expanded')).toBe('')
  })

  it('编辑用例名称更新内容并保留其他字段', async () => {
    const change = vi.fn()
    render(<GeneratedCasesReviewView content={content} onChange={change} />)
    fireEvent.click(screen.getByRole('button', { name: '编辑第一' }))
    const output = JSON.parse(change.mock.calls[0][0])
    expect(output.cases[0]).toMatchObject({ case_title: '新名称', case_id: 'case-a', case_type: '功能测试' })
  })

  it('删除当前用例后顺延选中下一条', async () => {
    render(<Draft allowDelete />)
    fireEvent.click(await screen.findByRole('button', { name: '删除第一' }))
    await waitFor(() => {
      const cases = JSON.parse(screen.getByTestId('draft').textContent!).cases as Array<{ case_title: string }>
      expect(cases.map(item => item.case_title)).toEqual(['用例乙', '用例丙'])
    })
    await waitFor(() => expect(selectionOf()).toMatchObject({ kind: 'case', key: '模块A:0' }))
  })

  it('删除当前选中项之前的用例后保持原选中项', async () => {
    render(<Draft allowDelete />)
    fireEvent.click(screen.getByRole('button', { name: '选择第三' }))
    await waitFor(() => expect(selectionOf()).toMatchObject({ kind: 'case', key: '模块B:2' }))
    fireEvent.click(screen.getByRole('button', { name: '删除第一' }))
    await waitFor(() => {
      const cases = JSON.parse(screen.getByTestId('draft').textContent!).cases as Array<{ case_title: string }>
      expect(cases.map(item => item.case_title)).toEqual(['用例乙', '用例丙'])
    })
    await waitFor(() => expect(selectionOf()).toMatchObject({ kind: 'case', key: '模块B:1' }))
  })

  it('只读模式不展示删除操作', async () => {
    render(<GeneratedCasesReviewView content={content} />)
    await waitFor(() => expect(selectionOf()).toEqual({ kind: 'overview' }))
    expect(screen.queryByRole('button', { name: '删除第一' })).not.toBeInTheDocument()
  })

  it('无效产物显示空态', () => {
    render(<GeneratedCasesReviewView content="not-json" />)
    expect(screen.getByText('用例格式无效，请重新生成')).toBeInTheDocument()
  })
})
