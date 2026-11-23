import { create } from 'zustand'
import type { Project } from '@/services/api'

type WorkbenchState = {
  activeProjectId?: string
  projectModalOpen: boolean
  editingProject: Project | null
  setActiveProjectId: (projectId?: string) => void
  openProjectModal: (project?: Project) => void
  closeProjectModal: () => void
}

export const useWorkbenchStore = create<WorkbenchState>((set) => ({
  activeProjectId: undefined,
  projectModalOpen: false,
  editingProject: null,
  setActiveProjectId: (projectId) => set({ activeProjectId: projectId }),
  openProjectModal: (project) => set({ projectModalOpen: true, editingProject: project ?? null }),
  closeProjectModal: () => set({ projectModalOpen: false, editingProject: null }),
}))
