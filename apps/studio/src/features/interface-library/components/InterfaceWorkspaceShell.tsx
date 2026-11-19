import type { ReactNode } from 'react'
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
    <div className="workbench-page asset-library-page">
      <div className="asset-library-tab-panel">
        <div className="asset-library-tab-pane">
          <div className={`workbench-page interface-library-page tp-surface ${styles.pageRoot} ${interfacePageRootClass} ${interfaceScopes}${className ? ` ${className}` : ''}`}>
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
