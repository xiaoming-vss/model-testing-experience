import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { goBackOrFallback } from './backNavigation'

function ListPage() {
  const navigate = useNavigate()
  return <button onClick={() => navigate('/detail?id=1')}>go-detail</button>
}

function DetailPage() {
  const navigate = useNavigate()
  return <button onClick={() => goBackOrFallback(navigate, '/ai-testing?tab=tasks')}>back</button>
}

function FallbackPage() {
  return <div>fallback-list</div>
}

describe('goBackOrFallback 与 BrowserRouter 集成', () => {
  it('应用内跳转后回退到上一页', async () => {
    render(
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<ListPage />} />
          <Route path="/detail" element={<DetailPage />} />
          <Route path="/ai-testing" element={<FallbackPage />} />
        </Routes>
      </BrowserRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'go-detail' }))
    expect(screen.getByRole('button', { name: 'back' })).toBeInTheDocument()
    expect(window.history.state?.idx).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: 'back' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'go-detail' })).toBeInTheDocument())
  })
})
