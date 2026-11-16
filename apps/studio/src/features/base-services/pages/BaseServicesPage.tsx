import '@/shared/styles/surface-tokens.css'
import '../styles/index.css'
import { SharedServicesPanel } from '../components/SharedServicesPanel'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'
import { BASE_SERVICE_TABS, resolveBaseServiceTab } from '../baseServiceTabs'

export function BaseServicesPage({ skillLibrary }: { skillLibrary: ReactNode }) {
  const [toolbarActions, setToolbarActions] = useState<HTMLDivElement | null>(null)
  const [searchParams] = useSearchParams()
  const { activeProjectId } = useActiveProject()
  const activeTab = resolveBaseServiceTab(searchParams.get('tab'))

  return (
    <div className="workbench-page base-services-page tp-surface">
      <div className="base-services-motion-panel">
      {activeTab === 'skills' ? skillLibrary : <section className="base-services-unified-panel tp-board tp-list-panel">
        <div className="tp-list-toolbar">
          <h1 className="tp-list-title">{BASE_SERVICE_TABS.find(option => option.key === activeTab)?.label}</h1>
          <div ref={setToolbarActions} />
        </div>
        <div className="base-services-panel-body base-services-panel-body-immersive">
          <SharedServicesPanel projectId={activeProjectId} provider={activeTab} toolbarActions={toolbarActions} />
        </div>
      </section>}
      </div>
    </div>
  )
}
