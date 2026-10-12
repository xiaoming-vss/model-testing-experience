import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TestingPage } from './TestingPage'

vi.mock('@/features/api-automation/pages/ApiAutomationPage', () => ({ ApiAutomationPage: () => <p>API内容</p> }))
vi.mock('@/features/ui-automation/pages/UiAutomationPage', () => ({ UiAutomationPage: () => <p>UI内容</p> }))
vi.mock('@/features/bugs/pages/BugListPage', () => ({ BugListPage: () => <p>Bug内容</p> }))
vi.mock('@/features/test-cases/pages/CaseLibraryPage', () => ({ CaseLibraryPage: () => <p>用例内容</p> }))
vi.mock('@/features/test-orders/pages/TestOrderPage', () => ({ TestOrderPage: () => <p>测试单内容</p> }))
afterEach(cleanup)

function LocationControls() {
  const location = useLocation()
  const navigate = useNavigate()
  return <><output>{location.search}</output><button onClick={() => navigate(-1)}>返回</button></>
}
function setup(path: string) {
  render(<MemoryRouter initialEntries={[path]}><TestingPage /><LocationControls /></MemoryRouter>)
}

// jsdom 的 getComputedStyle 会滞后于 hidden 属性切换，role 查询对刚切换过的面板不可靠；
// 标签页的可见性契约直接按 hidden 属性断言（与实现一致，浏览器行为相同）。
function expectPaneState(tab: string, options: { visible: boolean; text: string }) {
  const pane = document.getElementById(`testing-panel-${tab}`)
  expect(pane, `pane for ${tab}`).not.toBeNull()
  expect(pane!.hidden).toBe(!options.visible)
  expect(pane).toHaveTextContent(options.text)
}

describe('Testing workspace navigation', () => {
  it('defaults to orders and preserves scope when switching and navigating back', () => {
    setup('/testing?requirementId=42&sprintId=7')
    expect(screen.getByRole('tab', { name: '测试单' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('tab', { name: 'API测试' }))
    expectPaneState('api', { visible: true, text: 'API内容' })
    expectPaneState('orders', { visible: false, text: '测试单内容' })
    expect(screen.getByRole('status')).toHaveTextContent('?requirementId=42&sprintId=7&tab=api')
    fireEvent.click(screen.getByRole('button', { name: '返回' }))
    expectPaneState('orders', { visible: true, text: '测试单内容' })
    expectPaneState('api', { visible: false, text: 'API内容' })
  })
  it('supports keyboard navigation and legacy library links', () => {
    setup('/testing?tab=functional')
    const tab = screen.getByRole('tab', { name: '用例库' })
    expect(tab).toHaveAttribute('aria-selected', 'true')
    fireEvent.keyDown(tab, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: 'API测试' })).toHaveFocus()
    expectPaneState('api', { visible: true, text: 'API内容' })
    fireEvent.keyDown(document.activeElement!, { key: 'End' })
    expectPaneState('ui', { visible: true, text: 'UI内容' })
    expectPaneState('api', { visible: false, text: 'API内容' })
  })
  it('keeps the Bug route independent without exposing testing tabs', () => {
    setup('/testing?tab=bugs')
    expect(screen.getByText('Bug内容')).toBeVisible()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '测试' })).not.toBeInTheDocument()
  })
})
