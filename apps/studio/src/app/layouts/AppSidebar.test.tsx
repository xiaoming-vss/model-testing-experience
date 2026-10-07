import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { AppSidebar } from './AppSidebar'

afterEach(cleanup)

describe('AppSidebar', () => {
  it('limits developer navigation to Bugs and restores navigation after switching roles', () => {
    const view = render(<MemoryRouter initialEntries={['/testing?tab=bugs']}><AppSidebar bugOnly /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Bug列表' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('button', { name: '项目总览' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '基础服务' })).not.toBeInTheDocument()
    view.rerender(<MemoryRouter initialEntries={['/testing?tab=bugs']}><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('button', { name: '项目总览' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '基础服务' })).toBeInTheDocument()
  })
  it('opens project navigation and preserves the selected board in the URL', () => {
    render(<MemoryRouter initialEntries={['/projects?board=requirements']}><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('link', { name: '需求' })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(screen.getByRole('link', { name: '迭代' }))
    expect(screen.getByRole('link', { name: '迭代' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: '需求' })).not.toHaveAttribute('aria-current')
    fireEvent.click(screen.getByRole('button', { name: '项目总览' }))
    expect(screen.queryByRole('link', { name: '迭代' })).not.toBeInTheDocument()
  })

  it('places test design navigation above testing navigation', () => {
    render(<MemoryRouter initialEntries={['/projects']}><AppSidebar /></MemoryRouter>)
    const groups = screen.getAllByRole('button').map((button) => button.textContent?.trim())
    expect(groups.indexOf('测试设计')).toBeLessThan(groups.indexOf('测试'))
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
    ['/bugs/12', 'Bug列表'],
    ['/api-automation/collections/12', 'API测试'],
    ['/ui-automation/suites/12', 'UI测试'],
    ['/testing?tab=functional', '用例库'],
  ])('selects the parent navigation for %s', (path, label) => {
    render(<MemoryRouter initialEntries={[path]}><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page')
  })

  it('does not restore an unrelated group when returning to requirement analysis', () => {
    render(<MemoryRouter initialEntries={['/ai-testing?kind=analysis']}><AppSidebar /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: '测试' }))
    fireEvent.click(screen.getByRole('link', { name: '功能测试' }))
    expect(screen.getByRole('button', { name: '测试' })).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(screen.getByRole('link', { name: '需求分析' }))
    expect(screen.getByRole('button', { name: '测试' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('link', { name: '需求分析' })).toHaveAttribute('aria-current', 'page')
  })

  it.each(['/projects', '/base-services', '/ai-testing?kind=analysis'])('does not expand testing outside its routes: %s', (path) => {
    render(<MemoryRouter initialEntries={[path]}><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('button', { name: '测试' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('switches testing tabs while preserving scope parameters', () => {
    render(<MemoryRouter initialEntries={['/testing?tab=library&requirementId=42']}><AppSidebar /></MemoryRouter>)
    const link = screen.getByRole('link', { name: 'UI测试' })
    expect(link).toHaveAttribute('href', '/testing?tab=ui&requirementId=42')
    fireEvent.click(link)
    expect(link).toHaveAttribute('aria-current', 'page')
  })
})
