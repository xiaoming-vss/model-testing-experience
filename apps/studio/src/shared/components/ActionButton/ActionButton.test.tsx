import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Popconfirm } from 'antd'
import { afterEach, expect, it, vi } from 'vitest'
import { ActionButton } from './ActionButton'

afterEach(cleanup)

it('主要操作显示统一默认文字，也支持业务文案', () => {
  render(<><ActionButton operation="run" /><ActionButton operation="create">新建测试集</ActionButton></>)
  expect(screen.getByRole('button', { name: '运行' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '新建测试集' })).toBeInTheDocument()
})

it('纯图标按钮保留明确名称和悬浮提示', async () => {
  render(<ActionButton operation="edit" iconOnly aria-label="编辑需求" />)
  const button = screen.getByRole('button', { name: '编辑需求' })
  expect(button.textContent).toBe('')
  await userEvent.setup().hover(button)
  expect(await screen.findByRole('tooltip')).toHaveTextContent('编辑需求')
})

it('禁用和加载中的按钮不能执行操作', async () => {
  const click = vi.fn()
  render(<><ActionButton operation="run" disabled onClick={click} /><ActionButton operation="save" loading onClick={click} /></>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '运行' }))
  await user.click(screen.getByRole('button', { name: '保存' }))
  expect(click).not.toHaveBeenCalled()
})

it('删除保持红色并在现有确认框确认后才提交', async () => {
  const remove = vi.fn()
  render(<Popconfirm title="确认删除？" okText="确认删除" cancelText="取消" onConfirm={remove}>
    <ActionButton operation="delete" iconOnly />
  </Popconfirm>)
  const user = userEvent.setup()
  const button = screen.getByRole('button', { name: '删除' })
  expect(button.className).toContain('dangerous')
  await user.click(button)
  expect(remove).not.toHaveBeenCalled()
  await user.click(await screen.findByRole('button', { name: /取\s*消/ }))
  expect(remove).not.toHaveBeenCalled()
  await user.click(button)
  await user.click(await screen.findByRole('button', { name: '确认删除' }))
  await waitFor(() => expect(remove).toHaveBeenCalledTimes(1))
})
