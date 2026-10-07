import { useThemeStore } from '@/shared/theme/theme.store'
import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { DownOutlined, MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import { Layout } from 'antd'
import { AppIcon, type AppIconName } from '@/shared/icons'
import { MtxLogo } from '@/shared/components/MtxLogo/MtxLogo'
import { resolveTestingTab } from '@/features/testing/components/testingTab'
import '../styles/sidebar.css'

const testingLinks: Array<{ key: string; label: string; icon: AppIconName }> = [
  { key: 'orders', label: '测试单', icon: 'tasks' },
  { key: 'bugs', label: 'Bug列表', icon: 'bug' },
  { key: 'api', label: 'API测试', icon: 'api' },
  { key: 'ui', label: 'UI测试', icon: 'ui' },
  { key: 'library', label: '用例库', icon: 'caseLibrary' },
]

const designLinks: Array<{ key: string; label: string; icon: AppIconName; path: string }> = [
  { key: 'analysis', label: '需求分析', icon: 'analysis', path: '/ai-testing/requirement-analysis-tasks/' },
  { key: 'functional', label: '功能测试', icon: 'functional', path: '/ai-testing/function-tasks/' },
  { key: 'api', label: 'API测试', icon: 'api', path: '/ai-testing/tasks/' },
  { key: 'ui', label: 'UI测试', icon: 'ui', path: '/ai-testing/ui-tasks/' },
  { key: 'codeRisk', label: '代码风险分析', icon: 'testDesign', path: '/ai-testing/code-risk-tasks/' },
]

export function AppSidebar({ designCounts = {}, bugOnly = false }: { designCounts?: Record<string, number>; bugOnly?: boolean }) {
  const resolvedTheme = useThemeStore((state) => state.resolvedTheme)
  const { pathname, search } = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const route = pathname + search
  const [navigation, setNavigation] = useState<{
    route: string
    project?: boolean
    testing?: boolean
    design?: boolean
  }>({ route })
  // Manual toggles belong to the current visit, not to a previously visited URL.
  if (navigation.route !== route) setNavigation({ route })
  const expanded: typeof navigation = navigation.route === route ? navigation : { route }
  const inProjects = pathname.startsWith('/projects')
  const projectBoard = new URLSearchParams(search).get('board') === 'requirements' ? 'requirements' : 'sprints'
  const projectOpen = !collapsed && (expanded.project ?? inProjects)
  const testingTab = pathname.startsWith('/test-orders') ? 'orders'
    : pathname.startsWith('/bugs') ? 'bugs'
    : pathname.startsWith('/api-automation') ? 'api'
      : pathname.startsWith('/ui-automation') ? 'ui'
        : pathname === '/testing' || pathname.startsWith('/test-cases')
          ? resolveTestingTab(new URLSearchParams(search).get('tab')) : null
  const testingOpen = !collapsed && (expanded.testing ?? Boolean(testingTab))

  const inDesign = pathname.startsWith('/ai-testing')
  const designKind = designLinks.find((item) => pathname.startsWith(item.path))?.key
    ?? designLinks.find((item) => item.key === new URLSearchParams(search).get('kind'))?.key ?? 'analysis'
  const designOpen = !collapsed && (expanded.design ?? inDesign)

  function navLink(to: string, label: string, icon: AppIconName, active: boolean, count?: number) {
    return <Link key={to} to={to} className={`sidebar-link${active ? ' is-active' : ''}`}
      aria-current={active ? 'page' : undefined} title={collapsed ? label : undefined}>
      <AppIcon name={icon} size={18} /><span>{label}</span>{count !== undefined && <span className="sidebar-count">{count}</span>}
    </Link>
  }

  return (
    <Layout.Sider width={208} collapsedWidth={76} collapsed={collapsed} trigger={null}
      theme={resolvedTheme} className={`app-sider app-sidebar${collapsed ? ' is-collapsed' : ''}`}>
      <div className="sidebar-content">
        <Link className="sidebar-brand" to={bugOnly ? '/testing?tab=bugs' : '/projects'} aria-label={bugOnly ? 'MTX Bug列表' : 'MTX 项目总览'}>
          <MtxLogo size={36} /><span>MTX</span>
        </Link>
        <nav className="sidebar-navigation" aria-label="主导航">
          {bugOnly ? navLink('/testing?tab=bugs', 'Bug列表', 'bug', testingTab === 'bugs') : <>
          <button type="button" className={`sidebar-link sidebar-group${inProjects ? ' is-current-group' : ''}`}
            aria-expanded={projectOpen} aria-controls="sidebar-project-links"
            onClick={() => { setCollapsed(false); setNavigation({ ...expanded, route, project: !projectOpen }) }}>
            <AppIcon name="projects" size={18} /><span>项目总览</span>
            <DownOutlined aria-hidden="true" className={`sidebar-chevron${projectOpen ? ' is-open' : ''}`} />
          </button>
          <div id="sidebar-project-links" className="sidebar-children" hidden={!projectOpen}>
            {(['sprints', 'requirements'] as const).map((board) => {
              const params = new URLSearchParams(inProjects ? search : '')
              params.set('board', board)
              return navLink(`/projects?${params}`, board === 'sprints' ? '迭代' : '需求',
                board === 'sprints' ? 'sprint' : 'requirement', inProjects && projectBoard === board)
            })}
          </div>
          <button type="button" className={`sidebar-link sidebar-group${inDesign ? ' is-current-group' : ''}`}
            aria-expanded={designOpen} aria-controls="sidebar-design-links"
            onClick={() => { setCollapsed(false); setNavigation({ ...expanded, route, design: !designOpen }) }}>
            <AppIcon name="testDesign" size={18} /><span>测试设计</span>
            <DownOutlined aria-hidden="true" className={`sidebar-chevron${designOpen ? ' is-open' : ''}`} />
          </button>
          <div id="sidebar-design-links" className="sidebar-children" hidden={!designOpen}>
            {designLinks.map(({ key, label, icon }) => navLink(`/ai-testing?kind=${key}`, label, icon, inDesign && designKind === key, designCounts[key]))}
          </div>
          <button type="button" className={`sidebar-link sidebar-group${testingTab ? ' is-current-group' : ''}`}
            aria-expanded={testingOpen} aria-controls="sidebar-testing-links" title={collapsed ? '展开测试导航' : undefined}
            onClick={() => { setCollapsed(false); setNavigation({ ...expanded, route, testing: !testingOpen }) }}>
            <AppIcon name="testing" size={18} /><span>测试</span>
            <DownOutlined aria-hidden="true" className={`sidebar-chevron${testingOpen ? ' is-open' : ''}`} />
          </button>
          <div id="sidebar-testing-links" className="sidebar-children" hidden={!testingOpen}>
            {testingLinks.map(({ key, label, icon }) => {
              const params = new URLSearchParams(pathname === '/testing' ? search : '')
              params.set('tab', key)
              return navLink(`/testing?${params}`, label, icon, testingTab === key)
            })}
          </div>
          {navLink('/base-services', '基础服务', 'services', pathname.startsWith('/base-services'))}
          </>}
        </nav>
        <button className="sidebar-toggle" type="button" aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
          aria-expanded={!collapsed} onClick={() => setCollapsed((value) => !value)}>
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          {!collapsed && <span>收起侧边栏</span>}
        </button>
      </div>
    </Layout.Sider>
  )
}
