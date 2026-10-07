import extractionSource from '@/domain/requirements/fixtures/document-extraction.example.json?raw'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'
import { RequirementMaterialComparison } from './RequirementMaterialComparison'

const extraction = JSON.parse(extractionSource)
afterEach(cleanup)
function setup(content: unknown = extraction) {
  render(<TestThemeProvider><RequirementMaterialComparison content={content} /></TestThemeProvider>)
  return { user: userEvent.setup(), materials: screen.getByRole('region', { name: '材料内容' }), facts: screen.getByRole('region', { name: '提取事实' }) }
}

it('展示全部事实，保留表格、示例和待确认含义，缺失值可以通过关联问题理解', async () => {
  const { user, materials, facts } = setup()
  expect(within(facts).getAllByRole('button', { name: /^定位材料：/ })).toHaveLength(4)
  expect(within(materials).getByRole('cell', { name: '实际选项、业务含义及默认值未提供' })).toBeVisible()
  expect(within(facts).getAllByText('示例').length).toBeGreaterThan(0)
  expect(within(facts).getByText('待确认')).toBeVisible()
  expect(within(facts).queryByText('有明确依据')).toBeNull()
  await user.type(screen.getByRole('textbox', { name: '搜索事实' }), '实际选项')
  expect(within(facts).getAllByRole('button', { name: /^定位材料：/ })).toHaveLength(1)
  expect(within(facts).getByRole('button', { name: /转换类型的实际选项及各选项业务含义/ })).toBeVisible()
})

it('选择引用另一来源的事实后，切换材料并突出对应块，图片文字不丢失', async () => {
  const artifact = structuredClone(extraction)
  artifact.sources.push({ id: 'SRC02', name: '原型A', type: 'prototype', location: null, version: null })
  artifact.contentBlocks.push({ ...artifact.contentBlocks[1], id: 'B04', kind: 'image', text: null, image: { visibleTexts: ['原型可见控件'], meaning: '预览面板' }, sourceReferences: [{ sourceId: 'SRC02', locator: '第2张原型', excerpt: null }] })
  artifact.extractedFacts[1].relatedBlockIds = ['B04']
  artifact.extractedFacts[1].fact.sourceReferences = [{ sourceId: 'SRC02', locator: '第2张原型', excerpt: '转换类型' }]
  const { user, materials, facts } = setup(artifact)
  await user.click(within(facts).getByRole('button', { name: '定位材料：转换类型' }))
  expect(within(materials).getByRole('heading', { name: '原型A' })).toBeVisible()
  expect(within(materials).getByText('原型可见控件')).toBeVisible()
  expect(within(materials).getByText('关联依据')).toBeVisible()
  expect(within(materials).queryByText('示例入口：数据管理 → 转换数据。设置条件并刷新；列表展示转换任务 ID、转换类型、状态等字段。')).toBeNull()
  expect(within(facts).getByRole('button', { name: '原型A' })).toBeVisible()
})

it('问题可查看答复与影响，并定位关联事实对应的材料', async () => {
  const { user, materials } = setup()
  await user.click(screen.getByText('待确认问题', { exact: true }))
  const questions = screen.getByRole('region', { name: '待确认问题' })
  await user.click(within(questions).getByRole('tab', { name: /转换类型的实际选项及各选项业务含义/ }))
  expect(within(questions).queryByText('答复')).toBeNull()
  expect(within(questions).getByText('影响的工作')).toBeVisible()
  expect(within(materials).getByText('关联依据')).toBeVisible()
  expect(within(questions).queryByRole('textbox')).toBeNull()
})

it('非法 JSON 或缺少事实结构时显示可修正错误', () => {
  const { rerender } = render(<RequirementMaterialComparison content='{ "artifactType": "document_extraction"' />)
  expect(screen.getByRole('alert')).toHaveTextContent('原始 JSON')
  rerender(<RequirementMaterialComparison content={{ ...extraction, extractedFacts: [null] }} />)
  expect(screen.getByRole('alert')).toHaveTextContent('原始 JSON')
  rerender(<RequirementMaterialComparison content={{ ...extraction, sources: [{ ...extraction.sources[0], version: { invalid: true } }] }} />)
  expect(screen.getByRole('alert')).toHaveTextContent('原始 JSON')
})


it('待确认分类仅显示剩余缺口，全部解决后自动回到事实并隐藏分类', async () => {
  const artifact = structuredClone(extraction)
  artifact.questions[0].status = 'resolved'
  const remaining = artifact.questions.filter((q: { status: string }) => q.status === 'open').length
  const { rerender } = render(<TestThemeProvider><RequirementMaterialComparison content={artifact} /></TestThemeProvider>)
  const user = userEvent.setup()
  await user.click(screen.getByText('待确认问题', { exact: true }))
  const questions = screen.getByRole('region', { name: '待确认问题' })
  expect(within(questions).queryByText(artifact.questions[0].question)).toBeNull()
  expect(screen.getByText(`${remaining} 个待确认问题`)).toBeVisible()
  artifact.questions.forEach((q: { status: string }) => { q.status = 'resolved' })
  artifact.extractedFacts[0].fact.value = '上游算子为 hoi_tool'
  rerender(<TestThemeProvider><RequirementMaterialComparison content={structuredClone(artifact)} /></TestThemeProvider>)
  expect(screen.queryByText('待确认问题', { exact: true })).toBeNull()
  expect(screen.getByRole('region', { name: '提取事实' })).toBeVisible()
  expect(screen.getByText('上游算子为 hoi_tool')).toBeVisible()
  expect(screen.queryByText('已答复')).toBeNull()
})
