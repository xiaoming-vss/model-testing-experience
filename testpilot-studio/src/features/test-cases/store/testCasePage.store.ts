import { create } from 'zustand'

type FunctionalFilterSelection = {
  sprintId?: string | null
  requirementId?: string | null
}

type TestCasePageState = {
  functionalSelectionsByProject: Record<string, FunctionalFilterSelection>
  updateFunctionalSelection: (projectId: string, patch: Partial<FunctionalFilterSelection>) => void
}

export const useTestCasePageStore = create<TestCasePageState>((set) => ({
  functionalSelectionsByProject: {},
  updateFunctionalSelection: (projectId, patch) =>
    set((state) => ({
      functionalSelectionsByProject: {
        ...state.functionalSelectionsByProject,
        [projectId]: {
          ...state.functionalSelectionsByProject[projectId],
          ...patch,
        },
      },
    })),
}))
