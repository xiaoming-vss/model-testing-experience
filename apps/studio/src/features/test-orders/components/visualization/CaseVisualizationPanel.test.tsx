import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest'
import examples from '../../fixtures/visualization.json'
import type { Visualization, VisualizationState } from '../../visualizationTypes'
import { CaseVisualizationPanel } from './CaseVisualizationPanel'

const mocks = vi.hoisted(() => ({ get: vi.fn(), generate: vi.fn(), choose: vi.fn() }))
vi.mock('../../api/caseVisualization.api', async importOriginal => ({ ...await importOriginal<typeof import('../../api/caseVisualization.api')>(), caseVisualizationApi: { get: mocks.get, generate: mocks.generate } }))
vi.mock('@/features/ai-testing/hooks/usePersonalLlmChoice', () => ({ usePersonalLlmChoice: () => ({ choose: mocks.choose, dialog: null }) }))
const output = examples[0].output as Visualization
const ready: VisualizationState = { executionEntryId: 'entry-example', snapshotHash: 'hash', unavailableReason: null, latestRun: { runId: 'run', status: 'success', artifactStatus: 'ready', errorMessage: null }, effectiveArtifact: { artifactId: 'artifact', runId: 'run', schemaVersion: '1.0', status: 'ready', content: output } }
function setup(mode: 'text' | 'visual' = 'text') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  const onMode = vi.fn()
  const result = render(<QueryClientProvider client={client}><CaseVisualizationPanel orderId="order" entryId="entry-example" projectId="project" snapshot={examples[0].input.content} canGenerate preferredMode={mode} onMode={onMode} /></QueryClientProvider>)
  return { ...result, client, onMode }
}
beforeEach(() => { vi.clearAllMocks(); mocks.get.mockResolvedValue(ready); mocks.choose.mockResolvedValue('connection'); mocks.generate.mockResolvedValue({ disposition: 'queued' }) })
afterEach(cleanup)

describe('case visualization reading', () => {
  it('defaults to text, switches explicitly and presents only flow and verification focus', async () => {
    const { onMode } = setup()
    await screen.findByText('重新生成')
    expect(screen.getByRole('table')).toBeInTheDocument()
    fireEvent.click(screen.getByText('可视化'))
    await screen.findByText('场景流程')
    expect(onMode).toHaveBeenCalledWith('visual')
    expect(screen.getByRole('heading', { name: '验证焦点' })).toBeInTheDocument()
    expect(screen.queryByText('当前步骤图解')).not.toBeInTheDocument()
    expect(screen.queryByText(/其他步骤图解/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('图解原文依据')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /依据|原文/ })).not.toBeInTheDocument()
  })
  it('falls back without changing preference when no artifact exists', async () => {
    mocks.get.mockResolvedValue({ ...ready, effectiveArtifact: null, latestRun: null })
    const { onMode } = setup('visual')
    await screen.findByText('生成可视化')
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(onMode).not.toHaveBeenCalled()
  })
  it('does not switch text view when generation completes', async () => {
    mocks.get.mockResolvedValueOnce({ ...ready, effectiveArtifact: null, latestRun: null }).mockResolvedValue(ready)
    setup('visual')
    const button = await screen.findByRole('button', { name: '生成可视化' })
    await waitFor(() => expect(button).toBeEnabled())
    fireEvent.click(button)
    await waitFor(() => expect(mocks.generate).toHaveBeenCalledTimes(1))
    await screen.findByText('重新生成')
    expect(screen.getByRole('table')).toBeInTheDocument()
  })
  it('keeps old diagram visible after failed regeneration', async () => {
    mocks.get.mockResolvedValue({ ...ready, latestRun: { ...ready.latestRun, status: 'failed', artifactStatus: null, errorMessage: '图解生成失败' } })
    setup('visual')
    await screen.findByText('场景流程')
    expect(screen.getByText('已有图解继续可用。')).toBeInTheDocument()
  })
})

describe('step and diagram linkage', () => {
  it('links navigation, expected text and diagrams without recording execution results', async () => {
    const next = structuredClone(output)
    next.sources.push({ id: 'a1', field: 'action', index: 1 }, { id: 'e1', field: 'expected', index: 1 })
    next.assertions.push({ id: 'second-assertion', text: '第二步预期', sourceIds: ['e1'], entityIds: [] })
    next.visuals[0].title = '第一步图解'
    next.visuals.push({ ...structuredClone(next.visuals[0]), id: 'second-visual', title: '第二步图解', sourceIds: ['a1', 'e1'], assertionIds: ['second-assertion'] })
    mocks.get.mockResolvedValue({ ...ready, effectiveArtifact: { ...ready.effectiveArtifact, content: next } })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    render(<QueryClientProvider client={client}><CaseVisualizationPanel orderId="order" entryId="entry-example" snapshot={{ preconditions: [], steps: [...examples[0].input.content.steps, { action: '再次打开选择框', expected: '第二步预期' }] }} canGenerate={false} preferredMode="visual" onMode={vi.fn()} /></QueryClientProvider>)
    await screen.findByText('场景流程')
    expect(screen.getByRole('button', { name: /上一步/ })).toBeDisabled()
    expect(screen.getByLabelText('第一步图解')).toBeVisible()
    expect(screen.getByLabelText('第二步图解')).not.toHaveClass('is-current')
    fireEvent.click(screen.getByRole('button', { name: /下一步/ }))
    expect(screen.getByLabelText('当前步骤预期')).toHaveTextContent('第二步预期')
    expect(screen.getByLabelText('第二步图解')).toHaveClass('is-current')
    expect(screen.getByLabelText('第一步图解')).not.toHaveClass('is-current')
    expect(screen.getByRole('button', { name: /下一步/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /步骤 2：再次打开选择框/ })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: /上一步/ }))
    expect(screen.getByLabelText('第一步图解')).toHaveClass('is-current')
    expect(mocks.generate).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: '通过' })).not.toBeInTheDocument()
  })
})
