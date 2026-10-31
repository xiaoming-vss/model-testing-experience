import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, expect, it } from 'vitest'
import type { ReactNode } from 'react'
import { RequirementCards } from './RequirementCards'
import type { RequirementListItem } from '@/features/requirements/types'

afterEach(cleanup)

function LocationProbe() {
  return <output data-testid="location">{useLocation().pathname}</output>
}

const requirement: RequirementListItem = {
  requirementId: 'req-1',
  name: '身份与权限',
  sprintName: 'v1.2.0',
  createdAt: '2026-09-17T11:38:00Z',
}

function mount(renderActions: () => ReactNode = () => null) {
  return render(<MemoryRouter initialEntries={['/']}>
    <RequirementCards requirements={[requirement]} renderActions={renderActions} renderBinding={() => null} />
    <LocationProbe />
  </MemoryRouter>)
}

it('clicks anywhere on the card to open the requirement', () => {
  mount()
  fireEvent.click(document.querySelector('.requirements-card')!)
  expect(screen.getByTestId('location')).toHaveTextContent('/requirements/req-1')
})

it('keeps card actions from opening the requirement', () => {
  let clicks = 0
  mount(() => <button type="button" onClick={() => { clicks += 1 }}>编辑需求</button>)
  fireEvent.click(screen.getByRole('button', { name: '编辑需求' }))
  expect(clicks).toBe(1)
  expect(screen.getByTestId('location').textContent).toBe('/')
})

it('renders the requirement name before the document status', () => {
  mount()
  const title = screen.getByRole('heading', { name: '身份与权限' })
  const documentStatus = screen.getByText('未提供文档')
  expect(title.compareDocumentPosition(documentStatus) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})
