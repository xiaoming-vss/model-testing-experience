import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReadableRequirementMaterial } from './ReadableRequirementMaterial'

afterEach(cleanup)

const artifact = {
  schemaVersion: '0.2', artifactType: 'readable_requirement_material', title: '材料整理',
  sources: [{ id: 'S1', name: '需求文档', type: 'document', location: null }],
  materialBlocks: [{ id: 'B1', sourceId: 'S1', parentId: null, kind: 'paragraph', locator: '第1段', content: { text: '材料原文' } }],
  functions: [{ id: 'F1', name: '开关', sections: [{ title: '功能使用与业务规则', items: [{ text: '开启后执行处理', status: 'confirmed', materialBlockIds: ['B1'] }] }] }],
  questions: [{ id: 'Q1', question: '如何进入？', reason: '未说明', materialBlockIds: ['B1'], functionIds: ['F1'] }],
}

describe('可读需求材料', () => {
  it('按功能展示说明，并在条目和问题内展开材料依据', () => {
    render(<ReadableRequirementMaterial content={artifact} />)

    expect(screen.getByRole('tab', { name: /功能说明/ })).toHaveAttribute('aria-selected', 'true')
    const functionList = screen.getByRole('complementary', { name: '功能列表' })
    expect(within(functionList).getByText('开关')).toBeInTheDocument()
    const functionDetail = screen.getByRole('region', { name: '功能说明详情' })
    expect(within(functionDetail).getByText('功能使用与业务规则')).toBeInTheDocument()
    expect(within(functionDetail).getByText('开启后执行处理')).toBeInTheDocument()
    expect(within(functionDetail).queryByText('材料原文')).not.toBeInTheDocument()
    fireEvent.click(within(functionDetail).getByRole('button', { name: '依据 1' }))
    expect(within(functionDetail).getByText('材料原文')).toBeVisible()
    expect(within(functionDetail).getByText('第1段')).toBeVisible()

    fireEvent.click(screen.getByRole('tab', { name: /待确认/ }))
    const questionDetail = screen.getByRole('region', { name: '待确认详情' })
    expect(within(questionDetail).getByText('如何进入？')).toBeInTheDocument()
    expect(within(questionDetail).getByText('未说明')).toBeInTheDocument()
    expect(within(questionDetail).getByText('F1 开关')).toBeInTheDocument()
    expect(within(questionDetail).getByText('材料原文')).toBeVisible()
  })

  it('编辑时保留 JSON 其他内容', () => {
    const onChange = vi.fn()
    render(<ReadableRequirementMaterial content={artifact} editable onChange={onChange} />)

    fireEvent.change(screen.getByRole('textbox', { name: '开关 功能使用与业务规则 内容 1' }), { target: { value: '修改后说明' } })
    const result = JSON.parse(onChange.mock.lastCall![0])
    expect(result.functions[0].sections[0].items[0].text).toBe('修改后说明')
    expect(result.materialBlocks).toEqual(artifact.materialBlocks)

    fireEvent.click(screen.getByRole('tab', { name: /待确认/ }))
    fireEvent.change(screen.getByRole('textbox', { name: '待确认问题 1' }), { target: { value: '入口在哪里？' } })
    const edited = JSON.parse(onChange.mock.lastCall![0])
    expect(edited.questions[0].question).toBe('入口在哪里？')
    expect(edited.materialBlocks).toEqual(artifact.materialBlocks)
  })
})

it('切换功能与问题列表时更新详情，整体问题并入待确认页', () => {
  const value = structuredClone(artifact)
  value.functions.push({ id: 'F2', name: '上传', sections: [{ title: '页面入口', items: [{ text: '从任务中心进入', status: 'confirmed', materialBlockIds: ['B1'] }] }] })
  value.questions.push({ id: 'Q2', question: '总体范围？', reason: '未说明', materialBlockIds: [], functionIds: [] })
  render(<ReadableRequirementMaterial content={value} />)

  fireEvent.click(screen.getByRole('button', { name: /上传/ }))
  const functionDetail = screen.getByRole('region', { name: '功能说明详情' })
  expect(within(functionDetail).getByText('从任务中心进入')).toBeVisible()
  expect(within(functionDetail).queryByText('开启后执行处理')).not.toBeInTheDocument()

  fireEvent.click(screen.getByRole('tab', { name: /待确认/ }))
  const questionList = screen.getByRole('complementary', { name: '待确认问题列表' })
  expect(within(questionList).getByText('如何进入？')).toBeInTheDocument()
  expect(within(questionList).getByText('总体范围？')).toBeInTheDocument()
  expect(within(questionList).getByText('整体')).toBeInTheDocument()
  fireEvent.click(within(questionList).getByRole('button', { name: /总体范围/ }))
  const questionDetail = screen.getByRole('region', { name: '待确认详情' })
  expect(within(questionDetail).getByText('总体范围？')).toBeInTheDocument()
  expect(within(questionDetail).getByText('暂无材料依据')).toBeInTheDocument()
})
