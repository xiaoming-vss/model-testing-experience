import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ListPagination } from './ListPagination'

describe('ListPagination', () => {
  it('shows Chinese totals and returns to page one when page size changes', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ListPagination current={3} pageSize={20} total={120} onChange={onChange} />)
    expect(screen.getByText('显示第 41 条 - 第 60 条，共 120 条')).toBeInTheDocument()
    expect(screen.getByTitle('上一页')).toBeInTheDocument()
    expect(screen.getByTitle('下一页')).toBeInTheDocument()
    await user.click(screen.getByRole('combobox'))
    await user.click(screen.getByText('50 条/页'))
    expect(onChange).toHaveBeenCalledWith(1, 50)
  })

  it('waits for data before correcting a page emptied by deletion', () => {
    const onChange = vi.fn()
    const { rerender } = render(<ListPagination current={3} pageSize={20} total={0} loading onChange={onChange} />)
    expect(onChange).not.toHaveBeenCalled()
    rerender(<ListPagination current={3} pageSize={20} total={39} onChange={onChange} />)
    expect(onChange).toHaveBeenCalledWith(2, 20)
    expect(screen.getByText('显示第 21 条 - 第 39 条，共 39 条')).toBeInTheDocument()
  })

  it('keeps empty lists at page one', () => {
    const onChange = vi.fn()
    render(<ListPagination current={1} pageSize={20} total={0} onChange={onChange} />)
    expect(screen.getByText('显示第 0 条 - 第 0 条，共 0 条')).toBeInTheDocument()
    expect(onChange).not.toHaveBeenCalled()
  })
})
