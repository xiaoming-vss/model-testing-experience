import type { ReactNode } from 'react'

export type SidebarIconName = 'navSprint' | 'navRequirement' | 'testing' | 'navBug' | 'services'

const shapes: Record<SidebarIconName, ReactNode> = {
  navSprint: <path d="M19 7a8 8 0 0 0-13-1L3 9m0-5v5h5M5 17a8 8 0 0 0 13 1l3-3m0 5v-5h-5" />,
  navRequirement: <><path className="sidebar-icon-fill" d="M7 3h7l5 5v12a1 1 0 0 1-1 1H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" /><path d="M14 3v5h5M9 12h6M9 16h6" /></>,
  testing: <><rect className="sidebar-icon-fill" x="5" y="4" width="14" height="17" rx="2" /><rect className="sidebar-icon-fill" x="9" y="2" width="6" height="4" rx="1" /><path d="m8 13 3 3 5-6" /></>,
  navBug: <><rect className="sidebar-icon-fill" x="7" y="7" width="10" height="14" rx="5" /><path d="M9 7V5a3 3 0 0 1 6 0v2M3 9l4 2m10 0 4-2M3 15h4m10 0h4M4 21l4-3m8 0 4 3M12 11v6" /></>,
  services: <><rect className="sidebar-icon-fill" x="3" y="3" width="18" height="7" rx="2" /><rect className="sidebar-icon-fill" x="3" y="14" width="18" height="7" rx="2" /><path d="M7 6.5h.01M7 17.5h.01M15 6.5h3M15 17.5h3" /></>,
}

export function SidebarIcon({ name }: { name: SidebarIconName }) {
  return <svg className="sidebar-icon sidebar-icon-duotone" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"
    aria-hidden="true" focusable="false">{shapes[name]}</svg>
}
