import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { notify } from '@/shared/utils/toast'
import { ApiCandidateResultView, ApiConfigDiagramView } from '.'

vi.mock('@/shared/utils/toast', () => ({ notify: { success: vi.fn(), error: vi.fn() } }))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const loginCase = {
  method: 'POST',
  path: '/v1/login',
  headers: { 'Content-Type': 'application/json # [可选]' },
  json: {
    name: 'string (必传) # 用户名',
    password: 'string (必传)',
    authMethod: 'string (可选, enum:local|ldap, default:local)',
  },
  response: {
    code: 'integer (default:0)',
    data: {
      accessToken: 'string # [关键提取] 用于后续操作传参',
      mustChangePassword: 'boolean (default:false)',
    },
    message: 'string (default:ok)',
  },
}

const extraction = JSON.stringify({ login: loginCase })

const multiExtraction = JSON.stringify({
  login: loginCase,
  create_slice: {
    name: '创建语义切片任务',
    method: 'POST',
    path: '/v1/videos/{{videoId}}/semantic-slices',
    headers: { Authorization: 'Bearer {{token}} # [必传]' },
    path_params: { videoId: 'string (必传)' },
    json: { segments: 'array (必传)', depthSwitch: 'boolean (可选, default:false)' },
    response: { code: 'integer (default:0)', data: { taskId: 'string # [关键提取] 轮询任务状态' } },
  },
})

const candidate = JSON.stringify({
  cases: [{
    name: '登录',
    method: 'POST',
    path: '/v1/login',
    headers: { Authorization: 'Bearer {{token}}' },
    extractRules: [{ name: 'token', sourceExpr: '$.data.token' }],
    assertRules: [{ name: '状态码', comparator: 'eq', expectedValue: 200 }],
  }],
})

describe('ApiConfigDiagramView', () => {
  it('按接口展示请求/响应字段、约束与关键提取', () => {
    render(<ApiConfigDiagramView content={extraction} />)

    expect(screen.getByRole('heading', { name: 'login' })).toBeInTheDocument()
    expect(screen.getByLabelText('1 个接口')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: '请求字段 4' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: '响应字段 4' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: '认证头 0' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: '关键提取 1' })).toBeInTheDocument()
    expect(screen.getAllByText('/v1/login').length).toBeGreaterThan(0)

    const headers = screen.getByRole('table', { name: '请求头字段' })
    expect(within(headers).getByText('Content-Type')).toBeInTheDocument()
    expect(within(headers).getByText('application/json')).toBeInTheDocument()
    expect(within(headers).getByText('可选')).toBeInTheDocument()

    const body = screen.getByRole('table', { name: 'Body 字段' })
    expect(within(body).getByText('name')).toBeInTheDocument()
    expect(within(body).getByText('用户名')).toBeInTheDocument()
    expect(within(body).getByText('authMethod')).toBeInTheDocument()
    expect(within(body).getByText('默认')).toBeInTheDocument()
    expect(within(body).getByText('枚举')).toBeInTheDocument()
    expect(within(body).getByText('local|ldap')).toBeInTheDocument()

    const response = screen.getByRole('table', { name: '响应字段' })
    expect(within(response).getByText('data')).toBeInTheDocument()
    expect(within(response).getByText('accessToken')).toBeInTheDocument()
    expect(within(response).getByText('关键提取')).toBeInTheDocument()
    expect(within(response).getByText('用于后续操作传参')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'data.accessToken' })).toBeInTheDocument()
    expect(screen.queryByText('提取规则')).not.toBeInTheDocument()
    expect(screen.queryByText('断言规则')).not.toBeInTheDocument()
  })

  it('支持对象字段收起与展开', async () => {
    render(<ApiConfigDiagramView content={extraction} />)
    const user = userEvent.setup()

    await user.click(screen.getByRole('button', { name: '收起 data' }))
    expect(screen.queryByText('accessToken', { exact: true })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '展开 data' })).toHaveAttribute('aria-expanded', 'false')

    await user.click(screen.getByRole('button', { name: '展开 data' }))
    expect(screen.getByText('accessToken', { exact: true })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '收起 data' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('关键提取可展开祖先字段并定位到响应字段', async () => {
    const originalScrollIntoView = Element.prototype.scrollIntoView
    const scrollIntoView = vi.fn()
    Object.defineProperty(Element.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoView })
    try {
      render(<ApiConfigDiagramView content={extraction} />)
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: '收起 data' }))
      expect(screen.queryByText('accessToken', { exact: true })).not.toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'data.accessToken' }))
      await waitFor(() => expect(screen.getByText('accessToken', { exact: true })).toBeInTheDocument())
      expect(scrollIntoView).toHaveBeenCalled()
    } finally {
      if (originalScrollIntoView) Element.prototype.scrollIntoView = originalScrollIntoView
      else Reflect.deleteProperty(Element.prototype, 'scrollIntoView')
    }
  })

  it('支持搜索空态、清除和接口切换', async () => {
    render(<ApiConfigDiagramView content={multiExtraction} />)
    const user = userEvent.setup()
    const search = screen.getByRole('textbox', { name: '搜索接口' })

    await user.type(search, '不存在的接口')
    expect(screen.getByText('没有匹配的接口')).toBeInTheDocument()
    expect(screen.getByLabelText('0 个接口')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '清除搜索' }))
    expect(search).toHaveValue('')
    expect(screen.getByRole('button', { name: /POST login/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /POST 创建语义切片任务/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /POST 创建语义切片任务/ }))
    expect(screen.getByRole('heading', { name: '创建语义切片任务' })).toBeInTheDocument()
    expect(screen.getAllByText('Authorization').length).toBeGreaterThan(0)
    expect(screen.getAllByText('videoId').length).toBeGreaterThan(0)
    expect(screen.getAllByText('token').length).toBeGreaterThan(0)
    expect(screen.getByRole('table', { name: 'Path 字段' })).toBeInTheDocument()
    expect(screen.getByRole('table', { name: 'Body 字段' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'data.taskId' })).toBeInTheDocument()
  })

  it('复制接口路径并反馈结果', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    render(<ApiConfigDiagramView content={extraction} />)

    await userEvent.click(screen.getByRole('button', { name: '复制接口路径' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('/v1/login'))
    expect(notify.success).toHaveBeenCalledWith('接口路径已复制')
  })

  it('候选内容默认收起，展开后展示变量与提取/断言规则', async () => {
    render(<ApiCandidateResultView content={candidate} />)
    const user = userEvent.setup()
    const detail = screen.getByRole('region', { name: '接口详情' })
    const trigger = screen.getByRole('button', { name: '展开 POST 登录' })

    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(within(detail).queryByText('/v1/login')).not.toBeInTheDocument()

    await user.click(trigger)
    expect(screen.getByRole('button', { name: '收起 POST 登录' })).toHaveAttribute('aria-expanded', 'true')
    expect(within(detail).getByText('/v1/login')).toBeInTheDocument()
    expect(within(detail).getAllByText('token').length).toBeGreaterThan(0)
    expect(within(detail).getByText('提取规则')).toBeInTheDocument()
    expect(within(detail).getByText('断言规则')).toBeInTheDocument()
    expect(within(detail).getByText('$.data.token')).toBeInTheDocument()
    expect(within(detail).getByText('状态码')).toBeInTheDocument()
  })

  it('无法解析的候选内容显示明确空态', () => {
    render(<ApiCandidateResultView content="not-json" />)
    expect(screen.getByText('当前候选结果无法解析为 API 用例')).toBeInTheDocument()
  })

  it('无法解析的接口配置也显示空态', () => {
    render(<ApiConfigDiagramView content="not-json" />)
    expect(screen.getByText('当前接口配置无法解析')).toBeInTheDocument()
  })
})
