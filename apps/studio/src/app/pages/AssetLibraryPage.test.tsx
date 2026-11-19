import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AssetLibraryPage } from './AssetLibraryPage'

vi.mock('@/features/test-cases/pages/CaseLibraryPage', () => ({
  CaseLibraryPage: () => <p>用例库内容</p>,
}))
vi.mock('@/features/interface-library/pages/InterfaceLibraryPage', () => ({
  InterfaceLibraryPage: () => <p>接口库内容</p>,
}))
vi.mock('@/features/interface-library/pages/SoftwareRepositoriesPage', () => ({
  SoftwareRepositoriesPage: () => <p>软件仓库内容</p>,
}))

function LocationControls() {
  const location = useLocation()
  const navigate = useNavigate()
  function goToTab(tab: string) {
    const params = new URLSearchParams(location.search)
    params.set('tab', tab)
    navigate(`/asset-library?${params}`)
  }
  return <>
    <output>{`${location.pathname}${location.search}`}</output>
    <button onClick={() => goToTab('interfaces')}>去接口库</button>
    <button onClick={() => goToTab('repositories')}>去软件仓库</button>
  </>
}

function renderPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AssetLibraryPage />
      <LocationControls />
    </MemoryRouter>,
  )
}

afterEach(cleanup)

function expectPaneState(tab: string, options: { visible: boolean; text: string }) {
  const pane = document.getElementById(`asset-panel-${tab}`)
  expect(pane, `pane for ${tab}`).not.toBeNull()
  expect(pane!.hidden).toBe(!options.visible)
  expect(pane).toHaveTextContent(options.text)
}

describe('AssetLibraryPage', () => {
  it('defaults to the case library and keeps the page free of a duplicate tab bar', async () => {
    renderPage('/asset-library')

    expect(await screen.findByText('用例库内容')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('/asset-library?tab=cases')
    expectPaneState('cases', { visible: true, text: '用例库内容' })
    expect(document.getElementById('asset-panel-interfaces')).toBeNull()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: '用例库' })).not.toBeInTheDocument()
  })

  it('switches panes from the URL and keeps visited panes mounted', async () => {
    renderPage('/asset-library?tab=cases')
    await screen.findByText('用例库内容')

    fireEvent.click(screen.getByRole('button', { name: '去接口库' }))
    expect(await screen.findByText('接口库内容')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('/asset-library?tab=interfaces')
    expectPaneState('interfaces', { visible: true, text: '接口库内容' })
    expectPaneState('cases', { visible: false, text: '用例库内容' })

    fireEvent.click(screen.getByRole('button', { name: '去软件仓库' }))
    expect(await screen.findByText('软件仓库内容')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('/asset-library?tab=repositories')
    expectPaneState('repositories', { visible: true, text: '软件仓库内容' })
    expectPaneState('interfaces', { visible: false, text: '接口库内容' })
  })
})
