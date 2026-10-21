import { MtxLogo } from '@/shared/components/MtxLogo/MtxLogo'
import { useThemeStore } from '@/shared/theme/theme.store'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { Link, useLocation } from 'react-router-dom'
import { Layout } from 'antd'
import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import { SidebarIcon, type SidebarIconName } from './SidebarIcon'
import { resolveTestingTab } from '@/features/testing/components/testingTab'
import { useSidebarStore } from './sidebar.store'
import '../styles/sidebar.css'

export function AppSidebar({ bugOnly = false }: { bugOnly?: boolean }) {
  const resolvedTheme = useThemeStore((state) => state.resolvedTheme)
  const collapsed = useSidebarStore((state) => state.collapsed)
  const toggleCollapsed = useSidebarStore((state) => state.toggleCollapsed)
  const user = useAuthStore((state) => state.user)
  const { pathname, search } = useLocation()
  const inRequirements = pathname.startsWith('/requirements')
  const inProjects = pathname.startsWith('/projects') || inRequirements
  const projectBoard = inRequirements || new URLSearchParams(search).get('board') === 'requirements' ? 'requirements' : 'sprints'
  const testingTab = pathname.startsWith('/test-orders') ? 'orders'
    : pathname.startsWith('/bugs') ? 'bugs'
    : pathname.startsWith('/api-automation') ? 'api'
      : pathname.startsWith('/ui-automation') ? 'ui'
        : pathname.startsWith('/test-cases') ? 'library' : pathname === '/testing'
          ? resolveTestingTab(new URLSearchParams(search).get('tab')) : null
  function testingHref(tab: string) {
    const params = new URLSearchParams(pathname === '/testing' ? search : '')
    params.set('tab', tab)
    return `/testing?${params}`
  }

  function navLink(to: string, label: string, icon: SidebarIconName, active: boolean) {
    return <Link key={to} to={to} className={`sidebar-link${active ? ' is-active' : ''}`}
      aria-current={active ? 'page' : undefined} title={label}>
      <SidebarIcon name={icon} />
      <span className="sidebar-link-label">{label}</span>
    </Link>
  }

  function section(label: string) {
    return <div className="sidebar-section" aria-hidden="true">{label}</div>
  }

  const displayName = user?.nickname || user?.name || ''
  const avatarChar = displayName.trim().charAt(0).toUpperCase()

  return (
    <Layout.Sider collapsed={collapsed} collapsedWidth={76} width={176} trigger={null}
      theme={resolvedTheme}
      className={`app-sider app-sidebar${collapsed ? ' app-sidebar-collapsed' : ''}`}>
      <div className="sidebar-content">
        <Link className="sidebar-brand" to={bugOnly ? '/testing?tab=bugs' : '/projects'} aria-label={bugOnly ? 'MTX Bug列表' : 'MTX 迭代'}>
          <MtxLogo size={40} /><span className="sidebar-brand-name">MTX</span>
        </Link>
        <nav className="sidebar-navigation" aria-label="主导航">
          {bugOnly ? navLink('/testing?tab=bugs', 'Bug列表', 'navBug', testingTab === 'bugs') : <>
            {section('工作管理')}
            {(['sprints', 'requirements'] as const).map((board) => {
              const params = new URLSearchParams(inProjects ? search : '')
              params.delete('projectPanel')
              params.delete('panelProjectId')
              params.set('board', board)
              return navLink(`/projects?${params}`, board === 'sprints' ? '迭代' : '需求',
                board === 'sprints' ? 'navSprint' : 'navRequirement', inProjects && projectBoard === board)
            })}
            {section('质量管理')}
            {navLink(testingHref(testingTab && testingTab !== 'bugs' ? testingTab : 'orders'), '测试', 'testing', Boolean(testingTab && testingTab !== 'bugs'))}
            {navLink(testingHref('bugs'), 'Bug列表', 'navBug', testingTab === 'bugs')}
            {section('集成')}
            {navLink('/base-services', '基础服务', 'services', pathname.startsWith('/base-services'))}
          </>}
        </nav>
        <div className="sidebar-foot">
          {displayName ? (
            <Link to="/profile" className="sidebar-user" title="个人设置">
              <span className="sidebar-user-avatar" aria-hidden="true">{avatarChar}</span>
              <span className="sidebar-user-name">{displayName}</span>
            </Link>
          ) : null}
          <button type="button" className="sidebar-collapse" aria-label={collapsed ? '展开侧边栏' : '折叠侧边栏'}
            aria-expanded={!collapsed} onClick={toggleCollapsed}>
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </button>
        </div>
      </div>
    </Layout.Sider>
  )
}
