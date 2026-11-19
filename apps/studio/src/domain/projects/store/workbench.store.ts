import { create } from 'zustand'
import type { Project } from '@/services/api'

type WorkbenchState = {
  activeProjectId?: string
  activeSprintId?: string | null
  activeSprintProjectId?: string
  projectModalOpen: boolean
  editingProject: Project | null
  setActiveProjectId: (projectId?: string) => void
  setActiveSprintId: (sprintId?: string | null) => void
  openProjectModal: (project?: Project) => void
  closeProjectModal: () => void
}

export const useWorkbenchStore = create<WorkbenchState>((set) => ({
  activeProjectId: undefined,
  activeSprintId: undefined,
  activeSprintProjectId: undefined,
  projectModalOpen: false,
  editingProject: null,
  setActiveProjectId: (projectId) =>
    set({ activeProjectId: projectId, activeSprintId: undefined, activeSprintProjectId: undefined }),
  setActiveSprintId: (sprintId) =>
    set((state) => ({ activeSprintId: sprintId, activeSprintProjectId: state.activeProjectId })),
  openProjectModal: (project) => set({ projectModalOpen: true, editingProject: project ?? null }),
  closeProjectModal: () => set({ projectModalOpen: false, editingProject: null }),
}))
