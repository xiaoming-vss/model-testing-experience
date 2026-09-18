import { useAuthStore } from '@/features/auth/store/auth.store'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, type ReactNode } from 'react'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

export function QueryProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    // A different login must never inherit another user's connections or live query results.
    const unsubscribe = useAuthStore.subscribe((state, previous) => {
      if (state.token !== previous.token) {
        void queryClient.cancelQueries()
        queryClient.clear()
        useWorkbenchStore.getState().setActiveProjectId(undefined)
      }
    })
    const refreshPermissions = () => {
      void queryClient.invalidateQueries({ queryKey: ['projectAccess'] })
      void queryClient.invalidateQueries({ queryKey: ['projects'] })
    }
    window.addEventListener('project-permission-denied', refreshPermissions)
    return () => {
      unsubscribe()
      window.removeEventListener('project-permission-denied', refreshPermissions)
    }
  }, [])
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
