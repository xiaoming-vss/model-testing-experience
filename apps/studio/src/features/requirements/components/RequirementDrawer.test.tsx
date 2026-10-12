import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Form } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'
import { seedOwnerProject } from '@/test/projectAccess'
import { RequirementDrawer } from './RequirementDrawer'

afterEach(cleanup)

function mount(content: string, documentError?: string) {
  const client = new QueryClient()
  seedOwnerProject(client)
  const onFinish = vi.fn()
  function FormHost() {
    const [form] = Form.useForm()
    return <><Form form={form} initialValues={{ name: '需求', documentType: 'richtext', documentContent: content }} />
      <RequirementDrawer title="新建需求" open form={form} loading={false} error={null} documentError={documentError} projectId="project-1" onClose={() => {}} onFinish={onFinish} />
    </>
  }
  render(<QueryClientProvider client={client}><FormHost /></QueryClientProvider>)
  return onFinish
}

it('rejects empty rich text paragraphs', async () => {
  const onFinish = mount('<p><br></p>')
  fireEvent.click(screen.getByRole('button', { name: '保存' }))
  expect(await screen.findByText('请输入需求正文')).toBeInTheDocument()
  expect(onFinish).not.toHaveBeenCalled()
})

it('submits HTML without converting it to plain text', async () => {
  const onFinish = mount('<h2>需求标题</h2><p><strong>必填规则</strong></p>')
  fireEvent.click(screen.getByRole('button', { name: '保存' }))
  await waitFor(() => expect(onFinish).toHaveBeenCalled())
  expect(onFinish.mock.calls[0][0]).toMatchObject({ documentType: 'richtext', documentContent: '<h2>需求标题</h2><p><strong>必填规则</strong></p>' })
})

it('blocks saving when source hydration failed', () => {
  mount('', '需求正文加载失败')
  expect(screen.getByRole('button', { name: '保存' })).toBeDisabled()
  expect(screen.getByText('需求正文加载失败')).toBeInTheDocument()
})
