import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TestingPage } from './TestingPage'

vi.mock('@/features/api-automation/pages/ApiAutomationPage', () => ({ ApiAutomationPage: () => <p>API内容</p> }))
vi.mock('@/features/ui-automation/pages/UiAutomationPage', () => ({ UiAutomationPage: () => <p>UI内容</p> }))
vi.mock('@/features/bugs/pages/BugListPage', () => ({ BugListPage: () => <p>Bug内容</p> }))
vi.mock('@/features/test-orders/pages/TestOrderPage', () => ({ TestOrderPage: () => <p>测试单内容</p> }))
afterEach(cleanup)

function LocationControls() {
  const location = useLocation()
  const navigate = useNavigate()
  function goToTab(tab: string) {
    const params = new URLSearchParams(location.search)
    params.set('tab', tab)
    navigate(`?${params}`)
  }
  return <>
    <output>{location.search}</output>
    <button onClick={() => goToTab('api')}>去API</button>
    <button onClick={() => goToTab('ui')}>去UI</button>
    <button onClick={() => navigate(-1)}>返回</button>
  </>
}
function setup(path: string) {
  render(<MemoryRouter initialEntries={[path]}><TestingPage /><LocationControls /></MemoryRouter>)
}

function setupWithAssetRoute(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/testing" element={<TestingPage />} />
        <Route path="/asset-library" element={<p>资产库内容</p>} />
      </Routes>
      <LocationControls />
    </MemoryRouter>,
  )
}

// jsdom 的 getComputedStyle 会滞后于 hidden 属性切换，可见性契约直接按 hidden 属性断言。
function expectPaneState(tab: string, options: { visible: boolean; text: string }) {
  const pane = document.getElementById(`testing-panel-${tab}`)
  expect(pane, `pane for ${tab}`).not.toBeNull()
  expect(pane!.hidden).toBe(!options.visible)
  expect(pane).toHaveTextContent(options.text)
}

describe('Testing workspace navigation', () => {
  it('defaults to orders and keeps the page free of a duplicate tab bar', async () => {
    setup('/testing?requirementId=42&sprintId=7')
    await screen.findByText('测试单内容')
    expectPaneState('orders', { visible: true, text: '测试单内容' })
    expect(document.getElementById('testing-panel-api')).toBeNull()
    expect(document.getElementById('testing-panel-ui')).toBeNull()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '测试单' })).not.toBeInTheDocument()
  })

  it('switches panes from the URL, preserves scope and keeps visited panes mounted', async () => {
    setup('/testing?requirementId=42&sprintId=7')
    await screen.findByText('测试单内容')
    fireEvent.click(screen.getByRole('button', { name: '去API' }))
    await screen.findByText('API内容')
    expectPaneState('api', { visible: true, text: 'API内容' })
    expectPaneState('orders', { visible: false, text: '测试单内容' })
    expect(screen.getByRole('status')).toHaveTextContent('?requirementId=42&sprintId=7&tab=api')

    fireEvent.click(screen.getByRole('button', { name: '去UI' }))
    await screen.findByText('UI内容')
    expectPaneState('ui', { visible: true, text: 'UI内容' })
    expectPaneState('api', { visible: false, text: 'API内容' })

    fireEvent.click(screen.getByRole('button', { name: '返回' }))
    expectPaneState('api', { visible: true, text: 'API内容' })
    expectPaneState('ui', { visible: false, text: 'UI内容' })
    expectPaneState('orders', { visible: false, text: '测试单内容' })
  })

  it('redirects legacy library tabs to the asset library', async () => {
    setupWithAssetRoute('/testing?tab=functional')
    expect(await screen.findByText('资产库内容')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('?tab=cases')
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })

  it('keeps the Bug route independent without exposing testing tabs', async () => {
    setup('/testing?tab=bugs')
    expect(await screen.findByText('Bug内容')).toBeVisible()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '测试' })).not.toBeInTheDocument()
  })
})
