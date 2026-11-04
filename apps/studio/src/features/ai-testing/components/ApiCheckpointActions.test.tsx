import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiCheckpointActions } from './ApiCheckpointActions'

const calls = vi.hoisted(() => ({ save: vi.fn(), review: vi.fn(), retry: vi.fn(), revise: vi.fn() }))
vi.mock('@/services/api', () => ({ api: {
  saveApiCaseStageOutput: calls.save, reviewApiCaseStage: calls.review,
  retryApiCaseStage: calls.retry, reviseApiCaseStage: calls.revise,
} }))
vi.mock('../hooks/usePersonalLlmChoice', () => ({ usePersonalLlmChoice: () => ({ choose: async () => 'personal-llm', dialog: null }) }))
afterEach(cleanup)

describe('API checkpoint', () => {
  it('requires edits to be saved before continuing and sends the edited configuration', async () => {
    const user = userEvent.setup()
    const changed = vi.fn()
    calls.save.mockResolvedValue({ runId: 'run', status: 'waiting_review' })
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    render(<QueryClientProvider client={client}><ApiCheckpointActions
      run={{ runId: 'run', checkpointEnabled: true, currentStage: 'openapi_extract', status: 'waiting_review', reviewStatus: 'pending', importStatus: 'pending', importedTargets: [], importedAt: null, configJson: JSON.stringify({ apiExtraction: { login: { path: '/old' } } }) }}
      projectId="project" canReview canWrite canExecute onChange={changed}
    /></QueryClientProvider>)
    await user.click(screen.getByRole('button', { name: '处理接口配置' }))
    const editor = screen.getByRole('textbox', { name: '接口配置 JSON' })
    fireEvent.change(editor, { target: { value: '{"login":{"path":"/new"}}' } })
    expect(screen.getByRole('button', { name: '审核并继续' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '保存配置' }))
    await waitFor(() => expect(calls.save).toHaveBeenCalledWith('run', { apiExtraction: { login: { path: '/new' } } }))
    expect(changed).toHaveBeenCalled()
  })

  it('uses the current user’s model authorization when continuing', async () => {
    const user = userEvent.setup()
    calls.review.mockResolvedValue({ runId: 'run', status: 'pending' })
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    render(<QueryClientProvider client={client}><ApiCheckpointActions
      run={{ runId: 'run', checkpointEnabled: true, currentStage: 'openapi_extract', status: 'waiting_review', reviewStatus: 'pending', importStatus: 'pending', importedTargets: [], importedAt: null, configJson: '{"apiExtraction":{"login":{"path":"/login"}}}' }}
      projectId="project" canReview canWrite canExecute onChange={vi.fn()}
    /></QueryClientProvider>)
    await user.click(screen.getByRole('button', { name: '处理接口配置' }))
    await user.click(screen.getByRole('button', { name: '审核并继续' }))
    await waitFor(() => expect(calls.review).toHaveBeenCalledWith('run', {
      stage: 'openapi_extract', action: 'approve', llmConnectionId: 'personal-llm', requestId: expect.any(String),
    }))
  })
})
