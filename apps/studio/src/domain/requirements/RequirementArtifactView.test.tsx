import understandingSource from './fixtures/requirement-understanding.example.json?raw'
import extractionSource from './fixtures/document-extraction.example.json?raw'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { RequirementArtifactView } from './RequirementArtifactView'
import { parseRequirementArtifact } from './requirementArtifact'

const understanding = JSON.parse(understandingSource)
const extraction = JSON.parse(extractionSource)
afterEach(cleanup)

it('按模块和操作展示交互信息，保留未知与示例状态', async () => {
  render(<TestThemeProvider><RequirementArtifactView content={understanding} /></TestThemeProvider>)
  const user = userEvent.setup()
  const moduleButton = screen.getByRole('button', { name: /转换数据$/ })
  await user.click(moduleButton)
  const moduleItem = moduleButton.closest('.ant-collapse-item') as HTMLElement
  await user.click(within(moduleItem).getByRole('button', { name: /筛选任务列表$/ }))
  expect(within(moduleItem).getByText('操作目的')).toBeVisible()
  expect(within(moduleItem).queryByText('交互说明')).toBeNull()
  expect(screen.getByRole('heading', { name: 'UI 交互' })).toBeVisible()
  const uiEntry = screen.getByRole('button', { name: /转换数据 \/ 筛选任务列表$/ })
  expect(uiEntry).toHaveAttribute('aria-expanded', 'false')
  await user.click(uiEntry)
  expect(screen.getAllByText('待确认').length).toBeGreaterThan(0)
  await user.click(screen.getByRole('button', { name: /转换类型$/ }))
  expect(screen.getAllByText('默认值').length).toBeGreaterThan(0)
  expect(screen.getAllByText('示例').length).toBeGreaterThan(0)
  expect(screen.queryByText('artifactType')).toBeNull()
  expect(screen.queryByText('confirmationStatus')).toBeNull()
  expect(screen.queryByText('有明确依据')).toBeNull()
})

it('材料表格保留可读单元格，不把表格字段当正文', async () => {
  render(<TestThemeProvider><RequirementArtifactView content={JSON.stringify(extraction)} /></TestThemeProvider>)
  await userEvent.setup().click(screen.getByRole('button', { name: /筛选信息$/ }))
  expect(screen.getByText('实际选项、业务含义及默认值未提供')).toBeVisible()
  expect(screen.queryByText('rowSpan')).toBeNull()
})

it('旧文本由原有阅读器处理，非法新产物不会伪装成文本', () => {
  expect(parseRequirementArtifact('历史需求正文')).toBeNull()
  expect(() => parseRequirementArtifact('{"artifactType":"requirement_understanding"')).toThrow()
  render(<TestThemeProvider><RequirementArtifactView content={{ artifactType: 'requirement_understanding', schemaVersion: '9' }} /></TestThemeProvider>)
  expect(screen.getByRole('alert')).toHaveTextContent('不受支持')
})

it('已知选项用实际取值命名，保留部分选项完整性的含义', async () => {
  const artifact = structuredClone(understanding)
  const control = artifact.modules[0].operations[0].interaction.controls[0]
  const exampleFact = (value: string) => ({ value, confirmationStatus: 'example', sourceReferences: [{ sourceId: 'SRC01', locator: '合成选项示例', excerpt: null }], relatedQuestionIds: [] })
  control.options.items = [{ id: 'OPT01', value: exampleFact('任务级'), meaning: exampleFact('仅演示结构') }]
  control.options.completeness = exampleFact('partial')
  render(<TestThemeProvider><RequirementArtifactView content={artifact} /></TestThemeProvider>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /转换数据 \/ 筛选任务列表$/ }))
  await user.click(screen.getByRole('button', { name: /转换类型$/ }))
  expect(screen.getByRole('button', { name: /任务级$/ })).toBeVisible()
  expect(screen.queryByText('[object Object]')).toBeNull()
})

it('后续分支以分支条件命名，下一节点翻译为对应操作名', async () => {
  const artifact = structuredClone(understanding)
  const flow = artifact.businessFlows[0]
  flow.steps.push({ id: 'FN02', moduleId: 'M01', operationId: 'O01', nextSteps: [] })
  flow.steps[0].nextSteps.push({
    stepId: 'FN02',
    condition: { value: '设备为有直接绑定关系的设备（如遁甲）', confirmationStatus: 'confirmed', sourceReferences: [{ sourceId: 'SRC01', locator: '合成条件定位', excerpt: null }], relatedQuestionIds: [] },
    expectedBehavior: null,
    observableOutcome: null,
  })
  render(<TestThemeProvider><RequirementArtifactView content={artifact} /></TestThemeProvider>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: /筛选并观察转换任务$/ }))
  const flowItem = screen.getByRole('button', { name: /筛选并观察转换任务$/ }).closest('.ant-collapse-item') as HTMLElement
  await user.click(within(flowItem).getAllByRole('button', { name: /筛选任务列表$/ })[0])
  const branch = within(flowItem).getByRole('button', { name: /设备为有直接绑定关系的设备（如遁甲）/ })
  await user.click(branch)
  expect(within(flowItem).getByText('下一节点')).toBeVisible()
  expect(within(flowItem).queryByText('FN02')).toBeNull()
  expect(within(flowItem).getAllByText('筛选任务列表').length).toBeGreaterThan(0)
})
