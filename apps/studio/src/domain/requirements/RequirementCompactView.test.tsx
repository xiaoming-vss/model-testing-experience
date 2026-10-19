import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import compact from './fixtures/requirement-understanding.example.json'
import extraction from './fixtures/document-extraction.example.json'
import { RequirementArtifactValue } from './RequirementArtifactView'
import { RequirementUnderstandingComparison } from '@/features/ai-testing/components/RequirementUnderstandingComparison'
import { TestThemeProvider } from '@/test/TestThemeProvider'

afterEach(cleanup)

it('renders compact review citations and locates original material', () => {
  render(<TestThemeProvider><RequirementUnderstandingComparison content={compact} extractionContent={extraction} /></TestThemeProvider>)
  fireEvent.click(screen.getByRole('tab', { name: '业务规则' }))
  fireEvent.click(screen.getByText(compact.businessRules[0].name))
  const evidence = compact.evidence[0]
  const source = compact.sources.find(s => s.id === evidence.sourceId)!
  const citations = screen.getAllByRole('button', { name: `${source.name} · ${evidence.locator}` })
  fireEvent.click(citations[0])
  expect(screen.queryByText('需求理解缺少集中证据表')).not.toBeInTheDocument()
  expect(screen.getByRole('region', { name: '材料与需求理解对照' })).toBeInTheDocument()
})

it('renders rule-based flow conditions with expandable business meaning', async () => {
  const rule = compact.businessRules[0]
  render(<TestThemeProvider><RequirementArtifactValue artifact={compact} value={[rule.id]} field="conditionRuleIds" /></TestThemeProvider>)
  expect(screen.getByText(rule.name, { selector: 'summary' })).toBeInTheDocument()
  fireEvent.click(screen.getByLabelText(`查看规则：${rule.name}`))
  expect(await screen.findByText(rule.expectedBehavior[0].value!)).toBeVisible()
  expect(screen.queryByText('conditionRuleIds')).not.toBeInTheDocument()
  expect(screen.queryByText('evidenceIds')).not.toBeInTheDocument()
})

it('opens operation rule references and retains their evidence', async () => {
  const rule = compact.businessRules[0]
  const locate = vi.fn()
  render(<TestThemeProvider><RequirementArtifactValue artifact={compact} value={[rule.id]} field="ruleIds" onSourceReference={locate} /></TestThemeProvider>)
  const summary = screen.getByLabelText(`查看规则：${rule.name}`)
  expect(summary.closest('details')).not.toHaveAttribute('open')
  fireEvent.click(summary)
  expect(summary.closest('details')).toHaveAttribute('open')
  expect(await screen.findByText(rule.expectedBehavior[0].value!)).toBeVisible()
  fireEvent.click(screen.getAllByRole('button', { name: /示例输入约定/ })[0])
  expect(locate).toHaveBeenCalledWith({ sourceId: 'SRC01', locator: '示例输入约定', excerpt: null })
})

it('names rule-based branches and shows an explicit end instead of unknown', () => {
  const rule = compact.businessRules[0]
  render(<TestThemeProvider><RequirementArtifactValue artifact={compact} value={[{ stepId: null, conditionRuleIds: [rule.id] }]} field="nextSteps" /></TestThemeProvider>)
  fireEvent.click(screen.getByRole('button', { name: new RegExp(rule.name) }))
  expect(screen.getByText('流程结束')).toBeVisible()
  expect(screen.queryByText('未明确')).not.toBeInTheDocument()
})

it('keeps narrative strings, omits absent fields and preserves explicit unknown facts', () => {
  const artifact = JSON.parse(JSON.stringify(compact))
  artifact.modules[0].purpose = '查看并筛选任务'
  artifact.modules[0].operations[0].goal = '按条件查找任务'
  delete artifact.modules[0].operations[0].interaction.pagination
  artifact.modules[0].operations[0].interaction.sorting = { value: null, confirmationStatus: 'unconfirmed' }
  const control = artifact.modules[0].operations[0].interaction.controls[0]
  control.defaultValue = { value: null, confirmationStatus: 'unconfirmed' }
  const saved = JSON.stringify(artifact)
  render(<TestThemeProvider><RequirementUnderstandingComparison content={artifact} extractionContent={extraction} /></TestThemeProvider>)
  expect(screen.getByText('查看并筛选任务')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: 'UI 交互' }))
  // 控件、触发反馈与操作步骤均默认折叠，展开后才挂载对应事实。
  const understanding = within(screen.getByRole('region', { name: '需求理解内容' }))
  fireEvent.click(understanding.getByText('转换类型'))
  fireEvent.click(understanding.getByText('触发与反馈'))
  fireEvent.click(understanding.getByText('操作步骤与关联规则'))
  expect(understanding.getByText('按条件查找任务')).toBeVisible()
  expect(understanding.queryByText('分页')).not.toBeInTheDocument()
  expect(understanding.getByText('排序')).toBeVisible()
  expect(understanding.getAllByText('默认值')).toHaveLength(1)
  expect(understanding.getAllByText('待确认').length).toBeGreaterThan(0)
  expect(JSON.stringify(artifact)).toBe(saved)
})
