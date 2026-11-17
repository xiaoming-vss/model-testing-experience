import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { AppSidebar } from './AppSidebar'

afterEach(cleanup)

function LocationOutput() {
  const location = useLocation()
  return <output>{`${location.pathname}${location.search}`}</output>
}

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

  it('hides testing tabs until the testing entry is hovered', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/testing?tab=api']}><AppSidebar /></MemoryRouter>)
    const trigger = screen.getByRole('link', { name: '测试' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(trigger).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('link', { name: '测试单' })).not.toBeInTheDocument()

    await user.hover(trigger)
    expect(await screen.findByRole('link', { name: '测试单' })).toBeInTheDocument()
    const popoverContainer = document.querySelector<HTMLElement>('.top-nav-menu-popover .ant-popover-container')
    expect(popoverContainer).not.toBeNull()
    expect(popoverContainer!.style.padding).toBe('8px')
    expect(screen.getByRole('link', { name: 'API测试' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'UI测试' })).not.toHaveAttribute('aria-current')
    await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'true'))
  })

  it('navigates from the hover menu and preserves the current scope', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/testing?requirementId=42']}><AppSidebar /><LocationOutput /></MemoryRouter>)
    await user.hover(screen.getByRole('link', { name: '测试' }))
    await user.click(await screen.findByRole('link', { name: 'API测试' }))
    expect(screen.getByRole('status')).toHaveTextContent('/testing?requirementId=42&tab=api')
    await waitFor(() => expect(screen.getByRole('link', { name: '测试' })).toHaveAttribute('aria-expanded', 'false'))
  })

  it('places the asset library next to base services', () => {
    render(<MemoryRouter initialEntries={['/testing?tab=orders']}><AppSidebar /></MemoryRouter>)
    const nav = screen.getByRole('navigation', { name: '主导航' })
    const labels = Array.from(nav.querySelectorAll<HTMLElement>('.sidebar-link-label')).map(element => element.textContent)
    expect(labels).toEqual(['迭代', '需求', '测试', 'Bug列表', '资产库', '基础服务'])
  })

  it('opens testing tabs with the keyboard and supports arrows and Escape', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/testing?tab=api']}><AppSidebar /></MemoryRouter>)
    const trigger = screen.getByRole('link', { name: '测试' })
    trigger.focus()
    await user.keyboard('{ArrowDown}')
    const apiLink = await screen.findByRole('link', { name: 'API测试' })
    await waitFor(() => expect(apiLink).toHaveFocus())
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('link', { name: 'UI测试' })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(trigger).toHaveFocus()
    await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'false'))
  })

  it('hides asset library tabs until hovered and preserves scope when navigating', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/asset-library?tab=interfaces&foo=1']}><AppSidebar /><LocationOutput /></MemoryRouter>)
    const trigger = screen.getByRole('link', { name: '资产库' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(trigger).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('link', { name: '用例库' })).not.toBeInTheDocument()

    await user.hover(trigger)
    expect(await screen.findByRole('link', { name: '用例库' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '接口库' })).toHaveAttribute('aria-current', 'page')
    await user.click(screen.getByRole('link', { name: '软件仓库' }))
    expect(screen.getByRole('status')).toHaveTextContent('/asset-library?tab=repositories&foo=1')
    await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'false'))
  })

  it('keeps an open interface detail on the asset library trigger', () => {
    render(<MemoryRouter initialEntries={['/asset-library/interfaces/12']}><AppSidebar /></MemoryRouter>)
    const trigger = screen.getByRole('link', { name: '资产库' })
    expect(trigger).toHaveAttribute('href', '/asset-library/interfaces/12')
    expect(trigger).toHaveAttribute('aria-current', 'page')
  })

  it('keeps only one top navigation submenu open at a time', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/testing?tab=orders']}><AppSidebar /></MemoryRouter>)
    const assets = screen.getByRole('link', { name: '资产库' })
    const services = screen.getByRole('link', { name: '基础服务' })

    await user.hover(assets)
    expect(await screen.findByRole('link', { name: '用例库' })).toBeInTheDocument()
    await user.hover(services)
    expect(await screen.findByRole('link', { name: 'Skill库' })).toBeInTheDocument()
    await waitFor(() => expect(assets).toHaveAttribute('aria-expanded', 'false'))
    expect(services).toHaveAttribute('aria-expanded', 'true')
  })

  it('hides base service tabs until hovered and navigates between them', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/base-services?tab=mcp']}><AppSidebar /><LocationOutput /></MemoryRouter>)
    const trigger = screen.getByRole('link', { name: '基础服务' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(trigger).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('link', { name: 'Skill库' })).not.toBeInTheDocument()

    await user.hover(trigger)
    expect(await screen.findByRole('link', { name: 'Skill库' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'MCP' })).toHaveAttribute('aria-current', 'page')
    await user.click(screen.getByRole('link', { name: 'GitLab' }))
    expect(screen.getByRole('status')).toHaveTextContent('/base-services?tab=gitlab')
    await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'false'))
  })
})
