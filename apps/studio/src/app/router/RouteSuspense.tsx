import { Spin } from 'antd'
import { Suspense, type ReactNode } from 'react'

export function RouteSuspense({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className="grid min-h-[220px] place-items-center"><Spin aria-label="页面加载中" /></div>}>
      {children}
    </Suspense>
  )
}
