import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { TestThemeProvider } from '@/test/TestThemeProvider'
import type { RequirementRepositoryProfileWorkspace } from '../hooks/useRequirementRepositoryProfileWorkspace'
import { RequirementRepositoryProfileInspector } from './RequirementRepositoryProfileInspector'

vi.mock('@/domain/projects/components/ProjectActionButton', () => ({
  ProjectActionButton: ({ action, operation, ...props }: React.ComponentProps<'button'> & { action: string; operation?: string }) => {
    void action
    void operation
    return <button {...props} />
  },
}))

afterEach(cleanup)

function workspace(isCurrent: boolean) {
  const adopt = vi.fn()
  return {
    value: {
      profileCandidateMode: true,
      materialCandidateMode: true,
      currentMaterialAvailable: true,
      selectedCandidateId: 'profile-a',
      selectedProfileView: { candidateId: 'profile-a', label: '候选 profile-', resultYaml: '{}' },
      latestProfileView: { candidateId: 'profile-a' },
      candidateViews: [{ candidateId: 'profile-a', label: '候选 profile-' }],
      candidateSummaries: [{ candidateId: 'profile-a', disposition: 'available' }],
      selectedCandidate: { candidateId: 'profile-a', disposition: 'available', isCurrent },
      currentProfile: { candidateId: isCurrent ? 'profile-a' : null, currentToken: 'token' },
      currentProfileLoading: false,
      candidatePage: 1, candidatePageSize: 20, candidateTotal: 1,
      setCandidatePage: vi.fn(), setSelectedCandidateId: vi.fn(),
      materialVersions: [], bindings: [], bindingsLoading: false,
      candidateViewsLoading: false, candidateViewsError: null, busy: false,
      adopt: { mutate: adopt, isPending: false },
      dispose: { mutate: vi.fn(), isPending: false },
      clearCurrent: { mutate: vi.fn(), isPending: false },
      personalLlm: { dialog: null }, personalGitlab: { dialog: null },
    } as unknown as RequirementRepositoryProfileWorkspace,
    adopt,
  }
}

it('显示候选并显式采用，未采用时不标成当前', () => {
  const state = workspace(false)
  render(<TestThemeProvider><RequirementRepositoryProfileInspector workspace={state.value} /></TestThemeProvider>)
  expect(screen.getByText('尚未采用')).toBeInTheDocument()
  expect(screen.getByRole('group', { name: '选择仓库画像候选' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '采用此画像' }))
  expect(state.adopt).toHaveBeenCalledOnce()
})

it('已采用画像单独显示，当前候选不能重复采用', () => {
  const state = workspace(true)
  render(<TestThemeProvider><RequirementRepositoryProfileInspector workspace={state.value} /></TestThemeProvider>)
  expect(screen.getByText('已采用')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '查看当前画像' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '采用此画像' })).not.toBeInTheDocument()
})
