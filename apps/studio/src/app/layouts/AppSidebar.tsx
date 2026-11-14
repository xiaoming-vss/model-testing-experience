import { useLayoutEffect, useRef } from 'react'
import { MtxLogo } from '@/shared/components/MtxLogo/MtxLogo'
import { Link, useLocation } from 'react-router-dom'
import { SidebarIcon, type SidebarIconName } from './SidebarIcon'
import { assetTabForLocation, testingTabForLocation } from './navigation'
import '../styles/sidebar.css'

export function AppNavigationBrand({ bugOnly = false }: { bugOnly?: boolean }) {
  return <Link className="top-navigation-brand" to={bugOnly ? '/testing?tab=bugs' : '/projects'} aria-label={bugOnly ? 'MTX Bug列表' : 'MTX 迭代'}>
    <MtxLogo size={32} /><span>MTX</span>
  </Link>
}

export function AppSidebar({ bugOnly = false }: { bugOnly?: boolean }) {
  const { pathname, search } = useLocation()
  const navigationRef = useRef<HTMLElement>(null)
  const indicatorRef = useRef<HTMLSpanElement>(null)

  useLayoutEffect(() => {
    const navigation = navigationRef.current
    const indicator = indicatorRef.current
    if (!navigation || !indicator) return

    const updateIndicator = () => {
      const active = navigation.querySelector<HTMLElement>('[aria-current="page"]')
      if (!active) {
        indicator.style.opacity = '0'
        return
      }
      const firstPlacement = indicator.style.opacity !== '1'
      if (firstPlacement) indicator.style.transition = 'none'
      indicator.style.width = `${active.offsetWidth}px`
      indicator.style.transform = `translateX(${active.offsetLeft}px)`
      indicator.style.opacity = '1'
      if (firstPlacement) {
        void indicator.offsetWidth
        indicator.style.removeProperty('transition')
      }
    }

    updateIndicator()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(updateIndicator)
    observer?.observe(navigation)
    navigation.querySelectorAll('.sidebar-link').forEach(link => observer?.observe(link))
    window.addEventListener('resize', updateIndicator)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', updateIndicator)
    }
  }, [pathname, search, bugOnly])
  const inRequirements = pathname.startsWith('/requirements')
  const inProjects = pathname.startsWith('/projects') || inRequirements
  const projectBoard = inRequirements || new URLSearchParams(search).get('board') === 'requirements' ? 'requirements' : 'sprints'
  const testingTab = testingTabForLocation(pathname, search)
  const assetTab = assetTabForLocation(pathname, search)
  const assetHref = pathname.startsWith('/asset-library/interfaces')
    ? `${pathname}${search}`
    : `/asset-library?tab=${assetTab ?? 'cases'}`
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

  return (
    <div className="app-top-navigation">
      <nav ref={navigationRef} className="top-navigation-links" aria-label="主导航">
        <span ref={indicatorRef} className="top-navigation-indicator" aria-hidden="true" />
        {bugOnly ? navLink('/testing?tab=bugs', 'Bug列表', 'navBug', testingTab === 'bugs') : <>
          {(['sprints', 'requirements'] as const).map((board) => {
            const params = new URLSearchParams(inProjects ? search : '')
            params.delete('projectPanel')
            params.delete('panelProjectId')
            params.set('board', board)
            return navLink(`/projects?${params}`, board === 'sprints' ? '迭代' : '需求',
              board === 'sprints' ? 'navSprint' : 'navRequirement', inProjects && projectBoard === board)
          })}
          {navLink(testingHref(testingTab && testingTab !== 'bugs' ? testingTab : 'orders'), '测试', 'testing', Boolean(testingTab && testingTab !== 'bugs'))}
          {navLink(assetHref, '资产库', 'assets', Boolean(assetTab))}
          {navLink(testingHref('bugs'), 'Bug列表', 'navBug', testingTab === 'bugs')}
          {navLink('/base-services', '基础服务', 'services', pathname.startsWith('/base-services'))}
        </>}
      </nav>
    </div>
  )
}
