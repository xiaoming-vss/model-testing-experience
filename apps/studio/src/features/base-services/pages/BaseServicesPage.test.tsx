import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { BaseServicesPage } from './BaseServicesPage'

vi.mock('@/features/projects/hooks/useActiveProject', () => ({
  useActiveProject: () => ({ activeProjectId: 'project-1' }),
}))
vi.mock('../components/SharedServicesPanel', () => ({
  SharedServicesPanel: ({ provider }: { provider: string }) => <div>服务目录：{provider}</div>,
}))
afterEach(cleanup)
function Route() {
  return <><BaseServicesPage skillLibrary={<div>项目技能列表</div>} /><output>{useLocation().search}</output></>
}
it('renders the MCP tab from its URL and preserves the Skill library entry', () => {
  render(<MemoryRouter initialEntries={['/base-services?tab=mcp']}><Route /></MemoryRouter>)
  expect(screen.getByRole('tab', { name: 'MCP' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByText('服务目录：mcp')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('tab', { name: 'Skill库' }))
  expect(screen.getByText('项目技能列表')).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('?tab=skills')
  fireEvent.click(screen.getByRole('tab', { name: 'MCP' }))
  expect(screen.getByText('服务目录：mcp')).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('?tab=mcp')
})
