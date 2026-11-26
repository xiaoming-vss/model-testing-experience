import { lazy, useEffect, useState } from 'react'
import { ThemeSelect } from '@/shared/components/ThemeSelect'
import { ActionButton } from '@/shared/components/ActionButton'
import { DownOutlined, LogoutOutlined, SettingOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Dropdown, Layout, Menu, Popover, Select, Spin, Tooltip } from 'antd'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useCurrentUser } from '@/features/auth/hooks/useCurrentUser'
import { useLogout } from '@/features/auth/hooks/useLogout'
import { useActiveProject } from '@/domain/projects/hooks/useActiveProject'
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
import { ProjectRouteGuard } from '../router/guards/ProjectRouteGuard'
import { RouteSuspense } from '../router/RouteSuspense'

const AssetLibraryPage = lazy(() => import('../pages/AssetLibraryPage').then(({ AssetLibraryPage }) => ({ default: AssetLibraryPage })))
const RequirementDetailPage = lazy(() => import('../pages/RequirementDetailPage').then(({ RequirementDetailPage }) => ({ default: RequirementDetailPage })))
const ApiCollectionDetailPage = lazy(() => import('@/features/api-automation/pages/ApiCollectionDetailPage').then(({ ApiCollectionDetailPage }) => ({ default: ApiCollectionDetailPage })))
const ChangePasswordPage = lazy(() => import('@/features/auth/pages/ChangePasswordPage').then(({ ChangePasswordPage }) => ({ default: ChangePasswordPage })))
const LdapSettingsPage = lazy(() => import('@/features/admin/pages/LdapSettingsPage').then(({ LdapSettingsPage }) => ({ default: LdapSettingsPage })))
const AccountManagementPage = lazy(() => import('@/features/admin/pages/AccountManagementPage').then(({ AccountManagementPage }) => ({ default: AccountManagementPage })))
const ProfilePage = lazy(() => import('@/features/profile/pages/ProfilePage').then(({ ProfilePage }) => ({ default: ProfilePage })))
const ProjectsPage = lazy(() => import('@/features/projects/pages/ProjectsPage').then(({ ProjectsPage }) => ({ default: ProjectsPage })))
const SprintDetailPage = lazy(() => import('@/features/projects/pages/SprintDetailPage').then(({ SprintDetailPage }) => ({ default: SprintDetailPage })))
const AiSkillLibraryPage = lazy(() => import('@/features/ai-testing/pages/AiSkillLibraryPage').then(({ AiSkillLibraryPage }) => ({ default: AiSkillLibraryPage })))
const BaseServicesPage = lazy(() => import('@/features/base-services/pages/BaseServicesPage').then(({ BaseServicesPage }) => ({ default: BaseServicesPage })))
const TestingPage = lazy(() => import('../pages/TestingPage').then(({ TestingPage }) => ({ default: TestingPage })))
const InterfaceDetailPage = lazy(() => import('@/features/interface-library/pages/InterfaceDetailPage').then(({ InterfaceDetailPage }) => ({ default: InterfaceDetailPage })))
const TestOrderWorkspacePage = lazy(() => import('@/features/test-orders/pages/TestOrderWorkspacePage').then(({ TestOrderWorkspacePage }) => ({ default: TestOrderWorkspacePage })))
const BugDetailPage = lazy(() => import('@/features/bugs/pages/BugDetailPage').then(({ BugDetailPage }) => ({ default: BugDetailPage })))
const BugSubmitPage = lazy(() => import('@/features/bugs/pages/BugSubmitPage').then(({ BugSubmitPage }) => ({ default: BugSubmitPage })))
const UiTestSuiteCasePage = lazy(() => import('@/features/ui-automation/pages/UiTestSuiteCasePage').then(({ UiTestSuiteCasePage }) => ({ default: UiTestSuiteCasePage })))
const PerformanceRunDetailPage = lazy(() => import('@/features/performance/pages/PerformanceRunDetailPage').then(({ PerformanceRunDetailPage }) => ({ default: PerformanceRunDetailPage })))
const PerformanceCaseRunDetailPage = lazy(() => import('@/features/performance/pages/PerformanceCaseRunDetailPage').then(({ PerformanceCaseRunDetailPage }) => ({ default: PerformanceCaseRunDetailPage })))
const PerformanceRunsPage = lazy(() => import('@/features/performance/pages/PerformanceRunsPage').then(({ PerformanceRunsPage }) => ({ default: PerformanceRunsPage })))
const PerformanceSuiteDetailPage = lazy(() => import('@/features/performance/pages/PerformanceSuiteDetailPage').then(({ PerformanceSuiteDetailPage }) => ({ default: PerformanceSuiteDetailPage })))

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
  const prepareScopeTransition = useScopeTransition(contentRef, activeProjectId)
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
                      prepareScopeTransition(activeProjectId, id, projects.map(normalizeProjectId))
                      setActiveProjectId(id)
                      if (location.pathname.startsWith('/requirements/')) navigate('/projects?board=requirements')
                    }}
                    variant="borderless"
                  />
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
          <RouteSuspense>
          <Routes>
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
            <Route path="/ai-testing/skills" element={<Navigate to="/base-services?tab=skills" replace />} />
            <Route path="/base-services" element={<BaseServicesPage skillLibrary={<AiSkillLibraryPage embedded />} />} />
            <Route path="/api-automation/collections/:collectionId" element={<ApiCollectionDetailPage />} />
            <Route path="/ui-automation/suites/:suiteId" element={<UiTestSuiteCasePage />} />
            <Route path="/performance/suites/:suiteId" element={<PerformanceSuiteDetailPage />} />
            <Route path="/performance/runs" element={<PerformanceRunsPage />} />
            <Route path="/performance/runs/:runId" element={<PerformanceRunDetailPage />} />
            <Route path="/performance/case-runs/:runId" element={<PerformanceCaseRunDetailPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/change-password" element={<ChangePasswordPage />} />
            <Route path="/admin/ldap" element={<LdapSettingsPage />} />
            <Route path="/admin/users" element={<AccountManagementPage />} />
            <Route path="*" element={<Navigate to="/projects" replace />} />
          </Routes>
          </RouteSuspense>
          </ProjectRouteGuard>}
        </Content>
      </Layout>
    </Layout>
  )
}
