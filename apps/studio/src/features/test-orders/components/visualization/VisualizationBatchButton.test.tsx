import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { VisualizationBatchButton } from './VisualizationBatchButton'
const mocks = vi.hoisted(() => ({ batch: vi.fn(), getBatch: vi.fn(), choose: vi.fn() }))
vi.mock('../../api/caseVisualization.api', async original => ({ ...await original<typeof import('../../api/caseVisualization.api')>(), caseVisualizationApi: { batch: mocks.batch, getBatch: mocks.getBatch } }))
vi.mock('@/features/ai-testing/hooks/usePersonalLlmChoice', () => ({ usePersonalLlmChoice: () => ({ choose: mocks.choose, dialog: null }) }))
afterEach(cleanup)
beforeEach(() => { vi.clearAllMocks() })
describe('batch visualization', () => {
  it('freezes selection before model choice and shows per-entry dispositions', async () => {
    let resolveChoice: (value: string) => void = () => {}
    mocks.choose.mockImplementation(() => new Promise<string>(resolve => { resolveChoice = resolve }))
    const result = { batchId: 'batch', total: 2, counts: { skipped_available: 1, rejected: 1 }, items: [{ entryId: 'entry-one', disposition: 'skipped_available' }, { entryId: 'entry-two', disposition: 'rejected', errorMessage: '条目已不可用' }] }
    mocks.batch.mockResolvedValue(result); mocks.getBatch.mockResolvedValue(result)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const onSelect = vi.fn()
    const node = (ids: string[]) => <QueryClientProvider client={client}><VisualizationBatchButton orderId="order" projectId="project" entryIds={ids} onSelect={onSelect} /></QueryClientProvider>
    const view = render(node(['entry-one', 'entry-two']))
    fireEvent.click(screen.getByRole('button', { name: '生成所选图解（2）' }))
    await waitFor(() => expect(mocks.choose).toHaveBeenCalled())
    view.rerender(node(['entry-three']))
    resolveChoice('connection')
    await waitFor(() => expect(mocks.batch).toHaveBeenCalledWith('order', ['entry-one', 'entry-two'], 'connection', expect.any(String)))
    expect(await screen.findByText('条目已不可用')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'entry-one' }))
    expect(onSelect).toHaveBeenCalledWith('entry-one')
  })
  it('does not submit above the explicit batch limit', () => {
    const client = new QueryClient()
    render(<QueryClientProvider client={client}><VisualizationBatchButton orderId="order" entryIds={Array.from({ length: 101 }, (_, i) => `entry-${i}`)} onSelect={vi.fn()} /></QueryClientProvider>)
    expect(screen.getByRole('button', { name: '生成所选图解（101）' })).toBeDisabled()
    expect(mocks.batch).not.toHaveBeenCalled()
  })
})
