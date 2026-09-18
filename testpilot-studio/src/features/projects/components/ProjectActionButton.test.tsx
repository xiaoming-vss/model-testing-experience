import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Popconfirm } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'
import { ProjectActionButton } from './ProjectActionButton'

const access = vi.hoisted(() => ({ allowed: false }))
vi.mock('../hooks/useProjectAccess', () => ({ useProjectAccess: () => ({ can: () => access.allowed }) }))
vi.mock('../hooks/projectScope', () => ({ useScopedProjectId: () => 'project' }))
afterEach(() => { cleanup(); access.allowed = false })

it('无权限时统一删除按钮禁用，不能打开外层确认框', async () => {
  const remove = vi.fn()
  render(<Popconfirm title="确认删除项目？" onConfirm={remove}>
    <ProjectActionButton action="manage" operation="delete" iconOnly />
  </Popconfirm>)
  const button = screen.getByRole('button', { name: '删除' })
  expect(button).toBeDisabled()
  await userEvent.setup().click(button)
  expect(screen.queryByText('确认删除项目？')).toBeNull()
  expect(remove).not.toHaveBeenCalled()
})

it('有权限时统一运行按钮保留执行事件', async () => {
  access.allowed = true
  const run = vi.fn()
  render(<ProjectActionButton action="execute" operation="run" onClick={run} />)
  await userEvent.setup().click(screen.getByRole('button', { name: '运行' }))
  expect(run).toHaveBeenCalledTimes(1)
})
