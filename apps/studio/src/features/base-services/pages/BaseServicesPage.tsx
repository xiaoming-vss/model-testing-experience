import '@/shared/styles/surface-tokens.css'
import '../styles/index.css'
import { SharedServicesPanel } from '../components/SharedServicesPanel'
import { AppIcon } from '@/shared/icons'
import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'

type BaseServiceTab = 'llm' | 'gitlab' | 'skills' | 'mcp'

const tabOptions: Array<{
  key: BaseServiceTab
  label: string
  icon: ReactNode
}> = [
  {
    key: 'gitlab',
    label: 'GitLab',
    icon: <AppIcon name="gitlab" />,
  },
  {
    key: 'llm',
    label: 'LLM模型',
    icon: <AppIcon name="llm" />,
  },
  { key: 'mcp', label: 'MCP', icon: <AppIcon name="services" /> },
  { key: 'skills', label: 'Skill库', icon: <AppIcon name="skills" /> },
]

export function BaseServicesPage({ skillLibrary }: { skillLibrary: ReactNode }) {
  const [toolbarActions, setToolbarActions] = useState<HTMLDivElement | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const { activeProjectId } = useActiveProject()

  const activeTab = useMemo<BaseServiceTab>(() => {
    const tab = searchParams.get('tab')
    if (tab === 'zentao') return 'mcp'
    if (tab === 'llm' || tab === 'gitlab' || tab === 'skills' || tab === 'mcp') return tab
    return 'llm'
  }, [searchParams])

  function handleTabChange(nextTab: BaseServiceTab) {
    const nextSearchParams = new URLSearchParams(searchParams)
    nextSearchParams.set('tab', nextTab)
    setSearchParams(nextSearchParams, { replace: true })
  }

  return (
    <div className="workbench-page base-services-page tp-surface">
      <div className="base-services-navigation">
          <div className="base-services-tab-switcher" role="tablist" aria-label="基础服务模块切换">
            {tabOptions.map((option) => {
              const active = option.key === activeTab
              return (
                <button
                  key={option.key}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={`base-services-tab${active ? ' active' : ''}`}
                  onClick={() => handleTabChange(option.key)}
                >
                  <span className="base-services-tab-icon">{option.icon}</span>
                  <span>{option.label}</span>
                </button>
              )
            })}
          </div>
      </div>

      {activeTab === 'skills' ? skillLibrary : <section className="base-services-unified-panel tp-board tp-list-panel">
        <div className="tp-list-toolbar">
          <h1 className="tp-list-title">{tabOptions.find(option => option.key === activeTab)?.label}</h1>
          <div ref={setToolbarActions} />
        </div>
        <div className="base-services-panel-body base-services-panel-body-immersive">
          <SharedServicesPanel projectId={activeProjectId} provider={activeTab} toolbarActions={toolbarActions} />
        </div>
      </section>}
    </div>
  )
}
