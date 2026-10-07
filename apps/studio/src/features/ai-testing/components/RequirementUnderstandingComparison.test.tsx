import extractionSource from '@/domain/requirements/fixtures/document-extraction.example.json?raw'
import understandingSource from '@/domain/requirements/fixtures/requirement-understanding.example.json?raw'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'
import { RequirementUnderstandingComparison } from './RequirementUnderstandingComparison'

const extraction = JSON.parse(extractionSource), understanding = JSON.parse(understandingSource)
afterEach(cleanup)
function setup(content: unknown = understanding, upstream: unknown = extraction) {
  render(<TestThemeProvider><RequirementUnderstandingComparison content={content} extractionContent={upstream} /></TestThemeProvider>)
  return userEvent.setup()
}

it('默认显示模块与操作，五个分类可读且保留示例和未知状态', async () => {
  const user = setup()
  expect(screen.getByRole('tab', { name: '模块与操作' })).toHaveAttribute('aria-selected', 'true')
  const right = screen.getByRole('region', { name: '需求理解内容' })
  expect(within(right).getByRole('heading', { name: '转换数据' })).toBeVisible()
  expect(within(right).getByText('操作目的')).toBeVisible()
  expect(within(right).getAllByText('示例').length).toBeGreaterThan(0)
  await user.click(screen.getByRole('tab', { name: '功能概况' }))
  expect(within(right).getByText('适用范围')).toBeVisible()
  await user.click(screen.getByRole('tab', { name: '业务规则' }))
  expect(within(right).getByText('设置条件并刷新查询')).toBeVisible()
  await user.click(screen.getByRole('tab', { name: '待确认问题' }))
  expect(within(right).getByText('转换类型的实际选项及各选项业务含义是什么？')).toBeVisible()
})

it('点击说明中的依据能切换来源并显示对应图片文字', async () => {
  const upstream = structuredClone(extraction), result = structuredClone(understanding)
  const source = { id: 'SRC02', name: '第二张图', type: 'prototype', location: null, version: null }
  upstream.sources.push(source); result.sources.push(source)
  upstream.contentBlocks.push({ ...upstream.contentBlocks[1], id: 'B04', kind: 'image', text: null, image: { visibleTexts: ['可见控件A'], meaning: '界面说明' }, sourceReferences: [{ sourceId: 'SRC02', locator: '页面二', excerpt: null }] })
  result.modules[0].operations[0].goal.sourceReferences = [{ sourceId: 'SRC02', locator: '页面二', excerpt: '可见控件A' }]
  const user = setup(result, upstream)
  await user.click(within(screen.getByRole('region', { name: '需求理解内容' })).getByRole('button', { name: '第二张图 · 页面二' }))
  const left = screen.getByRole('region', { name: '材料内容' })
  expect(within(within(left).getByRole('article', { name: '页面二' })).getByText('可见控件A')).toBeVisible()
  expect(within(left).getByText('关联依据')).toBeVisible()
  expect(within(left).getByText('依据定位')).toBeVisible()
})

it('上游提取事实仍保留未确认信息，不被阶段审核升级成已确认', async () => {
  const user = setup()
  await user.click(screen.getByText('提取事实', { exact: true }))
  const left = screen.getByRole('region', { name: '已审核提取事实' })
  expect(within(left).getByText('待确认')).toBeVisible()
  expect(within(left).queryByText('有明确依据')).toBeNull()
})

it('缺少上游时仍可查看理解内容和新补充来源，不编造材料块', async () => {
  const result = structuredClone(understanding)
  result.sources.push({ id: 'SRC02', name: '业务确认', type: 'user_confirmation', location: null, version: null })
  result.modules[0].operations[0].goal.sourceReferences = [{ sourceId: 'SRC02', locator: '本次答复', excerpt: '只需手动刷新' }]
  const user = setup(result, null)
  const right = screen.getByRole('region', { name: '需求理解内容' })
  expect(within(right).getByText('操作目的')).toBeVisible()
  await user.click(within(right).getByRole('button', { name: '业务确认 · 本次答复' }))
  const left = screen.getByRole('region', { name: '材料内容' })
  expect(within(left).getByText('只需手动刷新')).toBeVisible()
  expect(within(left).queryByText('关联依据')).toBeNull()
  expect(within(left).getByText(/没有可用的材料提取记录/)).toBeVisible()
})


it('仅展示未解决问题和计数，全部解决后隐藏分类并回到模块正文', async () => {
  const artifact = structuredClone(understanding)
  artifact.questions[0].status = 'resolved'
  const remaining = artifact.questions.filter((q: { status: string }) => q.status === 'open').length
  const { rerender } = render(<TestThemeProvider><RequirementUnderstandingComparison content={artifact} extractionContent={extraction} /></TestThemeProvider>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('tab', { name: '待确认问题' }))
  expect(within(screen.getByRole('region', { name: '需求理解内容' })).queryByText(artifact.questions[0].question)).toBeNull()
  expect(screen.getByText(`${remaining} 条`)).toBeVisible()
  artifact.questions.forEach((q: { status: string }) => { q.status = 'resolved' })
  artifact.modules[0].operations[0].goal.value = '上游算子为 hoi_tool'
  rerender(<TestThemeProvider><RequirementUnderstandingComparison content={structuredClone(artifact)} extractionContent={extraction} /></TestThemeProvider>)
  expect(screen.queryByRole('tab', { name: '待确认问题' })).toBeNull()
  expect(screen.getByRole('tab', { name: '模块与操作' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByText('上游算子为 hoi_tool')).toBeVisible()
})


it('独立 UI 页签直接展开控件、选项和未知状态，引用可定位材料且原始数据不变', async () => {
  const result = structuredClone(understanding)
  const snapshot = JSON.stringify(result)
  const user = setup(result)
  await user.click(screen.getByRole('tab', { name: 'UI 交互' }))
  const right = screen.getByRole('region', { name: '需求理解内容' })
  expect(within(right).getByText('控件与字段')).toBeVisible()
  expect(within(right).getAllByText('转换类型').length).toBeGreaterThan(0)
  expect(within(right).getAllByText('默认值')).toHaveLength(2)
  expect(within(right).getAllByText('待确认').length).toBeGreaterThan(0)
  expect(within(right).getAllByText('示例').length).toBeGreaterThan(0)
  expect(within(right).getByText('触发方式')).toBeVisible()
  expect(within(right).getByText('条件联动')).toBeVisible()
  expect(within(right).getByText('校验与反馈')).toBeVisible()
  await user.click(within(right).getAllByRole('button', { name: /转换任务列表：合成演示输入/ })[0])
  expect(screen.getByRole('region', { name: '材料内容' })).toHaveTextContent('依据定位')
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
  const right=screen.getByRole('region', { name:'需求理解内容' })
  expect(within(right).getByRole('combobox', { name:'UI 所属模块' })).toBeVisible()
  expect(within(right).queryByText('后台任务',{exact:true})).toBeNull()
  await user.click(within(right).getByRole('combobox',{name:'UI 所属操作'}))
  await user.click(screen.getByText('查看结果',{exact:true}))
  expect(within(right).getByText('暂无控件记录')).toBeVisible()
  expect(within(right).getByText('触发方式')).toBeVisible()
})

it('没有模块时 UI 页签显示缺少交互记录，不推断产品没有控件', async () => {
  const result=structuredClone(understanding);result.modules=[]
  const user=setup(result)
  await user.click(screen.getByRole('tab',{name:'UI 交互'}))
  expect(screen.getByRole('region',{name:'需求理解内容'})).toHaveTextContent('暂无可查看的操作交互记录')
})


it('UI 选项和状态直接呈现，保留零值、否值与冲突且不升级示例', async () => {
  const result=structuredClone(understanding)
  const control=result.modules[0].operations[0].interaction.controls[0]
  const fact=structuredClone(control.label)
  control.options.items=[{id:'ZERO',value:{...fact,value:0},businessMeaning:{...fact,value:'零选项'}},{id:'FALSE',value:{...fact,value:false},businessMeaning:{...fact,value:'否选项'}}]
  control.options.completeness={...fact,value:'partial',confirmationStatus:'conflicting',relatedQuestionIds:['Q01']}
  const user=setup(result)
  await user.click(screen.getByRole('tab',{name:'UI 交互'}))
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
  expect(within(right).getByText('操作目的')).toBeVisible()
  expect(within(right).queryByText('交互说明')).toBeNull()
  expect(within(right).queryByText('默认值')).toBeNull()
  await user.click(within(right).getByRole('tab',{name:/查看结果/}))
  await user.click(within(right).getByRole('button',{name:'查看 UI 交互：转换数据 / 查看结果'}))
  expect(screen.getByRole('tab',{name:'UI 交互'})).toHaveAttribute('aria-selected','true')
  expect(within(right).getByText('查看结果',{exact:true})).toBeVisible()
  expect(within(right).getByText('暂无控件记录')).toBeVisible()
  expect(within(right).getByText('触发方式')).toBeVisible()
  expect(JSON.stringify(result)).toBe(original)
})
