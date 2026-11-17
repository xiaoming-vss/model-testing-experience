import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it } from 'vitest'
import { ApiCandidateResultView, ApiConfigDiagramView } from './ApiConfigDiagramView'

afterEach(cleanup)

const extraction = JSON.stringify({
  login: {
    method: 'POST',
    path: '/v1/login',
    headers: { 'Content-Type': 'application/json' },
    json: { name: 'string', password: 'string' },
    response: { code: 'integer', accessToken: 'string' },
  },
})

it('接口配置提取只展示接口配置，不展示提取规则和断言规则', () => {
  render(<ApiConfigDiagramView content={extraction} />)

  expect(screen.getByText('接口 1')).toBeInTheDocument()
  expect(screen.getByText('/v1/login')).toBeInTheDocument()
  expect(screen.queryByText('提取规则')).not.toBeInTheDocument()
  expect(screen.queryByText('断言规则')).not.toBeInTheDocument()
  expect(screen.queryByText('提取 0')).not.toBeInTheDocument()
  expect(screen.queryByText('断言 0')).not.toBeInTheDocument()
  expect(screen.queryByText('暂无提取规则')).not.toBeInTheDocument()
  expect(screen.queryByText('暂无断言规则')).not.toBeInTheDocument()
})

const candidate = JSON.stringify({
  cases: [
    {
      name: '登录',
      method: 'POST',
      path: '/v1/login',
      headers: { Authorization: 'Bearer {{token}}' },
      extractRules: [{ name: 'token', sourceExpr: '$.data.token' }],
      assertRules: [{ name: '状态码', comparator: 'eq', expectedValue: 200 }],
    },
  ],
})

it('候选接口默认折叠，可展开查看路径、变量和规则', async () => {
  render(<ApiCandidateResultView content={candidate} />)

  const trigger = screen.getByRole('button', { name: '展开 POST 登录' })
  expect(trigger).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByText('/v1/login')).not.toBeInTheDocument()

  await userEvent.setup().click(trigger)

  expect(screen.getByRole('button', { name: '折叠 POST 登录' })).toHaveAttribute(
    'aria-expanded',
    'true'
  )
  expect(screen.getByText('/v1/login')).toBeInTheDocument()
  expect(screen.getByText('使用 token')).toBeInTheDocument()
  expect(screen.getByText('提取 token')).toBeInTheDocument()
  expect(screen.getByText('提取规则')).toBeInTheDocument()
  expect(screen.getByText('断言规则')).toBeInTheDocument()
})

it('无法解析的候选内容显示明确空态', () => {
  render(<ApiCandidateResultView content="not-json" />)

  expect(screen.getByText('当前候选结果无法解析为 API 用例')).toBeInTheDocument()
})
