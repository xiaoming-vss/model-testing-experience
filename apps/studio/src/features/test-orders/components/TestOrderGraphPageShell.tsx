import type { ReactNode } from 'react'
import { MtxLogo } from '@/shared/components/MtxLogo/MtxLogo'
import { ThemeSelect } from '@/shared/components/ThemeSelect'
import { getTestOrderEntryStatusMeta, getTestOrderEntryStatusTone } from '../utils/testOrderStatus'
import type { TestOrder } from '../types'
import '@/shared/styles/surface-tokens.css'
import '../styles/graph-page.css'

type Props = {
  order?: TestOrder
  projectName?: string
  sprintName?: string
  children: ReactNode
}

export function TestOrderGraphPageShell({ order, projectName, sprintName, children }: Props) {
  const pending = Math.max(0, (order?.entriesTotal ?? 0) - (order?.entriesExecuted ?? 0))
  return (
    <div className="test-order-graph-page tp-surface">
      <header className="test-order-graph-page-brandbar">
        <div className="test-order-graph-page-brand"><MtxLogo size={30} /><strong>MTX</strong></div>
        <nav className="test-order-graph-page-context" aria-label="图谱所属范围">
          {projectName ? <span>{projectName}</span> : null}
          {sprintName ? <span>{sprintName}</span> : null}
          {order ? <span>测试单 {order.name}</span> : null}
        </nav>
        <ThemeSelect />
      </header>
      <main className="test-order-graph-page-main">
        <section className="test-order-graph-page-heading" aria-label="测试单概况">
          <h1>用例图谱</h1>
          {order ? <>
            <span className="tp-tone-tag tone-blue">{order.name}</span>
            {order.testedVersion ? <span className="test-order-graph-page-secondary">被测版本 {order.testedVersion}</span> : null}
            <span className="test-order-graph-page-secondary">已执行 {order.entriesExecuted ?? 0} / {order.entriesTotal ?? 0}</span>
            <div className="test-order-graph-page-counts">
              {[{ status: 'failed', count: order.entriesFailed ?? 0 }, { status: 'pending', count: pending }].map(({ status, count }) => (
                <span key={status} className={`tp-tone-tag tone-${getTestOrderEntryStatusTone(status)}`}>
                  {getTestOrderEntryStatusMeta(status).label} {count}
                </span>
              ))}
            </div>
          </> : null}
        </section>
        <div className="test-order-graph-page-content">{children}</div>
      </main>
    </div>
  )
}
