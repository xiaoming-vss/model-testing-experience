import { Spin } from 'antd'
import { Suspense, type ReactNode } from 'react'
import { serviceCardLoadingClass } from '@/shared/utils/surfaceClasses'

export function RouteSuspense({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className={serviceCardLoadingClass}><Spin aria-label="页面加载中" /></div>}>
      {children}
    </Suspense>
  )
}
