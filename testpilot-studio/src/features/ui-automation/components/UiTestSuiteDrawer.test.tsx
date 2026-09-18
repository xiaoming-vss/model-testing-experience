import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { seedOwnerProject } from '@/test/projectAccess'
import { Form } from 'antd'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { UiTestSuiteDrawer, type UiTestSuiteFormValues } from './UiTestSuiteDrawer'

function DrawerHarness() {
  const [form] = Form.useForm<UiTestSuiteFormValues>()

  return (
    <UiTestSuiteDrawer
      title="新建 UI测试集"
      open
      form={form}
      loading={false}
      error={null}
      onClose={vi.fn()}
      sprintOptions={[{ label: 'v1.0.0', value: 'sprint-1' }]}
      requirementOptions={[
        { label: '全部需求', value: 'all' },
        { label: '安装部署', value: 'requirement-1' },
      ]}
      onFinish={vi.fn()}
    />
  )
}

afterEach(cleanup)

describe('UiTestSuiteDrawer', () => {
  it('所属需求只展示可关联的具体需求', async () => {
    const user = userEvent.setup()
    const client = new QueryClient()
    seedOwnerProject(client)
    render(<QueryClientProvider client={client}><DrawerHarness /></QueryClientProvider>)

    await user.click(screen.getByRole('combobox', { name: '所属需求' }))

    expect(await screen.findByRole('option', { name: '安装部署' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: '全部需求' })).not.toBeInTheDocument()
  })
})
