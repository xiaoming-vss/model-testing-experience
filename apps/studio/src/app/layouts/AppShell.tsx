import { useEffect, useState } from 'react'
import { AssetLibraryPage } from '../pages/AssetLibraryPage'
import { RequirementDetailPage } from '../pages/RequirementDetailPage'
import { ThemeSelect } from '@/shared/components/ThemeSelect'
import { ActionButton } from '@/shared/components/ActionButton'
import { DownOutlined, LogoutOutlined, SettingOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Dropdown, Layout, Menu, Popover, Select, Spin, Tooltip } from 'antd'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ApiCollectionDetailPage } from '@/features/api-automation/pages/ApiCollectionDetailPage'
import { useCurrentUser } from '@/features/auth/hooks/useCurrentUser'
import { useLogout } from '@/features/auth/hooks/useLogout'
import { ChangePasswordPage } from '@/features/auth/pages/ChangePasswordPage'
import { LdapSettingsPage } from '@/features/admin/pages/LdapSettingsPage'
import { AccountManagementPage } from '@/features/admin/pages/AccountManagementPage'
import { ProfilePage } from '@/features/profile/pages/ProfilePage'
import { ProjectsPage } from '@/features/projects/pages/ProjectsPage'
import { SprintDetailPage } from '@/features/projects/pages/SprintDetailPage'
import { useActiveProject } from '@/domain/projects/hooks/useActiveProject'
import { useActiveSprint } from '@/domain/projects/hooks/useActiveSprint'
import { AiSkillLibraryPage } from '@/features/ai-testing/pages/AiSkillLibraryPage'
import { BaseServicesPage } from '@/features/base-services/pages/BaseServicesPage'
import { TestingPage } from '@/app/pages/TestingPage'
import { InterfaceDetailPage } from '@/features/interface-library/pages/InterfaceDetailPage'
import { TestOrderWorkspacePage } from '@/features/test-orders/pages/TestOrderWorkspacePage'
import { BugDetailPage } from '@/features/bugs/pages/BugDetailPage'
import { BugSubmitPage } from '@/features/bugs/pages/BugSubmitPage'
import { UiTestSuiteCasePage } from '@/features/ui-automation/pages/UiTestSuiteCasePage'
import { PerformanceRunDetailPage } from '@/features/performance/pages/PerformanceRunDetailPage'
import { PerformanceRunsPage } from '@/features/performance/pages/PerformanceRunsPage'
import { PerformanceSuiteDetailPage } from '@/features/performance/pages/PerformanceSuiteDetailPage'
import { AppNavigationBrand, AppSidebar } from './AppSidebar'
import { navigationIndex } from './navigation'
import { useNavigationTransition } from './useNavigationTransition'
import { useScopeTransition } from './useScopeTransition'
import { installTabMotion } from '@/shared/ui/tabMotion'
import { canNavigateAway } from '@/shared/utils/unsavedChanges'
import '@/shared/styles/tab-motion.css'
import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import { normalizeProjectId } from '@/utils/format'
import { isBugOnlyProject, useProjectAccess } from '@/domain/projects/hooks/useProjectAccess'
import { useBugScope } from '@/features/bugs/hooks/useBugScope'
import { ProjectRouteGuard } from '../router/guards/ProjectRouteGuard'

const { Header, Content } = Layout

export function AppShell() {
  const [projectSelectorOpen, setProjectSelectorOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const logout = useLogout()
  const { token, userQuery } = useCurrentUser()
  const currentUser = userQuery.data
  const mustChangePassword = Boolean(currentUser?.mustChangePassword ?? currentUser?.must_change_password)
  const isSuperAdmin = Boolean(currentUser?.isSuperAdmin ?? currentUser?.is_super_admin)
  const { activeProjectId, projects, projectsQuery, setActiveProjectId } = useActiveProject()
  const access = useProjectAccess(activeProjectId)
  const bugOnly = isBugOnlyProject(access.project)
  const contentRef = useNavigationTransition(
    navigationIndex(location.pathname, location.search, bugOnly),
    location.pathname,
  )
  const sprintScope = useActiveSprint(access.can('read'))
  const bugScope = useBugScope(activeProjectId, bugOnly)
  const { activeSprintId, sprintsQuery, selectSprint, sprintSelectorOptions } = bugOnly ? bugScope : sprintScope
  const prepareScopeTransition = useScopeTransition(contentRef, activeProjectId, activeSprintId)
  const showWorkbenchHeader = !['/profile', '/change-password', '/admin/users', '/admin/ldap'].some((path) => location.pathname.startsWith(path))

  const shellClassName = `app-shell app-shell-macos${location.pathname.startsWith('/base-services') ? ' app-shell-base-services' : ''}${location.pathname.startsWith('/requirements/') ? ' app-shell-requirement-detail' : ''}`

  useEffect(() => installTabMotion(document.body), [])

  useEffect(() => {
    const redirect = () => navigate('/change-password', { replace: true })
    window.addEventListener('password-change-required', redirect)
    return () => window.removeEventListener('password-change-required', redirect)
  }, [navigate])

  if (!token) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  if (mustChangePassword && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />
  }

  return (
    <Layout className={shellClassName}>
      <Layout>
        <Header className="app-header compact-header justify-end">
          <AppNavigationBrand bugOnly={bugOnly} />
          <div className="app-header-main min-w-0">
            {showWorkbenchHeader ? (
              <div className="project-header-bar project-header-bar-select-only flex w-auto items-center justify-start gap-4 max-[900px]:flex-col max-[900px]:items-start">
                <div className="project-selector-wrap">
                  <Select
                    className="project-select"
                    aria-label="当前项目"
                    popupMatchSelectWidth={false}
                    open={projectSelectorOpen}
                    onOpenChange={setProjectSelectorOpen}
                    popupRender={(menu) => <>
                      {menu}
                      {activeProjectId && access.can('read') && !bugOnly ? <Menu
                        selectable={false}
                        items={[
                          { type: 'divider' },
                          { key: 'members', icon: <UserOutlined />, label: '项目成员' },
                          { key: 'settings', icon: <SettingOutlined />, label: '项目设置', disabled: !access.can('manage') },
                        ]}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={({ key }) => {
                          if (key === 'settings' && !access.can('manage')) return
                          if (!canNavigateAway()) return
                          setProjectSelectorOpen(false)
                          const params = new URLSearchParams(location.pathname === '/projects' ? location.search : '')
                          params.set('projectPanel', key)
                          params.set('panelProjectId', activeProjectId)
                          navigate(`/projects?${params}`)
                        }}
                      /> : null}
                    </>}
                    loading={projectsQuery.isLoading}
                    value={activeProjectId}
                    placeholder="请选择项目"
                    suffixIcon={<DownOutlined />}
                    options={projects.map((project) => ({ label: project.name, value: normalizeProjectId(project) }))}
                    onChange={id => {
                      if (id === activeProjectId || !canNavigateAway()) return
                      prepareScopeTransition('project', activeProjectId, id, projects.map(normalizeProjectId))
                      setActiveProjectId(id)
                      if (location.pathname.startsWith('/requirements/')) navigate('/projects?board=requirements')
                    }}
                    variant="borderless"
                  />
                  {activeProjectId ? (
                    <>
                      <span className="project-scope-separator text-[var(--mac-glass-muted)]" aria-hidden="true">/</span>
                      <Select
                        className="project-select sprint-select"
                        popupMatchSelectWidth={false}
                        loading={sprintsQuery.isLoading}
                        value={activeSprintId ?? 'all'}
                        placeholder="全部迭代"
                        suffixIcon={<DownOutlined />}
                        options={sprintSelectorOptions}
                        onChange={id => {
                          if (id === (activeSprintId ?? 'all') || !canNavigateAway()) return
                          prepareScopeTransition('sprint', activeSprintId, id, sprintSelectorOptions.map(option => option.value))
                          selectSprint(id)
                          if (location.pathname.startsWith('/requirements/')) navigate('/projects?board=requirements')
                        }}
                        variant="borderless"
                      />
                    </>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
          <AppSidebar bugOnly={bugOnly} />
          <div className="app-header-actions flex shrink-0 items-center gap-1.5 max-[1200px]:ml-auto">
            <Popover trigger="click" placement="bottomRight" content={
              <div className="app-feedback-content max-w-[280px] text-[var(--app-shell-text)]">需求、想法和问题，请联系 <a href="mailto:limingjiang.x@gmail.com">limingjiang.x@gmail.com</a></div>
            }>
              <Button type="text" className="app-feedback-trigger text-xs whitespace-nowrap text-[var(--app-accent)]" aria-label="测试阶段反馈联系方式">测试阶段</Button>
            </Popover>
            {showWorkbenchHeader && !bugOnly ? <ActionButton type="primary" className="app-header-create-project action-btn-create" operation="create" onClick={() => { if (!canNavigateAway()) return; useWorkbenchStore.getState().openProjectModal(); navigate('/projects') }}>新建项目</ActionButton> : null}
            <ThemeSelect />
            <Dropdown
              menu={{
                items: [
                  ...(isSuperAdmin
                    ? [{ key: 'admin-users', icon: <TeamOutlined />, label: '账号管理' }, { key: 'admin-ldap', icon: <SettingOutlined />, label: 'LDAP 认证' }, { type: 'divider' as const }]
                    : []),
                  { key: 'profile', icon: <SettingOutlined />, label: '个人设置' },
                  { type: 'divider' },
                  {
                    key: 'logout',
                    icon: <LogoutOutlined />,
                    label: '退出登录',
                    danger: true,
                  },
                ],
                onClick: ({ key }) => {
                  if (['profile', 'admin-users', 'admin-ldap', 'logout'].includes(key) && !canNavigateAway()) return
                  if (key === 'profile') navigate('/profile')
                  if (key === 'admin-users') navigate('/admin/users')
                  if (key === 'admin-ldap') navigate('/admin/ldap')
                  if (key === 'logout') {
                    if (!logout.isPending) {
                      logout.mutate(undefined, {
                        onSuccess: () => navigate('/login', { replace: true }),
                      })
                    }
                  }
                },
              }}
              trigger={['click']}
            >
              <Tooltip title="当前用户">
                <Button type="text" shape="circle" icon={<UserOutlined />} />
              </Tooltip>
            </Dropdown>
          </div>
        </Header>
        <Content ref={contentRef} className="app-content">
          {projectsQuery.isPending || (projects.length > 0 && !activeProjectId) ? <Spin aria-label="项目加载中" /> : <ProjectRouteGuard>
          <Routes>
            <Route path="/" element={<Navigate to="/projects" replace />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:projectId/sprints/:sprintId" element={<SprintDetailPage />} />
            <Route path="/testing" element={<TestingPage />} />
            <Route path="/asset-library" element={<AssetLibraryPage />} />
            <Route path="/asset-library/interfaces/new" element={<InterfaceDetailPage />} />
            <Route path="/asset-library/interfaces/:interfaceId" element={<InterfaceDetailPage />} />
            <Route path="/test-cases" element={<Navigate to="/asset-library?tab=cases" replace />} />
            <Route path="/test-orders/:orderId" element={<TestOrderWorkspacePage />} />
            <Route path="/requirements/:requirementId" element={<RequirementDetailPage />} />
            <Route path="/bugs/new" element={<BugSubmitPage />} />
            <Route path="/bugs/:bugId" element={<BugDetailPage />} />
            <Route path="/ai-testing" element={<Navigate to="/projects?board=requirements" replace />} />
            <Route path="/ai-testing/tasks" element={<Navigate to="/projects?board=requirements" replace />} />
            <Route path="/ai-testing/code-risk-tasks/:taskId" element={<Navigate to="/projects?board=requirements" replace />} />
            <Route path="/ai-testing/skills" element={<Navigate to="/base-services?tab=skills" replace />} />
            <Route path="/base-services" element={<BaseServicesPage skillLibrary={<AiSkillLibraryPage embedded />} />} />
            <Route path="/api-automation" element={<Navigate to="/testing?tab=api" replace />} />
            <Route path="/api-automation/collections/:collectionId" element={<ApiCollectionDetailPage />} />
            <Route path="/ui-automation" element={<Navigate to="/testing?tab=ui" replace />} />
            <Route path="/ui-automation/suites/:suiteId" element={<UiTestSuiteCasePage />} />
            <Route path="/performance" element={<Navigate to="/testing?tab=perf" replace />} />
            <Route path="/performance/suites/:suiteId" element={<PerformanceSuiteDetailPage />} />
            <Route path="/performance/runs" element={<PerformanceRunsPage />} />
            <Route path="/performance/runs/:runId" element={<PerformanceRunDetailPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/change-password" element={<ChangePasswordPage />} />
            <Route path="/admin/ldap" element={<LdapSettingsPage />} />
            <Route path="/admin/users" element={<AccountManagementPage />} />
            <Route path="/projects/board=requirements" element={<Navigate to="/projects?board=requirements" replace />} />
            <Route path="/projects/board=sprints" element={<Navigate to="/projects?board=sprints" replace />} />
            <Route path="*" element={<Navigate to="/projects" replace />} />
          </Routes>
          </ProjectRouteGuard>}
        </Content>
      </Layout>
    </Layout>
  )
}
