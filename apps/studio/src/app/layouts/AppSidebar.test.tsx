import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { AppSidebar } from './AppSidebar'

afterEach(cleanup)

describe('AppSidebar', () => {
  it('limits developer navigation to Bugs and restores navigation after switching roles', () => {
    const view = render(<MemoryRouter initialEntries={['/testing?tab=bugs']}><AppSidebar bugOnly /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Bug列表' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('link', { name: '迭代' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '基础服务' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '代码风险分析' })).not.toBeInTheDocument()
    view.rerender(<MemoryRouter initialEntries={['/testing?tab=bugs']}><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('link', { name: '迭代' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '基础服务' })).toBeInTheDocument()
  })
  it('shows iterations and requirements as top-level links and preserves the selected board', () => {
    render(<MemoryRouter initialEntries={['/projects?board=requirements']}><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('link', { name: '需求' })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(screen.getByRole('link', { name: '迭代' }))
    expect(screen.getByRole('link', { name: '迭代' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: '需求' })).not.toHaveAttribute('aria-current')
    expect(screen.queryByRole('button', { name: '项目总览' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '迭代' }).parentElement).toHaveAttribute('aria-label', '主导航')
  })

  it('design operations live in requirement detail; 代码风险分析 has no standalone sidebar entry', () => {
    render(<MemoryRouter initialEntries={['/requirements/req']}><AppSidebar /></MemoryRouter>)
    expect(screen.queryByRole('button', { name: '测试设计' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '需求' })).toHaveAttribute('aria-current', 'page')
    // 代码风险分析并入需求工作区 Tab，与其他生成类型一致，不再有侧边栏入口。
    expect(screen.queryByRole('link', { name: '代码风险分析' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '迭代' })).toBeVisible()
    expect(screen.getByRole('link', { name: '需求' })).toBeVisible()
  })

  it('keeps Testing and Bugs accessible in the top navigation', () => {
    render(<MemoryRouter initialEntries={['/testing?tab=api']}><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('link', { name: '测试' })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(screen.getByRole('link', { name: 'Bug列表' }))
    expect(screen.getByRole('link', { name: 'Bug列表' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: '测试' })).not.toHaveAttribute('aria-current')
    expect(screen.getByRole('navigation', { name: '主导航' })).toHaveClass('top-navigation-links')
  })

  it.each([
    ['/test-orders/12', '测试'],
    ['/bugs/12', 'Bug列表'],
    ['/api-automation/collections/12', '测试'],
    ['/ui-automation/suites/12', '测试'],
    ['/asset-library/interfaces/12', '资产库'],
    ['/asset-library?tab=apps', '资产库'],
    ['/testing?tab=functional', '测试'],
  ])('selects the parent navigation for %s', (path, label) => {
    render(<MemoryRouter initialEntries={[path]}><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('link', { name: label })).toHaveAttribute('aria-current', 'page')
  })

  it('keeps Bugs scope and places services in the main navigation', () => {
    render(<MemoryRouter initialEntries={['/testing?tab=library&requirementId=42']}><AppSidebar /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Bug列表' })).toHaveAttribute('href', '/testing?tab=bugs&requirementId=42')
    expect(screen.getByRole('link', { name: '基础服务' }).parentElement).toHaveAttribute('aria-label', '主导航')
  })
})
