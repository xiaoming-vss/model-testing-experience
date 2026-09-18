import { create } from 'zustand'

type CaseLibraryFilterSelection = {
  requirementId?: string | null
  suiteId?: string | null
  priority?: string | null
}

type CaseLibraryState = {
  selectionsByProject: Record<string, CaseLibraryFilterSelection>
  updateSelection: (projectId: string, patch: Partial<CaseLibraryFilterSelection>) => void
}

export const useCaseLibraryStore = create<CaseLibraryState>((set) => ({
  selectionsByProject: {},
  updateSelection: (projectId, patch) =>
    set((state) => ({
      selectionsByProject: {
        ...state.selectionsByProject,
        [projectId]: {
          ...state.selectionsByProject[projectId],
          ...patch,
        },
      },
    })),
}))
