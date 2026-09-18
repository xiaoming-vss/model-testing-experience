import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ImportMigrationWarning } from './ImportMigrationWarning'

describe('ImportMigrationWarning', () => {
  it('历史功能套件目标未完整恢复时显示非阻塞提示', () => {
    render(<ImportMigrationWarning importMigrationComplete={false} />)

    expect(screen.getByText('历史导入目标数据不完整')).toBeInTheDocument()
    expect(screen.getByText(/不影响查看、审核或继续处理当前运行/)).toBeInTheDocument()
  })

  it('迁移完整时不显示提示', () => {
    const { container } = render(<ImportMigrationWarning importMigrationComplete />)

    expect(container).toBeEmptyDOMElement()
  })
})
