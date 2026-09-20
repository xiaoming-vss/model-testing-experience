import { AppIcon } from '@/shared/icons'
import { ActionButton } from '@/shared/components/ActionButton'
import { DownOutlined, LogoutOutlined, MoonOutlined, SettingOutlined, SunOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Dropdown, Layout, Menu, Select, Tooltip } from 'antd'
import type { MenuProps } from 'antd'
import { useMemo } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ApiCollectionDetailPage } from '@/features/api-automation/pages/ApiCollectionDetailPage'
import { useCurrentUser } from '@/features/auth/hooks/useCurrentUser'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { ProfilePage } from '@/features/profile/pages/ProfilePage'
import { ProjectsPage } from '@/features/projects/pages/ProjectsPage'
import { SprintDetailPage } from '@/features/projects/pages/SprintDetailPage'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { UnifiedAiTestingPage } from '@/features/ai-testing/pages/UnifiedAiTestingPage'
import { AiSkillLibraryPage } from '@/features/ai-testing/pages/AiSkillLibraryPage'
import { AiTestingOverviewPage } from '@/features/ai-testing/pages/AiTestingOverviewPage'
import { ApiCaseGenerateTaskDetailPage } from '@/features/ai-testing/pages/ApiCaseGenerateTaskDetailPage'
import { FunctionalCaseGenerateTaskDetailPage } from '@/features/ai-testing/pages/FunctionalCaseGenerateTaskDetailPage'
import { FunctionalCaseRelationsPage } from '@/features/ai-testing/pages/FunctionalCaseRelationsPage'
import { UiCaseGenerateTaskDetailPage } from '@/features/ai-testing/pages/UiCaseGenerateTaskDetailPage'
import { RequirementAnalysisTaskDetailPage } from '@/features/ai-testing/pages/RequirementAnalysisTaskDetailPage'
import { CodeRiskTaskDetailPage } from '@/features/ai-testing/pages/CodeRiskTaskDetailPage'
import { BaseServicesPage } from '@/features/base-services/pages/BaseServicesPage'
import { TestingPage } from '@/features/testing/pages/TestingPage'
import { TestOrderWorkspacePage } from '@/features/test-orders/pages/TestOrderWorkspacePage'
import { UiTestSuiteCasePage } from '@/features/ui-automation/pages/UiTestSuiteCasePage'
import { MtxLogo } from '@/shared/components/MtxLogo/MtxLogo'
import { useThemeStore } from '@/shared/store/theme.store'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { normalizeProjectId } from '@/utils/format'

const { Header, Sider, Content } = Layout

export function AppShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const logout = useAuthStore((state) => state.logout)
  const themeMode = useThemeStore((state) => state.mode)
  const toggleThemeMode = useThemeStore((state) => state.toggleMode)
  const { token } = useCurrentUser()
  const { activeProjectId, projects, projectsQuery, setActiveProjectId } = useActiveProject()
  const { activeSprintId, sprintsQuery, selectSprint, sprintSelectorOptions } = useActiveSprint()
  const showWorkbenchHeader = !location.pathname.startsWith('/profile')

  const selectedKey = useMemo(() => {
    if (location.pathname.startsWith('/base-services')) return '/base-services'
    if (location.pathname.startsWith('/ai-testing')) return '/ai-testing'
    if (location.pathname.startsWith('/test-cases')) return '/testing'
    if (location.pathname.startsWith('/test-orders')) return '/testing'
    if (location.pathname.startsWith('/testing')) return '/testing'
    if (location.pathname.startsWith('/api-automation')) return '/testing'
    if (location.pathname.startsWith('/ui-automation')) return '/testing'
    return '/projects'
  }, [location.pathname])

  const shellClassName = `app-shell app-shell-macos${location.pathname.startsWith('/base-services') ? ' app-shell-base-services' : ''}`

  const items: MenuProps['items'] = [
    { key: '/projects', icon: <AppIcon name="projects" size={20} />, label: '项目总览' },
    { key: '/testing', icon: <AppIcon name="testing" size={20} />, label: '测试' },
    { key: '/ai-testing', icon: <AppIcon name="testDesign" size={20} />, label: '测试设计' },
    { key: '/base-services', icon: <AppIcon name="services" size={20} />, label: '基础服务' },
  ]

  if (!token) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return (
    <Layout className={shellClassName}>
      <Sider
        width={76}
        collapsedWidth={76}
        trigger={null}
        theme="light"
        className="app-sider"
      >
        <div className="brand-row">
          <button className="brand" type="button" onClick={() => navigate('/projects')}>
            <MtxLogo size={36} className="brand-logo" />
            <span className="brand-text">MTX</span>
          </button>
        </div>
        <Menu
          mode="inline"
          inlineCollapsed={false}
          selectedKeys={[selectedKey]}
          items={items}
          onClick={({ key }) => navigate(String(key))}
        />
      </Sider>
      <Layout>
        <Header className="app-header compact-header">
          <div className="app-header-main">
            {showWorkbenchHeader ? (
              <div className="project-header-bar project-header-bar-select-only">
                <div className="project-selector-wrap">
                  <span className="project-selector-label">当前项目</span>
                  <span className="project-separator">/</span>
                  <Select
                    className="project-select"
                    loading={projectsQuery.isLoading}
                    value={activeProjectId}
                    placeholder="请选择项目"
                    suffixIcon={<DownOutlined />}
                    options={projects.map((project) => ({ label: project.name, value: normalizeProjectId(project) }))}
                    onChange={setActiveProjectId}
                    variant="borderless"
                  />
                  {activeProjectId ? (
                    <>
                      <span className="project-selector-divider" />
                      <span className="project-selector-label">当前迭代</span>
                      <span className="project-separator">/</span>
                      <Select
                        className="project-select sprint-select"
                        loading={sprintsQuery.isLoading}
                        value={activeSprintId ?? 'all'}
                        placeholder="全部迭代"
                        suffixIcon={<DownOutlined />}
                        options={sprintSelectorOptions}
                        onChange={selectSprint}
                        variant="borderless"
                      />
                    </>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
          <div className="app-header-feedback" role="note" aria-label="测试阶段反馈联系方式">
            <span className="app-header-feedback-badge">测试阶段</span>
            <span>需求、想法和问题，请联系 <a href="mailto:limingjiang.x@gmail.com">limingjiang.x@gmail.com</a></span>
          </div>
          <div className="app-header-actions">
            {showWorkbenchHeader ? <ActionButton type="primary" className="app-header-create-project action-btn-create" operation="create" onClick={() => { useWorkbenchStore.getState().openProjectModal(); navigate('/projects') }}>新建项目</ActionButton> : null}
            <Tooltip title={themeMode === 'dark' ? '切换浅色模式' : '切换黑夜模式'}>
              <Button
                type="text"
                shape="circle"
                icon={themeMode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
                onClick={toggleThemeMode}
              />
            </Tooltip>
            <Dropdown
              menu={{
                items: [
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
                  if (key === 'profile') navigate('/profile')
                  if (key === 'logout') {
                    logout()
                    navigate('/login', { replace: true })
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
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<Navigate to="/projects" replace />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:projectId/sprints/:sprintId" element={<SprintDetailPage />} />
            <Route path="/testing" element={<TestingPage />} />
            <Route path="/test-cases" element={<Navigate to="/testing?tab=library" replace />} />
            <Route path="/test-orders/:orderId" element={<TestOrderWorkspacePage />} />
            <Route path="/ai-testing" element={<AiTestingOverviewPage />} />
            <Route path="/ai-testing/skills" element={<AiSkillLibraryPage />} />
            <Route path="/ai-testing/tasks" element={<UnifiedAiTestingPage />} />
            <Route path="/ai-testing/tasks/:taskId" element={<ApiCaseGenerateTaskDetailPage />} />
            <Route path="/ai-testing/function-tasks/:taskId" element={<FunctionalCaseGenerateTaskDetailPage />} />
            <Route path="/ai-testing/function-tasks/:taskId/runs/:runId/graph" element={<FunctionalCaseRelationsPage />} />
            <Route path="/ai-testing/ui-tasks/:taskId" element={<UiCaseGenerateTaskDetailPage />} />
            <Route path="/ai-testing/requirement-analysis-tasks/:taskId" element={<RequirementAnalysisTaskDetailPage />} />
            <Route path="/ai-testing/code-risk-tasks/:taskId" element={<CodeRiskTaskDetailPage />} />
            <Route path="/base-services" element={<BaseServicesPage />} />
            <Route path="/api-automation" element={<Navigate to="/testing?tab=api" replace />} />
            <Route path="/api-automation/collections/:collectionId" element={<ApiCollectionDetailPage />} />
            <Route path="/ui-automation" element={<Navigate to="/testing?tab=ui" replace />} />
            <Route path="/ui-automation/suites/:suiteId" element={<UiTestSuiteCasePage />} />
            <Route path="/profile" element={<ProfilePage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}

