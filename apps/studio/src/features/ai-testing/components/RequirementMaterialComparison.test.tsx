import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { RequirementMaterialComparison } from './RequirementMaterialComparison'

afterEach(cleanup)

const artifact = {
  schemaVersion: '0.2', artifactType: 'readable_requirement_material', title: '材料整理',
  sources: [{ id: 'S1', name: '需求文档', type: 'document', location: null }],
  materialBlocks: [{ id: 'B1', sourceId: 'S1', parentId: null, kind: 'paragraph', locator: '第1段', content: { text: '材料原文' } }],
  functions: [{ id: 'F1', name: '开关', sections: [{ title: '功能使用与业务规则', items: [{ text: '开启后执行处理', status: 'confirmed', materialBlockIds: ['B1'] }] }] }],
  questions: [{ id: 'Q1', question: '如何进入？', reason: '未说明', materialBlockIds: ['B1'], functionIds: ['F1'] }],
}

it('新版材料按功能展示，能按需查看原文依据', () => {
  render(<RequirementMaterialComparison content={JSON.stringify(artifact)} />)
  expect(screen.getByText('开启后执行处理')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: '开启后执行处理' }))
  expect(within(screen.getByRole('complementary', { name: '材料依据' })).getByText('材料原文')).toBeVisible()
})

it('错误格式给出可修正提示', () => {
  render(<RequirementMaterialComparison content={'{"artifactType":'} />)
  expect(screen.getByRole('alert')).toBeVisible()
})
