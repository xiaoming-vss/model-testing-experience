import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { HistoricalCaseVerificationView } from './index'
import { analysis, emptyAnalysis, frozenInput } from './__fixtures__/historicalCaseVerification'

const options = vi.hoisted(() => ({ names: new Map([['req-old', '登录失败次数与锁定规则']]) }))

vi.mock('@/domain/projects/hooks/useProjectRequirementOptions', () => ({
  useProjectRequirementOptions: () => ({ requirementNameMap: options.names }),
}))

const NO_BATCH = '本次没有需要核验的规则变更或新增场景。'
const RULE_1 = '管理员账号的失败锁定阈值由 5 次降为 3 次。'
const RULE_3 = '超时自动解锁改由安全管理员手动解锁接管。'
const RULE_4 = '审计字段追加设备信息。'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function renderView(content: string = JSON.stringify(analysis), materialContent: string | null = JSON.stringify(frozenInput)) {
  vi.spyOn(api, 'getProjectFunctionTestSuites').mockResolvedValue({ items: [
    { suiteId: 'suite-1', name: '登录安全测试集' }, { suiteId: 'suite-2', name: '账号安全测试集' },
  ] } as never)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const tree = (body: string, material: string | null) => (
    <QueryClientProvider client={client}><HistoricalCaseVerificationView content={body} materialContent={material} projectId="project" /></QueryClientProvider>
  )
  const result = render(tree(content, materialContent))
  return { update: (body: string, material: string | null) => result.rerender(tree(body, material)) }
}

const rail = () => screen.getByRole('complementary', { name: '历史用例核验导航' })
const list = (name: string) => within(rail()).getByRole('navigation', { name })
const rows = (name: string) => within(list(name)).getAllByRole('button').map(button => button.textContent)
const archive = (name: string) => screen.getByRole('region', { name })
const finding = (id: string) => document.querySelector<HTMLElement>(`[data-finding-id="${id}"]`)!
const toggleOf = (id: string, label: RegExp) => within(finding(id)).getByRole('button', { name: label })
const category = (label: string, total: number) => within(rail()).getByRole('button', { name: new RegExp(`^${label}，${total} 条`) })

describe('历史用例核验', () => {
  it('默认查看待维护用例，切换到规则后打开首条可批注的结论', () => {
    renderView()
    expect(category('待维护用例', 2)).toHaveAttribute('aria-pressed', 'true')
    expect(rows('待维护用例列表')).toEqual([
      '1管理员第 3 次密码校验失败后可重试需修改',
      '1管理员锁定 15 分钟后自动解锁建议失效',
    ])
    expect(within(rail()).queryByRole('button', { name: /^可复用|^不受影响/ })).not.toBeInTheDocument()
    fireEvent.click(category('规则影响', 3))
    expect(category('补测测试点', 2)).toBeInTheDocument()
    expect(category('待确认', 1)).toBeInTheDocument()
    expect(rows('规则影响列表')).toEqual([`2${RULE_1}已变更`, `1${RULE_3}已替代`, `0${RULE_4}已补充`])
    expect(rail().querySelector('footer')).toHaveTextContent('共 3 条规则2 条待维护用例只读')

    const detail = archive('规则核验档案')
    expect(detail.querySelector('h2')).toHaveTextContent(RULE_1)
    expect(detail).toHaveTextContent('已变更')
    expect(detail).toHaveTextContent('impact-1')
    expect(detail).toHaveTextContent('batch-1')
    expect(detail).toHaveTextContent('历史需求 · 登录失败次数与锁定规则')
    expect(detail).toHaveTextContent('管理员连续输错密码 5 次后锁定账号。')
    expect(detail).toHaveTextContent('管理员连续输错密码 3 次后锁定账号。')
    expect(within(detail).getByRole('group', { name: '规则摘要' })).toHaveTextContent('需修改1建议失效0待确认1补测测试点1')
    expect(within(detail).getByRole('region', { name: '补测测试点' })).toHaveTextContent('再次输入错误密码。')

    // 有冻结全文的结论默认展开为带行内批注的完整用例；其余结论保持摘要。
    const first = finding('batch-1/case-a')
    expect(toggleOf('batch-1/case-a', /收起完整用例/)).toHaveAttribute('aria-expanded', 'true')
    expect(first).toHaveTextContent('需修改')
    expect(first).toHaveTextContent('case-a')
    expect(first).toHaveTextContent('当前规则')
    expect(within(first).getByRole('region', { name: '前置条件' })).toHaveTextContent('管理员账号连续登录失败 2 次。')
    expect(within(first).getByRole('region', { name: '操作步骤' })).toHaveTextContent('输入错误密码登录。可以继续重试，账号未锁定。')
    expect(first).toHaveTextContent('步骤 1 预期第 3 次失败后仍可重试，与本次规则冲突。')
    expect(first).toHaveTextContent('建议改为')
    expect(first).toHaveTextContent('将步骤 1 的预期改为「账号被锁定」。')

    expect(finding('batch-1/case-b')).not.toBeInTheDocument()
    expect(finding('batch-1/case-d')).toHaveTextContent('待确认')
  })

  it('结论可以收起和再次展开，也可以同时展开多条', () => {
    renderView()
    fireEvent.click(category('规则影响', 3))
    fireEvent.click(toggleOf('batch-1/case-a', /收起完整用例/))
    const collapsed = finding('batch-1/case-a')
    expect(within(collapsed).getByRole('button', { name: /在完整用例中查看/ })).toHaveAttribute('aria-expanded', 'false')
    expect(collapsed).not.toHaveTextContent('当前规则')
    // 收起后回到摘要：证据位置保留原文和预期。
    expect(collapsed).toHaveTextContent('步骤 1')
    expect(collapsed).toHaveTextContent('输入错误密码登录。')
    expect(collapsed).toHaveTextContent('可以继续重试，账号未锁定。')
    expect(within(collapsed).queryByRole('region', { name: '操作步骤' })).not.toBeInTheDocument()

    fireEvent.click(toggleOf('batch-1/case-a', /在完整用例中查看/))
    fireEvent.click(toggleOf('batch-1/case-d', /在完整用例中查看/))
    expect(finding('batch-1/case-a')).toHaveTextContent('当前规则')
    expect(finding('batch-1/case-d')).toHaveTextContent('当前规则')

    // 手动开关只对当前规则有效；重新选择规则后回到自动展开首条。
    fireEvent.click(toggleOf('batch-1/case-a', /收起完整用例/))
    fireEvent.click(within(list('规则影响列表')).getByRole('button', { name: new RegExp(RULE_1) }))
    expect(toggleOf('batch-1/case-a', /收起完整用例/)).toBeInTheDocument()
    expect(toggleOf('batch-1/case-d', /在完整用例中查看/)).toBeInTheDocument()
  })

  it('建议失效的结论来自全文，多处证据只在首处展开理由', () => {
    renderView()
    fireEvent.click(category('规则影响', 3))
    fireEvent.click(within(list('规则影响列表')).getByRole('button', { name: new RegExp(RULE_3) }))
    const invalidated = finding('batch-3/case-c')
    expect(invalidated).toHaveTextContent('补读全文后')
    expect(invalidated).toHaveTextContent('建议失效')
    expect(invalidated).toHaveTextContent('同一条结论，理由与建议见步骤 1')
    expect(within(invalidated).queryByRole('note', { name: '其他规则下的结论' })).not.toBeInTheDocument()
  })

  it('按处理情况筛选规则；纯补充只给补测测试点', () => {
    renderView()
    fireEvent.click(category('规则影响', 3))
    fireEvent.click(within(rail()).getByRole('button', { name: /^有待办/ }))
    expect(rows('规则影响列表')).toEqual([`2${RULE_1}已变更`, `1${RULE_3}已替代`])
    fireEvent.click(within(rail()).getByRole('button', { name: /^无待办/ }))
    expect(rows('规则影响列表')).toEqual([`0${RULE_4}已补充`])
    fireEvent.click(within(list('规则影响列表')).getByRole('button', { name: new RegExp(RULE_4) }))
    const detail = archive('规则核验档案')
    expect(detail).toHaveTextContent('已补充')
    expect(within(detail).getByRole('region', { name: '用例结论' })).toHaveTextContent('没有需要处理的历史用例')
    expect(within(detail).getByRole('region', { name: '补测测试点' })).toHaveTextContent('验证锁定审计记录包含设备信息。')
  })

  it('补测测试点分类阅读场景档案，并能回到所属规则', () => {
    renderView()
    fireEvent.click(category('补测测试点', 2))
    expect(category('规则影响', 3)).toHaveAttribute('aria-pressed', 'false')
    expect(rows('补测测试点列表')).toEqual(['1再次输入错误密码。 账号未锁定。', '2验证锁定审计记录包含设备信息。'])
    const scenario = archive('补测测试点档案')
    expect(scenario.querySelector('h2')).toHaveTextContent('再次输入错误密码。')
    expect(within(scenario).queryByText('前置条件', { exact: true })).not.toBeInTheDocument()
    expect(within(scenario).queryByText('预期', { exact: true })).not.toBeInTheDocument()
    expect(within(scenario).getByRole('region', { name: '所属规则' })).toHaveTextContent('管理员连续输错密码 3 次后锁定账号。')

    fireEvent.click(within(scenario).getByRole('button', { name: '在规则档案中查看' }))
    expect(category('规则影响', 3)).toHaveAttribute('aria-pressed', 'true')
    expect(within(list('规则影响列表')).getByRole('button', { name: new RegExp(RULE_1) })).toHaveAttribute('aria-current', 'true')
    expect(archive('规则核验档案')).toHaveTextContent(RULE_1)
    expect(toggleOf('batch-1/case-a', /收起完整用例/)).toBeInTheDocument()

    fireEvent.click(category('补测测试点', 2))
    fireEvent.click(within(list('补测测试点列表')).getByRole('button', { name: /验证锁定审计记录/ }))
    const point = archive('补测测试点档案')
    expect(point.querySelector('h2')).toHaveTextContent('验证锁定审计记录包含设备信息。')
    expect(point).not.toHaveTextContent('前置条件')
    expect(within(point).getByRole('region', { name: '所属规则' })).toHaveTextContent('设备')
  })

  it('待维护用例可按结论筛选，跳回规则时展开该用例的结论', () => {
    renderView()
    fireEvent.click(within(rail()).getByRole('button', { name: /^建议失效/ }))
    expect(rows('待维护用例列表')).toEqual(['1管理员锁定 15 分钟后自动解锁建议失效'])

    const caseArchive = archive('历史用例档案')
    expect(caseArchive.querySelector('h2')).toHaveTextContent('管理员锁定 15 分钟后自动解锁')
    expect(caseArchive).toHaveTextContent('补读全文后')
    // 用例档案里的批注标出所属规则，而不是「当前规则」。
    expect(within(caseArchive).getAllByText(`关联规则：${RULE_3}`)).toHaveLength(2)
    expect(caseArchive).not.toHaveTextContent('当前规则')
    expect(within(caseArchive).getByRole('region', { name: '操作步骤' })).toHaveTextContent('等待 15 分钟。')
    expect(caseArchive).toHaveTextContent('核验基于用例快照')
    expect(caseArchive).toHaveTextContent('case-c-snap-1')

    fireEvent.click(within(caseArchive).getByRole('button', { name: '在规则档案中查看' }))
    expect(within(list('规则影响列表')).getByRole('button', { name: new RegExp(RULE_3) })).toHaveAttribute('aria-current', 'true')
    expect(within(finding('batch-3/case-c')).getByText('当前规则')).toBeInTheDocument()
  })

  it('待确认分类说明缺少的依据，并能回到规则档案', () => {
    renderView()
    fireEvent.click(category('待确认', 1))
    expect(rows('待确认列表')).toEqual(['1锁定后的验证码引导待确认'])
    const pending = archive('待确认用例档案')
    expect(pending).toHaveTextContent('规则适用或用例内容不足以支持结论。')
    expect(pending).toHaveTextContent('本次规则未说明锁定后是否需要验证码，无法判定步骤 1 的预期。')
    expect(within(pending).getByRole('region', { name: '证据位置' })).toHaveTextContent('查看是否要求验证码。')
    expect(pending).toHaveTextContent(`来自规则已变更${RULE_1}`)
    expect(within(pending).getByRole('region', { name: '所属规则' })).toHaveTextContent('管理员连续输错密码 3 次后锁定账号。')

    const related = within(pending).getByRole('region', { name: '所属规则' })
    expect(related).toHaveTextContent('管理员连续输错密码 3 次后锁定账号。')
    fireEvent.click(within(related).getByRole('button', { name: '在规则档案中查看' }))
    expect(toggleOf('batch-1/case-d', /收起完整用例/)).toBeInTheDocument()
  })

  it('冻结输入不可用时保留结论和证据位置，不能在完整用例中查看', async () => {
    renderView(JSON.stringify(analysis), null)
    fireEvent.click(category('规则影响', 4))
    expect(rows('规则影响列表')).toEqual(['2规则 impact-1', '0规则 impact-2', '1规则 impact-3', '0规则 impact-4'])
    const detail = archive('规则核验档案')
    expect(detail.querySelector('h2')).toHaveTextContent('规则 impact-1')
    expect(detail).not.toHaveTextContent('历史规则')
    expect(detail).toHaveTextContent('前置条件和步骤原文来自冻结的核验输入，当前接口未返回。')

    const first = finding('batch-1/case-a')
    const toggle = toggleOf('batch-1/case-a', /在完整用例中查看/)
    expect(toggle).toBeDisabled()
    expect(toggle).toHaveAttribute('title', '前置条件和步骤原文来自冻结的核验输入，当前接口未返回')
    expect(first).toHaveTextContent('需修改')
    expect(first).toHaveTextContent('位置原文不可用，仅显示位置')
    expect(first).toHaveTextContent('步骤 1 预期第 3 次失败后仍可重试，与本次规则冲突。')
    expect(within(first).queryByRole('region', { name: '操作步骤' })).not.toBeInTheDocument()

    fireEvent.click(category('待维护用例', 2))
    expect(rows('待维护用例列表')).toEqual(['1case-a需修改', '1case-c建议失效'])
    expect(archive('历史用例档案')).toHaveTextContent('位置原文不可用，仅显示位置')
  })

  it('没有核验批次时说明没有需要核验的规则变更或新增场景', () => {
    renderView(JSON.stringify(emptyAnalysis))
    expect(screen.getAllByText(NO_BATCH)).toHaveLength(2)
    expect(within(rail()).queryByRole('navigation', { name: '规则影响列表' })).not.toBeInTheDocument()
    fireEvent.click(category('规则影响', 0))
    expect(screen.getAllByText(NO_BATCH)).toHaveLength(2)
  })

  it('结构不符的产物提示重新生成，不进入可视化', () => {
    renderView(JSON.stringify({ functionalOverview: { purpose: '旧内容' } }))
    expect(screen.getByText('历史用例核验结果格式无效，请重新生成')).toBeInTheDocument()
    expect(screen.queryByText('旧内容')).not.toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: '历史用例核验导航' })).not.toBeInTheDocument()
  })

  it('内容变化后回到待维护用例', () => {
    const { update } = renderView()
    fireEvent.click(category('补测测试点', 2))
    expect(archive('补测测试点档案')).toBeInTheDocument()
    update(JSON.stringify(emptyAnalysis), JSON.stringify(frozenInput))
    expect(category('待维护用例', 0)).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getAllByText(NO_BATCH)).toHaveLength(2)
  })

  it('宽屏跳回规则时定位到那条结论，窄屏选中后把阅读区滚入视野', () => {
    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: false, media: query } as MediaQueryList)))
    renderView()
    fireEvent.click(category('规则影响', 3))
    const scroller = rail().nextElementSibling as HTMLElement
    scroller.scrollTop = 120
    fireEvent.click(within(list('规则影响列表')).getByRole('button', { name: new RegExp(RULE_3) }))
    expect(scroller.scrollTop).toBe(0)

    // 定位时结论必须已经展开：收起状态的内容不足以滚动，浏览器的定位会被丢弃。
    const setScrollTop = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollTop')!.set!
    const expandedAtScroll: Array<string | null> = []
    vi.spyOn(Element.prototype, 'scrollTop', 'set').mockImplementation(function (this: HTMLElement, value: number) {
      if (value === 104) expandedAtScroll.push(finding('batch-1/case-d').querySelector('button')?.getAttribute('aria-expanded') ?? null)
      setScrollTop.call(this, value)
    })
    fireEvent.click(category('待确认', 1))
    scroller.scrollTop = 120
    fireEvent.click(within(archive('待确认用例档案')).getByRole('button', { name: '在规则档案中查看' }))
    // jsdom 里位置都是 0，所以只偏离定位留白。
    expect(scroller.scrollTop).toBe(104)
    expect(expandedAtScroll).toEqual(['true'])

    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query === '(max-width: 900px)', media: query } as MediaQueryList)))
    const scrollIntoView = vi.fn()
    Object.defineProperty(Element.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoView })
    fireEvent.click(within(list('规则影响列表')).getByRole('button', { name: new RegExp(RULE_3) }))
    expect(scrollIntoView).toHaveBeenCalledTimes(1)
  })
})
