import type { ReactNode } from 'react'
import { PaneActiveContext } from './paneActivity'

export function PaneActivityProvider({ active, children }: { active: boolean; children: ReactNode }) {
  return <PaneActiveContext.Provider value={active}>{children}</PaneActiveContext.Provider>
}
