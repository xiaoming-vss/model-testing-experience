import understandingSource from '@/domain/requirements/fixtures/requirement-understanding.example.json?raw'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'
import { RequirementUnderstandingComparison } from './RequirementUnderstandingComparison'

const understanding = JSON.parse(understandingSource)
afterEach(cleanup)
function setup(content: unknown = understanding, selectFirst = true) {
  render(<TestThemeProvider><RequirementUnderstandingComparison content={content} /></TestThemeProvider>)
  const firstCard = screen.queryByRole('list', { name: '业务模块导航' })?.querySelector('button')
  if (selectFirst && firstCard) fireEvent.click(firstCard)
  return userEvent.setup()
}

function expandUiDetails() {
  screen.getByRole('region', { name: '需求理解内容' }).querySelectorAll('.requirement-ui-control:not([open]) > summary').forEach(summary => fireEvent.click(summary))
}

it('默认需求解析提供流程和规则，模块详情与分类保留示例和未知状态', async () => {
  const user = setup()
  expect(screen.getByRole('tab', { name: '需求解析' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('heading', { name: '业务模块' })).toBeVisible()
  expect(screen.getByRole('heading', { name: '关联业务规则' })).toBeVisible()
  expect(screen.queryByRole('tab', { name: '模块与操作' })).toBeNull()
  const right = screen.getByRole('region', { name: '需求理解内容' })
  expect(within(right).getByRole('region', { name: '模块操作详情' })).toBeVisible()
  expect(within(right).getAllByText('操作目的').some(element => element.closest('details')?.open ?? true)).toBe(true)
  expect(within(right).getAllByText('示例').length).toBeGreaterThan(0)
  await user.click(screen.getByRole('tab', { name: '功能概况' }))
  expect(within(right).getByText('适用范围')).toBeVisible()
  await user.click(screen.getByRole('tab', { name: '业务规则' }))
  expect(within(right).getByText('设置条件并刷新查询')).toBeVisible()
  await user.click(screen.getByRole('tab', { name: /待确认问题/ }))
  expect(within(right).getByText('转换类型的实际选项及各选项业务含义是什么？')).toBeVisible()
})

it('只展示需求理解结果，不再提供原始材料、提取事实或显隐入口', () => {
  setup()
  expect(screen.getByRole('region', { name: '需求理解结果' })).toBeVisible()
  expect(screen.queryByRole('region', { name: '材料内容' })).not.toBeInTheDocument()
  expect(screen.queryByText('提取事实', { exact: true })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /材料／依据/ })).not.toBeInTheDocument()
})

it('仅展示未解决问题和计数，全部解决后隐藏分类并回到模块正文', async () => {
  const artifact = structuredClone(understanding)
  artifact.questions[0].status = 'resolved'
  const remaining = artifact.questions.filter((q: { status: string }) => q.status === 'open').length
  const { rerender } = render(<TestThemeProvider><RequirementUnderstandingComparison content={artifact} /></TestThemeProvider>)
  const user = userEvent.setup()
  expect(screen.getByRole('tab', { name: `待确认问题 ${remaining}` })).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: /待确认问题/ }))
  expect(within(screen.getByRole('region', { name: '需求理解内容' })).queryByText(artifact.questions[0].question)).toBeNull()
  expect(screen.getByText(`${remaining} 条`)).toBeVisible()
  artifact.questions.forEach((q: { status: string }) => { q.status = 'resolved' })
  artifact.modules[0].operations[0].goal.value = '上游算子为 hoi_tool'
  rerender(<TestThemeProvider><RequirementUnderstandingComparison content={structuredClone(artifact)} /></TestThemeProvider>)
  expect(screen.queryByRole('tab', { name: /待确认问题/ })).toBeNull()
  expect(screen.queryByRole('tab', { name: '模块与操作' })).toBeNull()
  expect(screen.getByRole('tab', { name: '需求解析' })).toHaveAttribute('aria-selected', 'true')
  await user.click(screen.getByRole('button', { name: artifact.modules[0].name }))
  expect(within(screen.getByRole('region', { name: '模块操作详情' })).getByText('上游算子为 hoi_tool')).toBeVisible()
})


it('独立 UI 页签手动展开控件、选项和未知状态，保留来源文本且原始数据不变', async () => {
  const result = structuredClone(understanding)
  const snapshot = JSON.stringify(result)
  const user = setup(result)
  await user.click(screen.getByRole('tab', { name: 'UI 交互' }))
  expandUiDetails()
  const right = screen.getByRole('region', { name: '需求理解内容' })
  expect(within(right).getByText('控件与字段')).toBeVisible()
  expect(within(right).getAllByText('转换类型').length).toBeGreaterThan(0)
  expect(within(right).queryByText('默认值')).toBeNull()
  expect(within(right).getAllByText('待确认').length).toBeGreaterThan(0)
  expect(within(right).getAllByText('示例').length).toBeGreaterThan(0)
  expect(within(right).getByText('触发方式')).toBeVisible()
  expect(within(right).queryByText('条件联动')).toBeNull()
  expect(within(right).queryByText('校验与反馈')).toBeNull()
  expect(within(right).getAllByText(/转换任务列表：合成演示输入/).length).toBeGreaterThan(0)
  expect(screen.queryByRole('region', { name: '材料内容' })).not.toBeInTheDocument()
  expect(JSON.stringify(result)).toBe(snapshot)
})

it('UI 页签默认选择有控件记录的模块，也允许查看无控件操作和缺少交互的记录', async () => {
  const result = structuredClone(understanding)
  const backend = structuredClone(result.modules[0])
  backend.id='BACKEND'; backend.name='后台处理'; backend.operations.forEach((o: { id: string; name: string; interaction: { controls: unknown[] } })=>{o.id='BACKGROUND';o.name='后台任务';o.interaction.controls=[]})
  result.modules.unshift(backend)
  const noControl = structuredClone(result.modules[1].operations[0])
  noControl.id='NO_CONTROLS';noControl.name='查看结果';noControl.interaction.controls=[]
  result.modules[1].operations.push(noControl)
  const user=setup(result)
  await user.click(screen.getByRole('tab', { name:'UI 交互' }))
  expandUiDetails()
  const right=screen.getByRole('region', { name:'需求理解内容' })
  expect(within(right).getByRole('combobox', { name:'选择操作' })).toBeVisible()
  expect(within(right).queryByText('后台任务',{exact:true})).toBeNull()
  await user.click(within(right).getByRole('combobox',{name:'选择操作'}))
  await user.click(screen.getByText('查看结果',{exact:true}))
  expandUiDetails()
  expect(within(right).getByText('暂无控件记录')).toBeVisible()
  expect(within(right).getByText('触发方式')).toBeVisible()
})

it('没有模块时 UI 页签显示缺少交互记录，不推断产品没有控件', async () => {
  const result=structuredClone(understanding);result.modules=[]
  const user=setup(result)
  await user.click(screen.getByRole('tab',{name:'UI 交互'}))
  expandUiDetails()
  expect(screen.getByRole('region',{name:'需求理解内容'})).toHaveTextContent('暂无可查看的操作交互记录')
})


it('UI 选项和状态直接呈现，保留零值、否值与冲突且不升级示例', async () => {
  const result=structuredClone(understanding)
  const control=result.modules[0].operations[0].interaction.controls[0]
  const fact=structuredClone(control.label)
  control.options.items=[{id:'ZERO',value:{...fact,value:0},businessMeaning:{...fact,value:'零选项'}},{id:'FALSE',value:{...fact,value:false},meaning:{...fact,value:'否选项'}}]
  control.options.completeness={...fact,value:'partial',confirmationStatus:'conflicting',relatedQuestionIds:['Q01']}
  const user=setup(result)
  await user.click(screen.getByRole('tab',{name:'UI 交互'}))
  expandUiDetails()
  const details=screen.getByRole('region',{name:'UI 控件详情'})
  expect(within(details).getByText('零选项')).toBeVisible()
  expect(within(details).getByText('否选项')).toBeVisible()
  expect(within(details).getAllByText('0').length).toBeGreaterThan(0)
  expect(within(details).getAllByText('false').length).toBeGreaterThan(0)
  expect(within(details).getByText('存在冲突')).toBeVisible()
  expect(within(details).getByText('部分已知')).toBeVisible()
  expect(within(details).queryByText('有明确依据')).toBeNull()
})


it('模块操作仅保留业务内容，并可跳转到指定操作的唯一交互展示', async () => {
  const result=structuredClone(understanding)
  const other=structuredClone(result.modules[0].operations[0])
  other.id='RESULT_VIEW';other.name='查看结果';other.interaction.controls=[]
  result.modules[0].operations.push(other)
  const original=JSON.stringify(result)
  const user=setup(result)
  const right=screen.getByRole('region',{name:'需求理解内容'})
  expect(within(right).getAllByText('操作目的').some(element => element.closest('details')?.open ?? true)).toBe(true)
  expect(within(right).queryByText('交互说明')).toBeNull()
  expect(within(right).queryByText('默认值')).toBeNull()
  await user.click(within(right).getByRole('tab',{name:/查看结果/}))
  await user.click(within(right).getByRole('button',{name:'查看 UI 交互：转换数据 / 查看结果'}))
  expandUiDetails()
  expect(screen.getByRole('tab',{name:'UI 交互'})).toHaveAttribute('aria-selected','true')
  expect(within(right).getByText('转换数据 / 查看结果',{exact:true})).toBeVisible()
  expect(within(right).getByText('暂无控件记录')).toBeVisible()
  expect(within(right).getByText('触发方式')).toBeVisible()
  expect(JSON.stringify(result)).toBe(original)
})


it('解析页隐藏模块下拉框，点击卡片保持当前分类且不改写数据', async () => {
  const result = structuredClone(understanding)
  result.businessRules.push({ ...result.businessRules[0], id: 'UNRELATED', name: '不相关模块规则', moduleIds: ['OTHER'], operationIds: [] })
  const snapshot = JSON.stringify(result)
  const user = setup(result)
  const right = screen.getByRole('region', { name: '需求理解内容' })
  expect(within(right).queryByText('不相关模块规则')).toBeNull()
  expect(within(right).getByTitle('设置条件并刷新查询')).toBeVisible()
  await user.click(within(right).getByRole('button', { name: result.modules[0].name }))
  await user.click(within(right).getByRole('button', { name: result.modules[0].name }))
  expect(screen.getByRole('tab', { name: '需求解析' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.queryByRole('combobox', { name: '业务模块' })).toBeNull()
  expect(within(right).getByRole('button', { name: result.modules[0].name })).toHaveAttribute('aria-pressed', 'true')
  expect(JSON.stringify(result)).toBe(snapshot)
})

it('卡片直接取全部模块并保持顺序，不受流程重复或缺失步骤影响', async () => {
  const result = structuredClone(understanding)
  const other = structuredClone(result.modules[0])
  other.id = 'OTHER'
  other.name = '后续模块'
  other.purpose.value = '后续模块独有说明'
  other.operations[0].ruleIds = []
  other.operations[0].id = 'NEXT'
  other.operations[0].name = '处理后续记录'
  result.modules.push(other)
  result.businessRules.push({ ...result.businessRules[0], id: 'NEXT_RULE', name: '后续模块规则', moduleIds: ['OTHER'], operationIds: ['NEXT'] })
  const step = { ...result.businessFlows[0].steps[0], moduleId: 'OTHER', operationId: 'NEXT' }
  result.businessFlows[0].steps = [{ ...step, id: 'NEXT1' }, { ...step, id: 'NEXT2' }]
  const snapshot = JSON.stringify(result)
  const user = setup(result)
  const right = screen.getByRole('region', { name: '需求理解内容' })
  const navigation = within(right).getByRole('list', { name: '业务模块导航' })
  expect(within(navigation).getAllByRole('button').map(button => button.getAttribute('aria-label'))).toEqual(result.modules.map((module: { name: string }) => module.name))
  await user.click(within(right).getByRole('button', { name: '后续模块' }))
  expect(screen.getByRole('tab', { name: '需求解析' })).toHaveAttribute('aria-selected', 'true')
  expect(within(right).getByText('后续模块独有说明', { selector: 'p' })).toBeVisible()
  expect(within(right).getByText('后续模块', { selector: 'summary' }).closest('details')).toHaveAttribute('open')
  expect(within(right).getAllByText('操作目的').some(element => element.closest('details')?.open ?? true)).toBe(true)
  expect(within(right).getByTitle('后续模块规则')).toBeVisible()
  expect(within(right).getByRole('button', { name: '后续模块' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.queryByRole('combobox', { name: '业务模块' })).toBeNull()
  expect(JSON.stringify(result)).toBe(snapshot)
})

it('规则摘要不借用另一条预期的引用，展开后仍能核对该条预期', async () => {
  const result = structuredClone(understanding)
  const rule = result.businessRules[0]
  rule.expectedBehavior[0].evidenceIds = []
  result.evidence.push({ id: 'EV_SECOND', sourceId: 'SRC01', locator: '仅第二项依据' })
  rule.expectedBehavior.push({ ...rule.expectedBehavior[0], value: '第二条预期', evidenceIds: ['EV_SECOND'] })
  const user = setup(result)
  const right = screen.getByRole('region', { name: '需求理解内容' })
  expect(within(right).getByText(/仅第二项依据/)).not.toBeVisible()
  await user.click(within(right).getByTitle(rule.name))
  expect(within(right).getByText(/仅第二项依据/)).toBeVisible()
})


it('默认显示全部模块，卡片单选过滤，再次点击取消并恢复全部', async () => {
  const result = structuredClone(understanding)
  result.modules.push({ ...structuredClone(result.modules[0]), id: 'OTHER', name: '另一个模块' })
  const user = setup(result, false)
  const navigation = screen.getByRole('list', { name: '业务模块导航' })
  const operations = screen.getByRole('region', { name: '模块操作详情' })
  const cards = within(navigation).getAllByRole('button')
  expect(cards.every(card => card.getAttribute('aria-pressed') === 'false')).toBe(true)
  expect(operations.querySelectorAll('.requirement-operation-module')).toHaveLength(2)
  await user.click(cards[0])
  expect(cards[0]).toHaveAttribute('aria-pressed', 'true')
  expect(operations.querySelectorAll('.requirement-operation-module')).toHaveLength(1)
  expect(within(operations).queryByText('另一个模块')).toBeNull()
  await user.click(cards[1])
  expect(cards[0]).toHaveAttribute('aria-pressed', 'false')
  expect(cards[1]).toHaveAttribute('aria-pressed', 'true')
  expect(operations.querySelectorAll('.requirement-operation-module')).toHaveLength(1)
  await user.click(cards[1])
  expect(cards.every(card => card.getAttribute('aria-pressed') === 'false')).toBe(true)
  expect(operations.querySelectorAll('.requirement-operation-module')).toHaveLength(2)
  expect(screen.getByRole('tab', { name: '需求解析' })).toHaveAttribute('aria-selected', 'true')
})

it('UI 控件和操作详情默认折叠，点击标题可展开再收起', async () => {
  const user = setup()
  await user.click(screen.getByRole('tab', { name: 'UI 交互' }))
  const right = screen.getByRole('region', { name: '需求理解内容' })
  const groups = Array.from(right.querySelectorAll('.requirement-ui-control'))
  expect(groups.length).toBeGreaterThan(0)
  expect(groups.every(group => !group.hasAttribute('open'))).toBe(true)
  fireEvent.click(groups[0].querySelector('summary')!)
  expect(groups[0]).toHaveAttribute('open')
  fireEvent.click(groups[0].querySelector('summary')!)
  expect(groups[0]).not.toHaveAttribute('open')
})

it.each(['', '   ', null, undefined])('没有产物内容时保持空白，不显示解析错误：%s', content => {
  render(<TestThemeProvider><RequirementUnderstandingComparison content={content} /></TestThemeProvider>)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.queryByRole('region', { name: '需求理解结果' })).not.toBeInTheDocument()
})

it('有内容但结构不完整时仍提示修正原始 JSON', () => {
  const incomplete = structuredClone(understanding)
  delete incomplete.functionalOverview
  render(<TestThemeProvider><RequirementUnderstandingComparison content={incomplete} /></TestThemeProvider>)
  expect(screen.getByRole('alert')).toHaveTextContent('当前内容不是完整的需求理解 JSON，请在原始 JSON 中修正')
})
