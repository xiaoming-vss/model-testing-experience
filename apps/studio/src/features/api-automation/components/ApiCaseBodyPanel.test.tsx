import type { TemplatesProps } from '@/features/api-automation/components/apiCaseEditorProps'
import { ApiCaseBodyPanel } from '@/features/api-automation/components/ApiCaseBodyPanel'
import { TestThemeProvider as ThemeProvider } from '@/test/TestThemeProvider'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Form } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'

/*
 * 请求体面板按设计稿改成「类型胶囊条 + 动作条 + 编辑器 + 状态条」，
 * 这组测试锁住类型切换与状态条的两条结论：JSON 合法性、内容大小。
 */

vi.mock('@/shared/utils/feedback', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/utils/feedback')>()),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

const templates: TemplatesProps = {
  setEnvVarInputRef: vi.fn(),
  renderEnvVarPicker: ({ trigger }) => <>{trigger}</>,
  insertTemplateText: vi.fn(),
  bodyJsonEditorRef: { current: null },
  insertTemplateTextIntoJson: vi.fn(),
  handleFormatBodyJson: vi.fn(),
  handleCompressBodyJson: vi.fn(),
}

function renderPanel(bodyType: 'none' | 'json' | 'form' | 'raw', bodyJson = '') {
  const formRef: { current: ReturnType<typeof Form.useForm<{ bodyType: string; bodyJson: string }>>[0] | null } = { current: null }

  function Harness() {
    const [form] = Form.useForm<{ bodyType: string; bodyJson: string }>()
    formRef.current = form
    const watchedBodyType = Form.useWatch('bodyType', form)

    return (
      <Form form={form} initialValues={{ bodyType, bodyJson }}>
        <ApiCaseBodyPanel bodyType={(watchedBodyType ?? bodyType) as 'none' | 'json'} templates={templates} />
      </Form>
    )
  }

  render(
    <ThemeProvider>
      <Harness />
    </ThemeProvider>,
  )

  return formRef
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

it('状态条给出 JSON 结论与内容大小', async () => {
  renderPanel('json', '{"code":200}')

  expect(await screen.findByText('无语法错误')).toBeInTheDocument()
  expect(screen.getByText('JSON Schema 合法')).toBeInTheDocument()
  expect(screen.getByText('大小: 12 B')).toBeInTheDocument()
  expect(screen.getByText('格式: JSON')).toBeInTheDocument()
})

it('请求体不是合法 JSON 时状态条与徽标都报错', async () => {
  renderPanel('json', '{"code":')

  expect(await screen.findByText('存在语法错误')).toBeInTheDocument()
  expect(screen.getByText('JSON 语法错误')).toBeInTheDocument()
})

it('点击类型胶囊写回表单的 bodyType', async () => {
  const formRef = renderPanel('json', '{}')
  const user = userEvent.setup()

  await user.click(screen.getByRole('tab', { name: 'raw' }))

  await waitFor(() => expect(formRef.current?.getFieldValue('bodyType')).toBe('raw'))
})

it('非 JSON 类型隐藏 JSON 专属动作，状态条只报大小与编码', async () => {
  renderPanel('raw', '')

  expect(await screen.findByText('无需校验')).toBeInTheDocument()
  expect(screen.queryByText('JSON Schema 合法')).toBeNull()
  expect(screen.queryByRole('button', { name: /插入变量/ })).toBeNull()
  expect(screen.getByText('编码: UTF-8')).toBeInTheDocument()
})
