import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BaseServicesPage } from './BaseServicesPage'

vi.mock('@/features/projects/hooks/useActiveProject', () => ({
  useActiveProject: () => ({ activeProjectId: 'project-1' }),
}))
vi.mock('../components/SharedServicesPanel', () => ({
  SharedServicesPanel: ({ provider }: { provider: string }) => <div>服务目录：{provider}</div>,
}))
afterEach(cleanup)

function renderPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <BaseServicesPage skillLibrary={<div>项目技能列表</div>} />
    </MemoryRouter>,
  )
}

describe('BaseServicesPage', () => {
  it.each([
    ['/base-services?tab=mcp', '服务目录：mcp'],
    ['/base-services?tab=llm', '服务目录：llm'],
    ['/base-services?tab=gitlab', '服务目录：gitlab'],
    ['/base-services?tab=zentao', '服务目录：mcp'],
    ['/base-services', '服务目录：llm'],
  ])('renders %s from its URL without an in-page tab bar', (path, content) => {
    renderPage(path)
    expect(screen.getByText(content)).toBeInTheDocument()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })

  it('renders the project skill library for the skills tab', () => {
    renderPage('/base-services?tab=skills')
    expect(screen.getByText('项目技能列表')).toBeInTheDocument()
  })
})
