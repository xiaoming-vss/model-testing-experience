import { AppIcon } from '@/shared/icons'
import { Alert } from 'antd'
import { useMemo } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { AiSkillLibraryPage } from './AiSkillLibraryPage'
import { UnifiedAiTestingPage } from './UnifiedAiTestingPage'
import '@/features/ai-testing/styles/index.css'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'
import { getErrorMessage } from '@/utils/format'

export function AiTestingOverviewPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { projectsQuery } = useActiveProject()
  const legacyTab = searchParams.get('tab')
  const activeEntryKey = useMemo<'skills' | 'tasks'>(() => {
    const tab = searchParams.get('tab')
    if (tab === 'skills') return 'skills'
    return 'tasks'
  }, [searchParams])

  if (legacyTab === 'api' || legacyTab === 'ui' || legacyTab === 'functional') {
    return <Navigate to="/ai-testing?tab=tasks" replace />
  }

  const overviewItems = [
    { key: 'tasks', title: '任务', icon: <AppIcon name="tasks" /> },
    {
      key: 'skills',
      title: 'Skill库',
      icon: <AppIcon name="skills" />,
    },
  ] as const

  return (
    <div className="workbench-page ai-testing-page ai-testing-overview-page">
      {projectsQuery.error ? (
        <Alert showIcon type="error" title={getErrorMessage(projectsQuery.error)} />
      ) : null}

      <section className="workbench-project-toolbar base-services-toolbar ai-testing-overview-toolbar">
        <div className="ai-testing-overview-switcher-row">
          <div className="ai-testing-overview-tab-switcher" role="tablist" aria-label="测试设计模块切换">
            {overviewItems.map((item) => {
              const active = item.key === activeEntryKey

              return (
                <button
                  key={item.key}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={`ai-testing-overview-tab${active ? ' active' : ''}`}
                  onClick={() => {
                    const nextSearchParams = new URLSearchParams(searchParams)
                    nextSearchParams.set('tab', item.key)
                    setSearchParams(nextSearchParams, { replace: true })
                  }}
                >
                  <span className="ai-testing-overview-tab-icon">{item.icon}</span>
                  <span>{item.title}</span>
                </button>
              )
            })}
          </div>
        </div>
      </section>

      {activeEntryKey === 'tasks' ? <UnifiedAiTestingPage embedded /> : <AiSkillLibraryPage embedded />}
    </div>
  )
}
