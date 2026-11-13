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
  it('显示功能说明和待确认问题，并能查看材料依据', () => {
    render(<ReadableRequirementMaterial content={artifact} />)
    expect(screen.getByText('开启后执行处理')).toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('navigation', { name: '功能和章节导航' })).getByRole('button', { name: /待确认问题/ }))
    expect(screen.getByText('如何进入？')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '如何进入？' }))
    const evidence = within(screen.getByRole('complementary', { name: '材料依据' }))
    expect(evidence.getByText('材料原文')).toBeInTheDocument()
    expect(evidence.getByText('第1段')).toBeInTheDocument()
  })
  it('编辑时保留 JSON 其他内容', () => {
    const onChange = vi.fn()
    render(<ReadableRequirementMaterial content={artifact} editable onChange={onChange} />)
    fireEvent.click(screen.getByRole('textbox', { name: '开关 功能使用与业务规则 内容 1' }))
    expect(within(screen.getByRole('complementary', { name: '材料依据' })).getByText('材料原文')).toBeVisible()
    fireEvent.change(screen.getByRole('textbox', { name: '开关 功能使用与业务规则 内容 1' }), { target: { value: '修改后说明' } })
    const result = JSON.parse(onChange.mock.lastCall![0])
    expect(result.functions[0].sections[0].items[0].text).toBe('修改后说明')
    expect(result.materialBlocks).toEqual(artifact.materialBlocks)
  })
})

it('只显示当前功能有内容的统一分类，整体问题独立展示', () => {
  const value = structuredClone(artifact)
  value.functions.push({ id: 'F2', name: '上传', sections: [{ title: '页面入口', items: [{ text: '从任务中心进入', status: 'confirmed', materialBlockIds: ['B1'] }] }] })
  value.questions.push({ id: 'Q2', question: '总体范围？', reason: '未说明', materialBlockIds: [], functionIds: [] })
  render(<ReadableRequirementMaterial content={value} />)
  const nav = within(screen.getByRole('navigation', { name: '功能和章节导航' }))
  expect(nav.queryByRole('button', { name: /页面入口/ })).not.toBeInTheDocument()
  fireEvent.click(nav.getByRole('button', { name: '上传' }))
  expect(screen.getByText('从任务中心进入')).toBeVisible()
  expect(nav.getByRole('button', { name: /页面入口/ })).toBeVisible()
  expect(nav.queryByRole('button', { name: /功能使用与业务规则/ })).not.toBeInTheDocument()
  expect(nav.queryByRole('button', { name: /待确认问题/ })).not.toBeInTheDocument()
  fireEvent.click(nav.getByRole('button', { name: /整体待确认/ }))
  expect(screen.getByText('总体范围？')).toBeVisible()
  expect(screen.queryByText('如何进入？')).not.toBeInTheDocument()
})
