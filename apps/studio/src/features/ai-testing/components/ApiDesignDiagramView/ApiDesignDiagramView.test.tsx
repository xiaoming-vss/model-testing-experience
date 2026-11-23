import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { notify } from '@/shared/utils/toast'
import { ApiDesignDiagramView } from './ApiDesignDiagramView'

vi.mock('@/shared/utils/toast', () => ({ notify: { success: vi.fn(), error: vi.fn() } }))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const baseDesign = {
  schemaVersion: 'api_test_design/1.0',
  interfaces: {
    create_user: {
      method: 'POST',
      path: '/api/users',
      cases: [
        {
          id: 'create_user_positive_full',
          title: '创建用户-正向-全参数',
          category: 'positive',
          priority: 'P0',
          intent: '验证完整合法参数创建用户成功',
          basis: { kind: 'positive', section: '', field: '', constraint: '' },
          patch: {},
          expected: {
            statusClass: '2xx',
            assertions: [{ assertSource: 'body_jsonpath', targetExpr: '$.id', comparator: 'exists', expectedValue: '' }],
          },
        },
        {
          id: 'create_user_age_below_min',
          title: '创建用户-边界-年龄低于最小值',
          category: 'boundary',
          priority: 'P1',
          intent: '验证年龄小于 minimum:18 时请求被拒绝',
          basis: { kind: 'constraint', section: 'json', field: '/age', constraint: 'minimum:18' },
          patch: { json: [{ op: 'replace', path: '/age', value: 17 }] },
          expected: { statusClass: '4xx', assertions: [] },
        },
      ],
      uncovered: [
        { kind: 'constraint', section: 'json', field: '/role', constraint: 'enum:admin,user', reason: 'soft_cap' },
      ],
    },
  },
}

const design = JSON.stringify(baseDesign)

const multiDesign = JSON.stringify({
  ...baseDesign,
  interfaces: {
    ...baseDesign.interfaces,
    read_user: {
      method: 'GET',
      path: '/api/users/{id}',
      cases: [{
        id: 'read_user_positive',
        title: '查询用户详情',
        category: 'positive',
        priority: 'P1',
        intent: '验证按 ID 查询用户详情',
        basis: { kind: 'positive', section: '', field: '', constraint: '' },
        patch: {},
        expected: { statusClass: '2xx', assertions: [] },
      }],
      uncovered: [],
    },
  },
})

describe('ApiDesignDiagramView', () => {
  it('按接口展示覆盖摘要、分组、用例依据和未覆盖约束', () => {
    render(<ApiDesignDiagramView content={design} />)
    expect(screen.getByRole('heading', { name: 'create_user' })).toBeInTheDocument()
    expect(screen.getByLabelText('1 个接口')).toBeInTheDocument()
    expect(screen.getByText((_, element) => element?.tagName === 'SPAN' && element.textContent === '2 条用例')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '正向 1 条，反向 0 条，边界 1 条' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '全部，2 条用例' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '反向，0 条用例' })).toBeDisabled()
    expect(screen.getByText('创建用户-正向-全参数')).toBeInTheDocument()
    expect(screen.getByText('正向全参数基线')).toBeInTheDocument()
    expect(screen.getByText('验证完整合法参数创建用户成功')).toBeInTheDocument()
    expect(screen.getByText('$.id')).toBeInTheDocument()
    expect(screen.getByText('存在')).toBeInTheDocument()
    expect(screen.getByText('创建用户-边界-年龄低于最小值')).toBeInTheDocument()
    expect(screen.getByText('body.age · minimum:18')).toBeInTheDocument()
    expect(screen.getByText('17')).toBeInTheDocument()
    expect(screen.getByText('body.role')).toBeInTheDocument()
    expect(screen.getByText('enum:admin,user')).toBeInTheDocument()
    expect(screen.getByText('数量上限')).toBeInTheDocument()
  })

  it('支持接口搜索、空态和清除搜索', async () => {
    render(<ApiDesignDiagramView content={multiDesign} />)
    const search = screen.getByRole('textbox', { name: '搜索接口' })
    await userEvent.type(search, '不存在的接口')
    expect(screen.getByText('没有匹配的接口')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '清除搜索' }))
    expect(search).toHaveValue('')
    expect(screen.getByRole('button', { name: /POST create_user/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /GET read_user/ })).toBeInTheDocument()
  })

  it('切换接口后重置筛选并定位未覆盖约束', async () => {
    render(<ApiDesignDiagramView content={multiDesign} />)
    await userEvent.click(screen.getByRole('button', { name: /GET read_user/ }))
    expect(screen.getByRole('heading', { name: 'read_user' })).toBeInTheDocument()
    expect(screen.getByText('约束全覆盖')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '定位' }))
    expect(screen.getByRole('heading', { name: 'create_user' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '全部，2 条用例' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('按分类筛选用例并支持单条和全部展开', async () => {
    render(<ApiDesignDiagramView content={design} />)
    const positiveCase = screen.getByRole('button', { name: /创建用户-正向-全参数/ })
    const boundaryCase = screen.getByRole('button', { name: /创建用户-边界-年龄低于最小值/ })
    expect(positiveCase).toHaveAttribute('aria-expanded', 'true')
    expect(boundaryCase).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(boundaryCase)
    expect(boundaryCase).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(screen.getByRole('button', { name: '收起全部' }))
    expect(positiveCase).toHaveAttribute('aria-expanded', 'false')
    expect(boundaryCase).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(screen.getByRole('button', { name: '展开全部' }))
    expect(positiveCase).toHaveAttribute('aria-expanded', 'true')
    expect(boundaryCase).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(screen.getByRole('button', { name: '边界，1 条用例' }))
    expect(screen.queryByText('创建用户-正向-全参数')).not.toBeInTheDocument()
    expect(screen.getByText('创建用户-边界-年龄低于最小值')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '全部，2 条用例' }))
    expect(screen.getByText('创建用户-正向-全参数')).toBeInTheDocument()
  })

  it('复制接口路径并反馈结果', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    render(<ApiDesignDiagramView content={design} />)
    await userEvent.click(screen.getByRole('button', { name: '复制接口路径' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('/api/users'))
    expect(notify.success).toHaveBeenCalledWith('接口路径已复制')
  })

  it('无效 JSON 显示解析空态并可切换到原文', async () => {
    const onShowRaw = vi.fn()
    render(<ApiDesignDiagramView content="{not-json" onShowRaw={onShowRaw} />)
    expect(screen.getByText('当前设计产物无法解析')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '查看原文' }))
    expect(onShowRaw).toHaveBeenCalled()
  })

  it('没有用例时显示空态', () => {
    render(<ApiDesignDiagramView content={JSON.stringify({ schemaVersion: 'api_test_design/1.0', interfaces: { read_one: { method: 'GET', path: '/read', cases: [], uncovered: [] } } })} />)
    expect(screen.getByText('暂无可视化的接口用例设计')).toBeInTheDocument()
  })
})
