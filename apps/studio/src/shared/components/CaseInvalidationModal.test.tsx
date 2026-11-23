import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { CaseInvalidationModal, type CaseInvalidationItem } from './CaseInvalidationModal'

const cases: CaseInvalidationItem[] = [
  { id: 'case-1', name: '登录成功', invalidatedAt: '2026-11-22T02:30:00Z' },
  { id: 'case-2', name: '登录失败', invalidatedAt: null },
  { id: 'case-3', name: '退出系统', invalidatedAt: null },
]

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderModal(props: Partial<ComponentProps<typeof CaseInvalidationModal>> = {}) {
  const onSubmit = vi.fn()
  const view = render(
    <CaseInvalidationModal
      open
      scopeLabel="登录接口集 · 3 条用例"
      cases={cases}
      canWrite
      onClose={() => {}}
      onSubmit={onSubmit}
      {...props}
    />,
  )
  return { ...view, onSubmit }
}

/** 弹窗里的复选框顺序固定为：全选、然后按当前筛选后的用例顺序。 */
function checkboxes() {
  return [...document.querySelectorAll<HTMLInputElement>('.ant-modal input[type="checkbox"]')]
}

function selectAllLabel() {
  return document.querySelector('.ant-modal .ant-checkbox-wrapper') as HTMLElement
}

it('展示范围、状态与失效时间，未选择时两个提交动作都不可用', async () => {
  renderModal()

  expect(screen.getByText('管理用例状态')).toBeInTheDocument()
  expect(screen.getByText('当前范围：登录接口集 · 3 条用例')).toBeInTheDocument()
  expect(screen.getByText(/已失效/, { selector: '.tp-tone-tag' })).toBeInTheDocument()
  expect(screen.getByText(/2026\/11\/22 10:30/)).toBeInTheDocument()
  expect(selectAllLabel()).toHaveTextContent('全选（当前筛选 3 条）')

  expect(screen.getByRole('button', { name: '标记失效' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '恢复有效' })).toBeDisabled()
  expect(checkboxes()).toHaveLength(4)
})

it('全选当前筛选后提交失效，并回传全部可见用例', async () => {
  const { onSubmit } = renderModal()
  const user = userEvent.setup()

  await user.click(checkboxes()[0])
  await waitFor(() => expect(screen.getByText('已选 3 条')).toBeInTheDocument())
  await user.click(screen.getByRole('button', { name: '标记失效' }))

  expect(onSubmit).toHaveBeenCalledWith(['case-1', 'case-2', 'case-3'], true)
})

it('搜索后全选只覆盖匹配用例，恢复有效回传 false', async () => {
  const { onSubmit } = renderModal()
  const user = userEvent.setup()

  await user.type(screen.getByPlaceholderText('搜索用例名称'), '登录')
  await waitFor(() => expect(selectAllLabel()).toHaveTextContent('全选（当前筛选 2 条）'))
  expect(screen.queryByText('退出系统')).toBeNull()

  await user.click(checkboxes()[0])
  await waitFor(() => expect(screen.getByText('已选 2 条')).toBeInTheDocument())
  await user.click(screen.getByRole('button', { name: '恢复有效' }))

  expect(onSubmit).toHaveBeenCalledWith(['case-1', 'case-2'], false)
})

it('没有写权限时即使勾选了用例也不能提交', async () => {
  renderModal({ canWrite: false })
  const user = userEvent.setup()

  await user.click(checkboxes()[1])
  await waitFor(() => expect(screen.getByText('已选 1 条')).toBeInTheDocument())
  expect(screen.getByRole('button', { name: '标记失效' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '恢复有效' })).toBeDisabled()
})
