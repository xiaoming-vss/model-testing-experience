import { createContext, useContext } from 'react'
export const ProjectScope = createContext<string | undefined>(undefined)
export function useScopedProjectId() { return useContext(ProjectScope) }
