import type { TemplatesProps } from '@/features/api-automation/components/apiCaseEditorProps'
import { ApiCaseHeadersPanel, type ApiCaseHeaderRow } from '@/features/api-automation/components/ApiCaseHeadersPanel'
import { TestThemeProvider as ThemeProvider } from '@/test/TestThemeProvider'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Form } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'

/*
 * 请求头面板按设计稿改成「快捷注入工具条 + 键值表 + 虚线新增行」，
 * 这组测试锁住四个入口：预设注入、回车新增、清空未启用、批量编辑 RAW。
 */

vi.mock('@/features/projects/hooks/useProjectAccess', () => ({
  useProjectAccess: () => ({ can: () => true, loading: false, error: null }),
}))
vi.mock('@/features/projects/hooks/projectScope', () => ({
  useScopedProjectId: () => 'project-1',
}))
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

function renderPanel(headers: ApiCaseHeaderRow[] = []) {
  const formRef: { current: ReturnType<typeof Form.useForm<{ headers: ApiCaseHeaderRow[] }>>[0] | null } = { current: null }

  function Harness() {
    const [form] = Form.useForm<{ headers: ApiCaseHeaderRow[] }>()
    formRef.current = form
    const watchedHeaders = Form.useWatch('headers', form) as ApiCaseHeaderRow[] | undefined

    return (
      <Form form={form} initialValues={{ headers }}>
        <ApiCaseHeadersPanel headers={watchedHeaders ?? []} templates={templates} />
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

it('快捷注入按预设补一行请求头，Accept 连值一起带上', async () => {
  const formRef = renderPanel()
  const user = userEvent.setup()

  await user.click(screen.getByRole('button', { name: '+Authorization' }))
  await user.click(screen.getByRole('button', { name: '+Accept: application/json' }))

  await waitFor(() =>
    expect(formRef.current?.getFieldValue('headers')).toEqual([
      { enabled: true, key: 'Authorization', value: '' },
      { enabled: true, key: 'Accept', value: 'application/json' },
    ]),
  )
  expect(screen.getByDisplayValue('Authorization')).toBeInTheDocument()
})

it('底部虚线行回车新增一行并清空草稿', async () => {
  const formRef = renderPanel()
  const user = userEvent.setup()

  await user.type(screen.getByPlaceholderText('添加新的请求头 (键)...'), 'X-Tenant-Id')
  // `user.type` 会把 `{` 当转义符，带 `{{变量}}` 的值直接改值更贴近真实输入。
  fireEvent.change(screen.getByPlaceholderText('值 (支持 {{变量}} 语法)...'), { target: { value: '{{tenant}}' } })
  fireEvent.keyDown(screen.getByPlaceholderText('添加新的请求头 (键)...'), { key: 'Enter' })

  await waitFor(() =>
    expect(formRef.current?.getFieldValue('headers')).toEqual([
      { enabled: true, key: 'X-Tenant-Id', value: '{{tenant}}' },
    ]),
  )
  expect(screen.getByPlaceholderText('添加新的请求头 (键)...')).toHaveValue('')
})

it('清空未启用只删掉勾掉的行，启用行原样留下', async () => {
  const formRef = renderPanel([
    { enabled: true, key: 'Content-Type', value: 'application/json' },
    { enabled: false, key: 'X-Legacy', value: 'gone' },
  ])
  const user = userEvent.setup()

  await user.click(screen.getByRole('button', { name: /清空未启用/ }))

  await waitFor(() =>
    expect(formRef.current?.getFieldValue('headers')).toEqual([
      { enabled: true, key: 'Content-Type', value: 'application/json' },
    ]),
  )
  expect(screen.queryByDisplayValue('X-Legacy')).toBeNull()
})

it('批量编辑按「名称: 值」逐行替换请求头', async () => {
  const formRef = renderPanel([{ enabled: true, key: 'Content-Type', value: 'application/json' }])
  const user = userEvent.setup()

  await user.click(screen.getByRole('button', { name: /批量编辑/ }))
  const textarea = await screen.findByLabelText('请求头批量编辑内容')
  fireEvent.change(textarea, { target: { value: 'Authorization: Bearer {{token}}\nX-Workspace-Id: WS-90281' } })
  // antd 会在两个汉字之间插空格，按钮的可访问名是「应 用」。
  await user.click(screen.getByRole('button', { name: /应\s*用/ }))

  await waitFor(() =>
    expect(formRef.current?.getFieldValue('headers')).toEqual([
      { enabled: true, key: 'Authorization', value: 'Bearer {{token}}' },
      { enabled: true, key: 'X-Workspace-Id', value: 'WS-90281' },
    ]),
  )
})

it('复制当前行把该行追加到表尾', async () => {
  const formRef = renderPanel([{ enabled: true, key: 'User-Agent', value: 'Mozilla/5.0' }])
  const user = userEvent.setup()

  await user.click(screen.getByRole('button', { name: '复制请求头' }))

  await waitFor(() =>
    expect(formRef.current?.getFieldValue('headers')).toEqual([
      { enabled: true, key: 'User-Agent', value: 'Mozilla/5.0' },
      { enabled: true, key: 'User-Agent', value: 'Mozilla/5.0' },
    ]),
  )
})
