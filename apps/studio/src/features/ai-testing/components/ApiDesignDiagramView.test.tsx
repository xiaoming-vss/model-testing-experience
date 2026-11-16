import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiDesignDiagramView } from './ApiDesignDiagramView'

afterEach(cleanup)

const design = JSON.stringify({
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
})

describe('ApiDesignDiagramView', () => {
  it('按接口展示用例、依据、参数变异和未覆盖约束', () => {
    render(<ApiDesignDiagramView content={design} />)
    expect(screen.getByText('接口 1')).toBeInTheDocument()
    expect(screen.getByText('用例 2')).toBeInTheDocument()
    expect(screen.getByText('创建用户-正向-全参数')).toBeInTheDocument()
    expect(screen.getByText('正向全参数基线')).toBeInTheDocument()
    expect(screen.getByText('验证年龄小于 minimum:18 时请求被拒绝')).toBeInTheDocument()
    expect(screen.getByText('body.age · minimum:18')).toBeInTheDocument()
    expect(screen.getByText('改为')).toBeInTheDocument()
    expect(screen.getByText('body.age')).toBeInTheDocument()
    expect(screen.getByText('17')).toBeInTheDocument()
    expect(screen.getByText('body.role · enum:admin,user')).toBeInTheDocument()
    expect(screen.getByText('数量上限')).toBeInTheDocument()
  })

  it('可单条或全部折叠用例详情', async () => {
    render(<ApiDesignDiagramView content={design} />)
    expect(screen.getByText('正向全参数基线')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '收起用例 创建用户-正向-全参数' }))
    expect(screen.queryByText('正向全参数基线')).not.toBeInTheDocument()
    expect(screen.getByText('验证年龄小于 minimum:18 时请求被拒绝')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '收起全部' }))
    expect(screen.queryByText('body.age · minimum:18')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '展开全部' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '展开全部' }))
    expect(screen.getByText('body.age · minimum:18')).toBeInTheDocument()
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
