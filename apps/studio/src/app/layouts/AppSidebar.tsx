import { useThemeStore } from '@/shared/theme/theme.store'
import { useAuthStore } from '@/features/auth/store/auth.store'
import { Link, useLocation } from 'react-router-dom'
import { Layout } from 'antd'
import { MenuFoldOutlined, MenuUnfoldOutlined, FlagOutlined, FileOutlined, CheckSquareOutlined, BugOutlined, DatabaseOutlined } from '@ant-design/icons'
import { AppIcon, type AppIconName } from '@/shared/icons'
import { resolveTestingTab } from '@/features/testing/components/testingTab'
import { useSidebarStore } from './sidebar.store'
import '../styles/sidebar.css'

/* 折叠态的激活项使用强调色线条图标，并由样式保留模块名称和选中底色。
   SVG 经 <img> 引用,CSS 无法对其换色,故以独立变体资源切换;
   强调色变体按浅色主题绘制,暗色主题沿用原有激活处理。 */
const OUTLINE_ICONS: Partial<Record<AppIconName, typeof FlagOutlined>> = {
  navSprint: FlagOutlined, navRequirement: FileOutlined, testing: CheckSquareOutlined,
  navBug: BugOutlined, services: DatabaseOutlined,
}

const COLLAPSED_ACTIVE_ICONS: Partial<Record<AppIconName, AppIconName>> = {
  navSprint: 'navSprintActive',
  navRequirement: 'navRequirementActive',
  testing: 'testingActive',
  navBug: 'navBugActive',
  services: 'servicesActive',
}

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

  function navLink(to: string, label: string, icon: AppIconName, active: boolean) {
    const OutlineIcon = OUTLINE_ICONS[icon]
    const activeIcon = collapsed && active && resolvedTheme !== 'dark' ? COLLAPSED_ACTIVE_ICONS[icon] : undefined
    return <Link key={to} to={to} className={`sidebar-link${active ? ' is-active' : ''}`}
      aria-current={active ? 'page' : undefined} title={label}>
      {!collapsed && OutlineIcon ? <OutlineIcon className="sidebar-icon" aria-hidden="true" /> : <AppIcon name={activeIcon ?? icon} size={22} className={`sidebar-icon sidebar-icon-${icon}`} />}
      <span className="sidebar-link-label">{label}</span>
    </Link>
  }

  function section(label: string) {
    return <div className="sidebar-section" aria-hidden="true">{label}</div>
  }

  const displayName = user?.nickname || user?.name || ''
  const avatarChar = displayName.trim().charAt(0).toUpperCase()

  return (
    <Layout.Sider collapsed={collapsed} collapsedWidth={76} width={192} trigger={null}
      theme={resolvedTheme}
      className={`app-sider app-sidebar${collapsed ? ' app-sidebar-collapsed' : ''}`}>
      <div className="sidebar-content">
        <Link className="sidebar-brand" to={bugOnly ? '/testing?tab=bugs' : '/projects'} aria-label={bugOnly ? 'MTX Bug列表' : 'MTX 迭代'}>
          <span className="sidebar-logo-mark" aria-hidden="true">M</span><span className="sidebar-brand-name">MTX</span>
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
