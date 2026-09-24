import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { AppSidebar } from './AppSidebar'

afterEach(cleanup)

describe('AppSidebar', () => {
  it('opens project navigation and preserves the selected board in the URL', () => {
    render(<MemoryRouter initialEntries={['/projects?board=requirements']}><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('link', { name: '需求' })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(screen.getByRole('link', { name: '迭代' }))
    expect(screen.getByRole('link', { name: '迭代' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: '需求' })).not.toHaveAttribute('aria-current')
    fireEvent.click(screen.getByRole('button', { name: '项目总览' }))
    expect(screen.queryByRole('link', { name: '迭代' })).not.toBeInTheDocument()
  })

  it('supports collapsing the sidebar and reopening the testing group', () => {
    render(<MemoryRouter initialEntries={['/testing?tab=api']}><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'API测试' })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(screen.getByRole('button', { name: '收起侧边栏' }))
    expect(screen.queryByRole('link', { name: 'API测试' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '测试' }))
    expect(screen.getByRole('link', { name: 'API测试' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '测试' }))
    expect(screen.queryByRole('link', { name: 'API测试' })).not.toBeInTheDocument()
  })

  it.each([
    ['/test-orders/12', '测试单'],
    ['/api-automation/collections/12', 'API测试'],
    ['/ui-automation/suites/12', 'UI测试'],
    ['/testing?tab=functional', '用例库'],
  ])('selects the parent navigation for %s', (path, label) => {
    render(<MemoryRouter initialEntries={[path]}><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page')
  })

  it('switches testing tabs while preserving scope parameters', () => {
    render(<MemoryRouter initialEntries={['/testing?tab=library&requirementId=42']}><AppSidebar /></MemoryRouter>)
    const link = screen.getByRole('link', { name: 'UI测试' })
    expect(link).toHaveAttribute('href', '/testing?tab=ui&requirementId=42')
    fireEvent.click(link)
    expect(link).toHaveAttribute('aria-current', 'page')
  })
})
