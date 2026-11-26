import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HistoricalRelationView } from './index'
import { analysis, emptyAnalysis, frozenInput } from './__fixtures__/historicalRelation'

const options = vi.hoisted(() => ({
  names: new Map([['req-old', '登录失败次数与锁定规则'], ['req-mid', '登录异常审计记录']]),
  sprints: new Map([['req-old', 'sprint-1'], ['req-mid', 'sprint-2']]),
  sprintNames: new Map([['sprint-1', '第 18 迭代'], ['sprint-2', '第 19 迭代']]),
}))

vi.mock('@/domain/projects/hooks/useProjectRequirementOptions', () => ({
  useProjectRequirementOptions: () => ({
    requirementNameMap: options.names,
    requirementSprintMap: options.sprints,
    sprintNameMap: options.sprintNames,
  }),
}))

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderView(content: string = JSON.stringify(analysis), materialContent: string | null = JSON.stringify(frozenInput)) {
  render(<HistoricalRelationView content={content} materialContent={materialContent} projectId="project" />)
}

const rail = () => screen.getByRole('complementary', { name: '历史需求关联导航' })
const list = (name: string) => within(rail()).getByRole('navigation', { name })
const impacts = () => within(screen.getByRole('region', { name: '规则影响' })).getAllByRole('region', { name: /^规则影响 imp-/ })
const evidenceOf = (region: HTMLElement) => {
  const evidence = region.querySelector('details')!
  fireEvent.click(within(evidence).getByText('条冻结条目'))
  return evidence
}
const detailTitle = () => screen.getByRole('region', { name: '关联需求详情' }).querySelector('h2')
const paragraphs = (node: HTMLElement) => [...node.querySelectorAll('p')].map((item) => item.textContent)

describe('历史需求关联', () => {
  it('按历史需求列出关联，默认阅读第一条关联档案', () => {
    renderView()
    expect(within(list('关联需求列表')).getAllByRole('button').map((button) => button.textContent)).toEqual([
      '2 项登录失败次数与锁定规则规则变更',
      '1 项登录异常审计记录补充规则',
    ])
    const detail = screen.getByRole('region', { name: '关联需求详情' })
    expect(detailTitle()).toHaveTextContent('登录失败次数与锁定规则')
    expect(detail).toHaveTextContent('规则变更')
    expect(detail).toHaveTextContent('req-old')
    expect(detail).toHaveTextContent('第 18 迭代')
    expect(detail).toHaveTextContent('本次需求对该历史需求的主要动作是「规则变更」：共 2 项规则影响，其中 1 项依据充分、1 项待确认。')
    expect(within(detail).getByRole('group', { name: '关联摘要' })).toHaveTextContent('规则影响2依据充分1待确认1引用本次条目2')
    expect(impacts()).toHaveLength(2)
    expect(rail().querySelector('footer')).toHaveTextContent('共 2 条关联2 待确认只读')
  })

  it('每条规则影响并排对照历史规则与本次规则，材料依据默认折叠、展开后显示两侧冻结条目', () => {
    renderView()
    const [changed, retired] = impacts()
    expect(changed).toHaveTextContent('已变更')
    expect(changed).toHaveTextContent('依据充分')
    expect(changed).toHaveTextContent('历史规则')
    expect(changed).toHaveTextContent('管理员连续输错密码 5 次后锁定账号。')
    expect(changed).toHaveTextContent('本次规则')
    expect(changed).toHaveTextContent('管理员连续输错密码 3 次后锁定账号。')
    expect(changed).toHaveTextContent('锁定阈值由 5 次降为 3 次。')
    expect(changed).toHaveTextContent('角色')
    expect(changed).toHaveTextContent('连续登录失败')

    expect(retired).toHaveTextContent('本次规则（已取消）')
    expect(retired).toHaveTextContent('没有接续规则')
    expect(retired).toHaveTextContent('已取消')
    expect(retired).toHaveTextContent('待确认')
    expect(retired).toHaveTextContent('账号已锁定')
    expect(retired).toHaveTextContent('未列明')

    const evidence = changed.querySelector('details')!
    expect(evidence).not.toHaveAttribute('open')
    fireEvent.click(within(evidence).getByText('材料依据'))
    expect(evidence).toHaveAttribute('open')
    expect(evidence).toHaveTextContent('历史材料')
    expect(evidence).toHaveTextContent('本次材料')
    expect(evidence).toHaveTextContent('明确')
    expect(evidence).toHaveTextContent('管理员登录 · 功能使用与业务规则')
    expect(within(evidence).getAllByText('1-3-1')).toHaveLength(2)
  })

  it('冻结输入里找不到的条目只显示引用，不编造原文', () => {
    renderView()
    const evidence = evidenceOf(screen.getByRole('region', { name: '规则影响 imp-2' }))
    expect(within(evidence).getByText('missing')).toBeInTheDocument()
    expect(paragraphs(evidence)).toEqual(['条目原文不可用，仅显示条目引用。', '管理员可通过绑定邮箱自助解锁。'])
  })

  it('冻结输入不可用时退回为只显示条目引用', () => {
    renderView(JSON.stringify(analysis), null)
    const evidence = evidenceOf(screen.getByRole('region', { name: '规则影响 imp-1' }))
    expect(paragraphs(evidence)).toEqual(['条目原文不可用，仅显示条目引用。', '条目原文不可用，仅显示条目引用。'])
    expect(within(evidence).getAllByText('1-3-1')).toHaveLength(2)
  })

  it('按关联类型筛选列表，没有该类型的筛选禁用', () => {
    renderView()
    expect(within(rail()).getByRole('button', { name: /^沿用规则/ })).toBeDisabled()
    fireEvent.click(within(rail()).getByRole('button', { name: /^补充规则/ }))
    expect(within(list('关联需求列表')).getAllByRole('button').map((button) => button.textContent)).toEqual(['1 项登录异常审计记录补充规则'])
    expect(detailTitle()).toHaveTextContent('登录异常审计记录')
    expect(screen.getByRole('region', { name: '已确认历史关系' })).toHaveTextContent('登录异常审计记录补充规则登录失败次数与锁定规则')
    fireEvent.click(within(rail()).getByRole('button', { name: /^规则变更/ }))
    expect(list('关联需求列表')).toHaveTextContent('登录失败次数与锁定规则')
  })

  it('待确认分类区分已定位和未定位的问题，并能双向跳转', () => {
    renderView()
    fireEvent.click(within(rail()).getByRole('button', { name: /^待确认，2 条/ }))
    expect(within(list('待确认列表')).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Q1邮件自助解锁是否一并取消？待确认',
      'Q2是否涉及第三方登录？待确认',
    ])
    expect(screen.getByRole('region', { name: '待确认问题详情' })).toHaveTextContent('需要向业务方确认的问题')
    expect(screen.getByRole('region', { name: '关联规则' })).toHaveTextContent('登录失败次数与锁定规则')

    fireEvent.click(within(rail()).getByRole('button', { name: /^未定位/ }))
    expect(list('待确认列表')).toHaveTextContent('是否涉及第三方登录')
    expect(screen.getByRole('region', { name: '关联规则' })).toHaveTextContent('尚未定位到一条具体规则')
    expect(screen.getByRole('region', { name: '材料依据' })).toHaveTextContent('暂无材料依据')

    fireEvent.click(within(rail()).getByRole('button', { name: /^已定位到规则/ }))
    fireEvent.click(within(screen.getByRole('region', { name: '关联规则' })).getByRole('button'))
    expect(screen.getByRole('region', { name: '关联需求详情' })).toHaveTextContent('登录失败次数与锁定规则')
    expect(within(rail()).getByRole('button', { name: /^关联需求，2 条/ })).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: '查看问题' }))
    expect(within(rail()).getByRole('button', { name: /^待确认，2 条/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('region', { name: '待确认问题详情' })).toHaveTextContent('邮件自助解锁是否一并取消？')
  })

  it('空关联结果说明没有可关联需求，并保留待确认问题', () => {
    renderView(JSON.stringify(emptyAnalysis))
    expect(screen.getAllByText('没有可关联的历史需求；仍有 1 个待确认问题，可在导航栏切换查看。')).toHaveLength(2)
    expect(within(rail()).queryByRole('navigation', { name: '关联需求列表' })).not.toBeInTheDocument()
    fireEvent.click(within(rail()).getByRole('button', { name: /^待确认，1 条/ }))
    expect(screen.getByRole('region', { name: '待确认问题详情' })).toHaveTextContent('是否涉及第三方登录')
  })

  it('结构不符的产物提示重新生成，不进入可视化', () => {
    renderView(JSON.stringify({ functionalOverview: { purpose: '旧内容' } }))
    expect(screen.getByText('历史需求关联结果格式无效，请重新生成')).toBeInTheDocument()
    expect(screen.queryByText('旧内容')).not.toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: '历史需求关联导航' })).not.toBeInTheDocument()
  })

  it('宽屏切换选中项时详情回到顶部，窄屏则把详情滚入视野', () => {
    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: false, media: query } as MediaQueryList)))
    const scrollIntoView = vi.fn()
    Object.defineProperty(Element.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoView })
    renderView()
    const scroller = rail().nextElementSibling as HTMLElement
    scroller.scrollTop = 80
    fireEvent.click(within(list('关联需求列表')).getByRole('button', { name: /登录异常审计记录/ }))
    expect(scroller.scrollTop).toBe(0)
    expect(scrollIntoView).not.toHaveBeenCalled()

    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query === '(max-width: 900px)', media: query } as MediaQueryList)))
    fireEvent.click(within(list('关联需求列表')).getByRole('button', { name: /登录失败次数与锁定规则/ }))
    expect(scrollIntoView).toHaveBeenCalledTimes(1)
  })
})
