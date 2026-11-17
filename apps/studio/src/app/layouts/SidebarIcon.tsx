import type { ReactNode } from 'react'

export type SidebarIconName = 'navSprint' | 'navRequirement' | 'testing' | 'assets' | 'navBug' | 'services'

// 顶部一级导航统一使用线性图标，形状与性能测试原型保持一致。
const shapes: Record<SidebarIconName, ReactNode> = {
  navSprint: <><path d="M8 6h13M8 12h13M8 18h13" /><circle cx="3" cy="6" r="1" fill="currentColor" stroke="none" /><circle cx="3" cy="12" r="1" fill="currentColor" stroke="none" /><circle cx="3" cy="18" r="1" fill="currentColor" stroke="none" /></>,
  navRequirement: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6" /></>,
  testing: <path d="M13 2 3 14h8l-1 8 10-12h-8z" />,
  assets: <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />,
  navBug: <><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></>,
  services: <><rect x="3" y="4" width="18" height="6" rx="2" /><rect x="3" y="14" width="18" height="6" rx="2" /><path d="M7 7h.01M7 17h.01" /></>,
}

export function SidebarIcon({ name }: { name: SidebarIconName }) {
  return <svg className="sidebar-icon" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
    aria-hidden="true" focusable="false">{shapes[name]}</svg>
}
