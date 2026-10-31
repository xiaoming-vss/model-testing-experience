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
