import { useLayoutEffect, useRef, useState } from 'react'
import { MtxLogo } from '@/shared/components/MtxLogo/MtxLogo'
import { Link, useLocation } from 'react-router-dom'
import { SidebarIcon, type SidebarIconName } from './SidebarIcon'
import {
  ASSET_LIBRARY_TABS,
  assetTabForLocation,
  testingTabForLocation,
  type AssetLibraryTab,
} from './navigation'
import { TopNavTabMenu } from './TopNavTabMenu'
import { TESTING_TAB_OPTIONS } from '@/features/testing/components/testingTab'
import {
  BASE_SERVICE_TABS,
  resolveBaseServiceTab,
  type BaseServiceTab,
} from '@/features/base-services/baseServiceTabs'
import '../styles/sidebar.css'

type TopNavMenuKey = 'testing' | 'assets' | 'services'

export function AppNavigationBrand({ bugOnly = false }: { bugOnly?: boolean }) {
  return <Link className="top-navigation-brand" to={bugOnly ? '/testing?tab=bugs' : '/projects'} aria-label={bugOnly ? 'MTX Bug列表' : 'MTX 迭代'}>
    <MtxLogo size={32} /><span>MTX</span>
  </Link>
}

export function AppSidebar({ bugOnly = false }: { bugOnly?: boolean }) {
  const { pathname, search } = useLocation()
  const navigationRef = useRef<HTMLElement>(null)
  const indicatorRef = useRef<HTMLSpanElement>(null)
  const [openMenu, setOpenMenu] = useState<TopNavMenuKey | null>(null)

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
  const baseServiceTab = pathname.startsWith('/base-services')
    ? resolveBaseServiceTab(new URLSearchParams(search).get('tab'))
    : null
  const assetTriggerHref = pathname.startsWith('/asset-library/interfaces')
    ? `${pathname}${search}`
    : assetHref(assetTab ?? 'cases')
  function testingHref(tab: string) {
    const params = new URLSearchParams(pathname === '/testing' ? search : '')
    params.set('tab', tab)
    return `/testing?${params}`
  }
  function assetHref(tab: AssetLibraryTab) {
    const params = new URLSearchParams(pathname.startsWith('/asset-library') ? search : '')
    params.set('tab', tab)
    return `/asset-library?${params}`
  }
  function baseServicesHref(tab: BaseServiceTab) {
    const params = new URLSearchParams(pathname.startsWith('/base-services') ? search : '')
    params.set('tab', tab)
    return `/base-services?${params}`
  }
  function handleMenuOpenChange(key: TopNavMenuKey, nextOpen: boolean) {
    setOpenMenu(current => nextOpen ? key : current === key ? null : current)
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
          <TopNavTabMenu label="测试" menuLabel="测试工作区" icon="testing"
            items={TESTING_TAB_OPTIONS}
            activeKey={testingTab && testingTab !== 'bugs' ? testingTab : null}
            hrefForItem={testingHref}
            open={openMenu === 'testing'}
            onOpenChange={nextOpen => handleMenuOpenChange('testing', nextOpen)} />
          {navLink(testingHref('bugs'), 'Bug列表', 'navBug', testingTab === 'bugs')}
          <TopNavTabMenu label="资产库" menuLabel="资产库" icon="assets"
            items={ASSET_LIBRARY_TABS}
            activeKey={assetTab}
            hrefForItem={assetHref}
            triggerHref={assetTriggerHref}
            open={openMenu === 'assets'}
            onOpenChange={nextOpen => handleMenuOpenChange('assets', nextOpen)} />
          <TopNavTabMenu label="基础服务" menuLabel="基础服务" icon="services"
            items={BASE_SERVICE_TABS}
            activeKey={baseServiceTab}
            hrefForItem={baseServicesHref}
            open={openMenu === 'services'}
            onOpenChange={nextOpen => handleMenuOpenChange('services', nextOpen)} />
        </>}
      </nav>
    </div>
  )
}
