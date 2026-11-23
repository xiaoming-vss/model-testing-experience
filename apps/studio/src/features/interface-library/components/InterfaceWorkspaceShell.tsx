import type { ReactNode } from 'react'
import {
  ASSET_LIBRARY_PAGE_CLASS,
  ASSET_LIBRARY_TAB_PANEL_CLASS,
  ASSET_LIBRARY_TAB_PANE_CLASS,
} from '@/shared/ui/assetLibraryShell'
import { interfacePageRootClass } from '../pageClasses'
import styles from '../styles/interface-library.module.css'
import detailStyles from '../styles/interface-detail.module.css'

const interfaceScopes = `${styles.scope} ${detailStyles.scope}`

export function InterfaceWorkspaceShell({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={ASSET_LIBRARY_PAGE_CLASS}>
      <div className={ASSET_LIBRARY_TAB_PANEL_CLASS}>
        <div className={ASSET_LIBRARY_TAB_PANE_CLASS}>
          <div className={`workbench-page interface-library-page tp-surface ${styles.pageRoot} ${interfacePageRootClass} ${interfaceScopes}${className ? ` ${className}` : ''}`}>
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
