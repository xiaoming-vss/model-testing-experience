import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider as ThemeProvider } from '@/test/TestThemeProvider'
import { PerfStepEditor } from './PerfStepsEditor'
import { createPerfHeaderRow, createPerfStep } from '../utils/perfCaseForm'

vi.mock('@/domain/projects/hooks/useProjectAccess', () => ({
  useProjectAccess: () => ({ can: () => true, loading: false, error: null }),
}))
vi.mock('@/domain/projects/hooks/projectScope', () => ({
  useScopedProjectId: () => 'project-1',
}))

afterEach(cleanup)

function step() {
  return createPerfStep({
    name: 'login',
    method: 'POST',
    path: '/api/login',
    headers: [{ ...createPerfHeaderRow(), name: 'X-Tenant', value: '{{env.tenant}}' }],
    bodyMode: 'json',
    bodyText: '{"ok":true}',
    checks: [{ id: 'check-1', type: 'status', op: 'eq', path: '', name: '', pattern: '', value: '200' }],
    extract: [],
  })
}

function renderEditor(onChange = vi.fn(), canWrite = true) {
  render(<ThemeProvider>
    <PerfStepEditor
      step={step()}
      stepIndex={0}
      stepCount={2}
      variables={['token']}
      projectId="project-1"
      environmentName="预发环境"
      environmentBaseUrl="https://pre-api.example.com"
      canWrite={canWrite}
      dirty={false}
      saving={false}
      errors={[]}
      errorsAlert={null}
      onBack={vi.fn()}
      onMove={vi.fn()}
      onDelete={vi.fn()}
      onCancel={vi.fn()}
      onSave={vi.fn()}
      onChange={onChange}
    />
  </ThemeProvider>)
  return onChange
}

it('renders the API-style request bar and four tabs', () => {
  renderEditor()

  expect(screen.getByText('https://pre-api.example.com')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: /请求头/ })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: /请求体/ })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: /后置操作/ })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '设置' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /保存用例/ })).toBeDisabled()
})

it('adds a request header from the quick preset', async () => {
  const user = userEvent.setup()
  const onChange = renderEditor()

  await user.click(screen.getByRole('button', { name: /X-Tenant/ }))

  expect(onChange).toHaveBeenCalledWith({
    headers: expect.arrayContaining([
      expect.objectContaining({ name: 'X-Tenant', value: '{{env.tenant}}' }),
    ]),
  })
})

it('groups assertions and extracts in post operations and keeps settings separate', async () => {
  const user = userEvent.setup()
  renderEditor()

  await user.click(screen.getByRole('tab', { name: /后置操作/ }))

  expect(screen.getByText('统一管理断言与提取规则，提取结果供后续步骤使用。')).toBeInTheDocument()
  expect(screen.getByText('断言', { exact: true })).toBeInTheDocument()
  expect(screen.getByText('提取规则', { exact: true })).toBeInTheDocument()

  await user.click(screen.getByRole('tab', { name: '设置' }))

  expect(screen.getByLabelText('步骤 1 失败后')).toBeInTheDocument()
  expect(screen.getByText('思考时间（ms）')).toBeInTheDocument()
})

it('formats a valid JSON body from the body tab', async () => {
  const user = userEvent.setup()
  const onChange = renderEditor()

  await user.click(screen.getByRole('tab', { name: /请求体/ }))
  expect(screen.getByText('JSON 合法')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: '格式化代码' }))

  expect(onChange).toHaveBeenCalledWith({ bodyText: '{\n  "ok": true\n}' })
})


it('批量编辑请求头保留冒号后的完整值', async () => {
  const user = userEvent.setup()
  const onChange = renderEditor()
  await user.click(screen.getByRole('button', { name: /批量编辑/ }))
  const editor = await screen.findByLabelText('请求头批量编辑内容')
  await user.clear(editor)
  await user.type(editor, 'Authorization: Bearer token:part')
  await user.click(screen.getByRole('button', { name: /应\s*用/ }))
  expect(onChange).toHaveBeenCalledWith({ headers: [expect.objectContaining({ name: 'Authorization', value: 'Bearer token:part' })] })
})

it('只读时请求头和请求体的编辑操作均不可用', async () => {
  const user = userEvent.setup()
  renderEditor(vi.fn(), false)
  expect(screen.getByRole('button', { name: /批量编辑/ })).toBeDisabled()
  expect(screen.getByLabelText('步骤 1 请求头 1 值')).toBeDisabled()
  await user.click(screen.getByRole('tab', { name: /请求体/ }))
  expect(screen.getByRole('tab', { name: 'raw' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '格式化代码' })).toBeDisabled()
  expect(screen.getByRole('button', { name: /插入变量/ })).toBeDisabled()
})
