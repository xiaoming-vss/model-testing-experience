import extractionSource from '@/domain/requirements/fixtures/document-extraction.example.json?raw'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, expect, it } from 'vitest'
import { RequirementMaterialComparison } from './RequirementMaterialComparison'

const extraction = JSON.parse(extractionSource)
afterEach(cleanup)
function setup(content: unknown = extraction) {
  render(<TestThemeProvider><RequirementMaterialComparison content={content} /></TestThemeProvider>)
  return { user: userEvent.setup(), facts: screen.getByRole('region', { name: '提取事实' }) }
}

it('展示全部事实，保留表格、示例和待确认含义，缺失值可以通过关联问题理解', async () => {
  const { user, facts } = setup()
  expect(within(facts).getAllByRole('button', { name: /^查看依据：/ })).toHaveLength(4)
  expect(screen.queryByRole('region', { name: '材料内容' })).not.toBeInTheDocument()
  expect(within(facts).getAllByText('示例').length).toBeGreaterThan(0)
  expect(within(facts).getByText('待确认')).toBeVisible()
  expect(within(facts).queryByText('有明确依据')).toBeNull()
  await user.type(screen.getByRole('textbox', { name: '搜索事实' }), '实际选项')
  expect(within(facts).getAllByRole('button', { name: /^查看依据：/ })).toHaveLength(1)
  expect(within(facts).getByRole('button', { name: /转换类型的实际选项及各选项业务含义/ })).toBeVisible()
})

it('事实在结果内展开依据摘录，不再切换或显示原始材料', async () => {
  const artifact = structuredClone(extraction)
  artifact.extractedFacts[1].fact.sourceReferences[0].excerpt = '保留的依据摘录'
  const { user, facts } = setup(artifact)
  const toggle = within(facts).getAllByRole('button', { name: /^查看依据：/ })[1]
  await user.click(toggle)
  expect(toggle).toHaveAttribute('aria-expanded', 'true')
  expect(within(facts).getByText('依据来源与摘录')).toBeVisible()
  expect(facts.querySelector('blockquote')).not.toBeNull()
  expect(screen.queryByRole('region', { name: '材料内容' })).not.toBeInTheDocument()
  await user.click(toggle)
  expect(toggle).toHaveAttribute('aria-expanded', 'false')
})

it('问题保留影响说明，不显示材料对照', async () => {
  const { user } = setup()
  await user.click(screen.getByText('待确认问题', { exact: true }))
  const questions = screen.getByRole('region', { name: '待确认问题' })
  await user.click(within(questions).getByRole('tab', { name: /转换类型的实际选项及各选项业务含义/ }))
  expect(within(questions).queryByText('答复')).toBeNull()
  expect(within(questions).getByText('影响的工作')).toBeVisible()
  expect(screen.queryByRole('region', { name: '材料内容' })).not.toBeInTheDocument()
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
  const entry = screen.getByRole('radio', { name: `待确认问题 ${remaining}` })
  expect(entry.closest('.ant-segmented-item')?.querySelector('.requirement-pending-questions-label')).not.toBeNull()
  await user.click(entry.closest('label')!)
  const questions = screen.getByRole('region', { name: '待确认问题' })
  expect(within(questions).queryByText(artifact.questions[0].question)).toBeNull()
  expect(questions.querySelectorAll('.ant-collapse-item')).toHaveLength(remaining)
  artifact.questions.forEach((q: { status: string }) => { q.status = 'resolved' })
  artifact.extractedFacts[0].fact.value = '上游算子为 hoi_tool'
  rerender(<TestThemeProvider><RequirementMaterialComparison content={structuredClone(artifact)} /></TestThemeProvider>)
  expect(screen.queryByText('待确认问题', { exact: true })).toBeNull()
  expect(screen.getByRole('region', { name: '提取事实' })).toBeVisible()
  expect(screen.getByText('上游算子为 hoi_tool')).toBeVisible()
  expect(screen.queryByText('已答复')).toBeNull()
})

function EditableHarness({ initial, onChange }: { initial: unknown; onChange: (content: string) => void }) {
  const [content, setContent] = useState(initial)
  return <TestThemeProvider><RequirementMaterialComparison content={content} editable
    onChange={next => { setContent(next); onChange(next) }} /></TestThemeProvider>
}

it('输入后立即卸载会提交还没到防抖时间的草稿', () => {
  let latest = ''
  const { unmount } = render(<TestThemeProvider><RequirementMaterialComparison content={extraction} editable
    onChange={next => { latest = next }} /></TestThemeProvider>)
  fireEvent.change(screen.getByRole('textbox', { name: '事实内容 EF01' }), { target: { value: '未提交草稿' } })
  unmount()
  expect(JSON.parse(latest).extractedFacts[0].fact.value).toBe('未提交草稿')
})

it('待审核时事实文本和确认状态直接可编辑并回写 JSON', async () => {
  let latest = ''
  render(<EditableHarness initial={extraction} onChange={content => { latest = content }} />)
  const user = userEvent.setup()
  const editor = screen.getByRole('textbox', { name: '事实内容 EF01' })
  await user.clear(editor)
  await user.type(editor, '数据管理 → 批量转换')
  await waitFor(() => expect(JSON.parse(latest).extractedFacts[0].fact.value).toBe('数据管理 → 批量转换'))

  await user.click(screen.getByRole('combobox', { name: '确认状态 EF01' }))
  const dropdown = document.querySelector('.ant-select-dropdown:not(.ant-select-dropdown-hidden)')
  if (!dropdown) throw new Error('确认状态选项未展开')
  await user.click(within(dropdown as HTMLElement).getByTitle('待确认'))
  expect(JSON.parse(latest).extractedFacts[0].fact.confirmationStatus).toBe('unconfirmed')
})

it('待审核时待确认问题可直接修改并回写 JSON', async () => {
  let latest = ''
  render(<EditableHarness initial={extraction} onChange={content => { latest = content }} />)
  const user = userEvent.setup()
  await user.click(screen.getByText('待确认问题', { exact: true }))
  const editor = screen.getByRole('textbox', { name: '问题内容 Q01' })
  await user.clear(editor)
  await user.type(editor, '转换类型有哪些可选项？')
  expect(JSON.parse(latest).questions[0].question).toBe('转换类型有哪些可选项？')
})

