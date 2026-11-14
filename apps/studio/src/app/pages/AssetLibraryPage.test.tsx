import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AssetLibraryPage } from './AssetLibraryPage'

vi.mock('@/features/test-cases/pages/CaseLibraryPage', () => ({
  CaseLibraryPage: () => <p>用例库内容</p>,
}))
vi.mock('@/features/interface-library/pages/InterfaceLibraryPage', () => ({
  InterfaceLibraryPage: () => <p>接口库内容</p>,
}))
vi.mock('@/features/interface-library/pages/ApiAppsPage', () => ({
  ApiAppsPage: () => <p>应用内容</p>,
}))

function LocationOutput() {
  const location = useLocation()
  return <output>{`${location.pathname}${location.search}`}</output>
}

function renderPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AssetLibraryPage />
      <LocationOutput />
    </MemoryRouter>,
  )
}

afterEach(cleanup)

describe('AssetLibraryPage', () => {
  it('defaults to the case library and keeps visited panes mounted', () => {
    renderPage('/asset-library')

    expect(screen.getByRole('status')).toHaveTextContent('/asset-library?tab=cases')
    expect(screen.getByRole('tab', { name: '用例库' })).toHaveAttribute('aria-selected', 'true')
    expect(document.getElementById('asset-panel-cases')).not.toHaveAttribute('hidden')

    fireEvent.click(screen.getByRole('tab', { name: '接口库' }))
    expect(screen.getByRole('status')).toHaveTextContent('/asset-library?tab=interfaces')
    expect(document.getElementById('asset-panel-interfaces')).not.toHaveAttribute('hidden')
    expect(document.getElementById('asset-panel-cases')).toHaveAttribute('hidden')
    expect(screen.getByText('用例库内容')).toBeInTheDocument()
    expect(screen.getByText('接口库内容')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: '应用' }))
    expect(screen.getByRole('status')).toHaveTextContent('/asset-library?tab=apps')
    expect(document.getElementById('asset-panel-apps')).not.toHaveAttribute('hidden')
    expect(screen.getByText('应用内容')).toBeInTheDocument()
  })

  it('supports arrow, home and end keys across the three asset tabs', () => {
    renderPage('/asset-library?tab=cases')

    const cases = screen.getByRole('tab', { name: '用例库' })
    fireEvent.keyDown(cases, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: '接口库' })).toHaveFocus()
    expect(screen.getByRole('status')).toHaveTextContent('/asset-library?tab=interfaces')

    fireEvent.keyDown(document.activeElement!, { key: 'End' })
    expect(screen.getByRole('tab', { name: '应用' })).toHaveFocus()
    expect(screen.getByRole('status')).toHaveTextContent('/asset-library?tab=apps')

    fireEvent.keyDown(document.activeElement!, { key: 'Home' })
    expect(screen.getByRole('status')).toHaveTextContent('/asset-library?tab=cases')
  })
})
